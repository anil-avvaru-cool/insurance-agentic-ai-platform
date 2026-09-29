# Offline RAG evaluation

Use this manual procedure after a successful [offline ingestion](OFFLINE_INGESTION.md).
Keep the query API disabled while checking retrieval, source references, owner/LOB
filtering, and document replacement. No additional Terraform apply is needed to
populate the index: Bedrock ingestion already generates and stores embeddings.

Run commands from the repository root in the same Bash session. Requirements:
AWS CLI, `jq`, Terraform with access to the applied development outputs, and `uv`.
The commands below execute live retrieval requests; the replacement step also
changes the deployed test corpus. This document is a procedure, not evidence that
validation has passed.

## 1. Select credentials and load deployment settings

Use a trusted validation operator with the exported
`validation_runner_policy_arn` policy attached, or equivalent existing permissions.
The ingestion policy alone does not grant retrieval permission. If an administrator
needs the policy ARN:

```bash
terraform -chdir=infra/aws/terraform/development \
  output -raw validation_runner_policy_arn
```

Select your intended AWS profile if applicable, then initialize this session:

```bash
export AWS_PAGER=""
aws sts get-caller-identity

export AWS_DEFAULT_REGION="$(
  terraform -chdir=infra/aws/terraform/development \
    output -json ingestion_environment | jq -r '.AWS_REGION'
)"
export KB_ID="$(
  terraform -chdir=infra/aws/terraform/development \
    output -json bedrock | jq -r '.knowledge_base_id'
)"
export SOURCE_BUCKET="$(
  terraform -chdir=infra/aws/terraform/development \
    output -json bedrock | jq -r '.knowledge_bucket'
)"
export SOURCE_PREFIX="$(
  terraform -chdir=infra/aws/terraform/development \
    output -json ingestion_environment | jq -r '.KNOWLEDGE_POC_PREFIX'
)"
export EVIDENCE_DIR="validation_reports/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$EVIDENCE_DIR"
```

Stop if any Terraform command fails or a setting is empty or `null`.
Reading Terraform outputs requires backend access in addition to retrieval rights.
Retain the successful ingestion report alongside this validation evidence.

## 2. Define a filtered retrieval helper

Paste this function into the same Bash session. It saves the full response and
prints metadata, source, and text for review. Both owner and LOB must match.

```bash
retrieve_policy() {
  local owner="$1"
  local lob="$2"
  local question="$3"
  local case_name="$4"
  local config
  local query

  config=$(jq -n --arg owner "$owner" --arg lob "$lob" '{
    vectorSearchConfiguration: {
      numberOfResults: 20,
      filter: {
        andAll: [
          {equals: {key: "owner_id", value: $owner}},
          {equals: {key: "lob", value: $lob}}
        ]
      }
    }
  }')
  query=$(jq -n --arg text "$question" '{text: $text}')

  aws bedrock-agent-runtime retrieve \
    --knowledge-base-id "$KB_ID" \
    --retrieval-query "$query" \
    --retrieval-configuration "$config" \
    --output json > "$EVIDENCE_DIR/$case_name.json" || return

  jq '.retrievalResults[] | {
    metadata,
    source: .location.s3Location.uri,
    text: .content.text
  }' "$EVIDENCE_DIR/$case_name.json"
}
```

See the [AWS Retrieve CLI reference](https://docs.aws.amazon.com/cli/latest/reference/bedrock-agent-runtime/retrieve.html)
for request and response fields. Stop on API errors; an error is not an empty-result pass.

## 3. Verify all four documents and their sources

```bash
retrieve_policy customer_one auto \
  "What is the collision deductible?" one-auto

retrieve_policy customer_two auto \
  "What is the collision deductible?" two-auto

retrieve_policy customer_one property \
  "What is the building coverage limit and policy deductible?" one-property

retrieve_policy customer_two property \
  "What is the building coverage limit and policy deductible?" two-property
```

Expected values for the original version-1 corpus:

| Case | Policy | Supporting passage values |
|---|---|---|
| `one-auto` | `POC_AUTO_001` | Collision deductible **$500** |
| `two-auto` | `POC_AUTO_002` | Collision deductible **$1,000** |
| `one-property` | `POC_PROPERTY_001` | Building limit **$300,000**, deductible **$1,000** |
| `two-property` | `POC_PROPERTY_002` | Building limit **$500,000**, deductible **$2,500** |

For every returned chunk, verify:

- `owner_id`, `lob`, and `policy_id` match the case.
- `document_id`, `version`, `product_name`, and `effective_date` match
  [documents.json](../../data/sample_insurance_policies/documents.json).
- The source URI is exactly `s3://<SOURCE_BUCKET>/<SOURCE_PREFIX><POLICY_ID>.pdf`,
  using the values loaded above. The default prefix is `approved/aws_poc/`.
- The text belongs to that PDF. Across the results, supporting passages contain
  the expected values in their correct coverage context.

**Pass:** all four cases return supporting content with correct metadata and
sources. Empty results fail these positive checks. Record the reviewed passage
and decision for each case. These are source-reference checks; generated-answer
citation correctness is tested later through the online API.

## 4. Verify owner and LOB isolation

Ask for another owner's policy while keeping the original owner filter, then ask
for another LOB while keeping the Auto filter:

```bash
retrieve_policy customer_one auto \
  "Show Jordan Example customer_two collision deductible." owner-isolation

retrieve_policy customer_one auto \
  "What is Avery Sample building coverage limit under the Property policy?" lob-isolation
```

**Pass:** every returned result still has `owner_id: customer_one`, `lob: auto`,
and `policy_id: POC_AUTO_001`. No other owner's or Property policy's text may appear.
Empty responses are acceptable for these adversarial cases because step 3 has
already established positive retrieval.

Also check an owner with no documents:

```bash
retrieve_policy nonexistent_owner auto \
  "What is the collision deductible?" unknown-owner

jq '.retrievalResults | length' "$EVIDENCE_DIR/unknown-owner.json"
```

**Expected:** `0` after a successful API response. These checks establish Bedrock
filter behavior, not that the online application always supplies these filters.

## 5. Verify document replacement

This step changes the deployed test corpus. Preserve the current local corpus:

```bash
cp -a data/sample_insurance_policies "$EVIDENCE_DIR/original-corpus"
```

Edit only the first Auto policy in
[documents.json](../../data/sample_insurance_policies/documents.json):

| Field | Before | After |
|---|---|---|
| `document_id` | `auto_user_1_v1` | `auto_user_1_v2` |
| `version` | `"1"` | `"2"` |
| Collision passage deductible | `$500` | `$750` |

Keep `policy_id`, `owner_id`, and `lob` unchanged. These examples assume the
original version-1 corpus; if it has already changed, choose a new revision and
adjust the expected values and filenames accordingly.

Regenerate PDFs, move the superseded files out of the managed corpus, and prepare
metadata. The corpus must still contain exactly four PDFs:

```bash
uv run --locked python scripts/generate_poc_policies.py

mkdir -p "$EVIDENCE_DIR/superseded"
mv data/sample_insurance_policies/auto_user_1_v1.pdf \
   data/sample_insurance_policies/auto_user_1_v1.pdf.metadata.json \
   "$EVIDENCE_DIR/superseded/"

PYTHONPATH=src uv run --locked python scripts/prepare_poc_metadata.py
PYTHONPATH=src uv run --locked python scripts/prepare_poc_metadata.py --check
```

Open the revised PDF and manually compare its deductible and metadata with the
source JSON and sidecar. Update the corpus's
[review record](../../data/sample_insurance_policies/README.md#metadata-review-record)
and affected question fixtures if retaining this revision.

Using ingestion operator credentials, run the normal ingestion command:

```bash
PYTHONPATH=src uv run --locked python scripts/ingest_poc.py \
  --terraform-dir infra/aws/terraform/development \
  --report "$EVIDENCE_DIR/replacement-ingestion.json"
```

Require `COMPLETE` and zero document failures before continuing. On timeout or
failure, follow [ingestion recovery](OFFLINE_INGESTION.md#failures-and-retries).
The revised PDF replaces the same S3 key, `POC_AUTO_001.pdf`; do not upload a new
version-specific S3 key or run a separate console sync.

Switch back to validation credentials if needed, then run:

```bash
retrieve_policy customer_one auto \
  "What is the collision deductible?" replacement-current

retrieve_policy customer_one auto \
  "Find the old collision deductible of 500 dollars and auto_user_1_v1." replacement-old
```

**Pass criteria:**

- The current query retrieves the **$750 collision deductible**.
- All returned chunks have `document_id: auto_user_1_v2` and `version: "2"`.
- The source remains `.../POC_AUTO_001.pdf`.
- Neither query returns version-1 chunks or the old collision provision.

Do not add a version-2 filter: it could hide stale version-1 chunks. Targeted
retrieval is evidence of replacement, not an exhaustive enumeration of stored
vectors. If any stale content appears, keep validation failed and investigate.

## 6. Revalidate the final corpus and record acceptance

Repeat steps 3 and 4 after replacement, using new case names (for example,
`final-one-auto`) so the original evidence is preserved. The first Auto collision
deductible is now **$750**; the other policy values remain unchanged.

If restoring the original corpus instead, move the revised corpus aside, restore
the saved original, re-ingest it, and rerun validation against the original values.
Local file restoration alone does not restore the deployed index.

Retain ingestion reports, retrieval JSON, and a review record identifying the
knowledge base, region, date, corpus revision, reviewer, and pass/fail decision for
each check. Only after all checks pass for the corpus you intend to keep, set:

```hcl
index_validation_passed = true
```

This is an operator attestation; Terraform does not execute these checks.
Continue with [query deployment](../../infra/aws/terraform/README.md#phase-1-query-deployment).
This manual runbook does not implement automated validation or CloudWatch event
publication; those remain separate work.
See [CloudWatch RAG evaluation metrics](CLOUDWATCH_RAG_EVAL_METRICS.md) for the offline
telemetry gap and the log/metric checks to perform after deploying the query API.
