# Offline AWS POC ingestion

Step 3 of [the Phase 1 plan](PHASE_1_AWS_POC_PLAN.md) is implemented by
`scripts/ingest_poc.py`. It validates the four reviewed PDFs and current metadata
sidecars, checks live AWS resources, uploads the eight approved source objects,
then starts and monitors one Bedrock ingestion job. It writes a JSON report and
returns nonzero on validation, upload, API, job, document, or timeout failures.
A successful deployed run is still required to accept step 3. Retrieval,
source citations and owner/LOB isolation are separate step 4 acceptance checks.

## Short path

Use your AWS development login/profile and the existing initialized Terraform
backend. No model API keys or application secrets are needed. Run from the repo:

```sh
aws login  # only if your AWS CLI login session has expired
uv sync --locked
terraform -chdir=infra/aws/terraform/development init -reconfigure \
  -backend-config=development.s3.tfbackend
terraform -chdir=infra/aws/terraform/development plan -out=development.tfplan
terraform -chdir=infra/aws/terraform/development show development.tfplan
# Apply after reviewing the plan, including any unrelated existing infrastructure:
terraform -chdir=infra/aws/terraform/development apply development.tfplan
PYTHONPATH=src uv run --locked python scripts/ingest_poc.py \
  --terraform-dir infra/aws/terraform/development
```

The ingestion command reads `ingestion_environment` directly from Terraform's
applied outputs; there are no bucket names or resource IDs to copy. It uses the
standard AWS credential chain. It does not deploy infrastructure. The development
root also manages RDS, SQS, ECR and networking; it is not an ingestion-only stack.
For a new account/backend, follow the [Terraform setup](../infra/aws/terraform/README.md).
AgentCore image publishing and the runtime root are unnecessary for ingestion.

Reports default to `ingestion_reports/<timestamp>_<unique_id>.json` (gitignored).
Use `--report PATH` for a chosen location. The report includes run ID, document
hashes, uploaded keys, duration, full ingestion job ID/status/statistics/failure
reasons, and whether the coordination lock was retained. It contains no PDF
content. Preserve the report, especially on timeout or lost AWS responses.
The timeout limits polling; an in-flight SDK call can also take its configured
network timeout/retries. A local timeout does not stop the AWS ingestion job.

## Terraform and permissions

The settings reviewed for this POC are:

| Setting | Value |
|---|---|
| Dedicated data-source prefix | `approved/aws_poc/` |
| Parser | Bedrock default text parser; these PDFs have selectable text |
| Embedding | Titan Text Embeddings V2, FLOAT32, 1,024 dimensions |
| Vector index | S3 Vectors, 1,024 dimensions, cosine distance |
| Chunking | Fixed size, 300 tokens, 15% overlap |
| Filterable metadata | Includes `owner_id` and `lob` |
| Data-source deletion policy | `DELETE` |
| Polling timeout | 900 seconds |
| Document storage | Private, encrypted and versioned S3 |

`knowledge_poc_prefix` and `knowledge_ingestion_timeout_seconds` are optional
Terraform overrides. Required region/account variables and the backend must
point to the same intended deployment. The runner checks actual bucket region,
knowledge-base/data-source status, prefix, model, index and chunking configuration,
plus every page of ingestion jobs before uploading. These checks cannot prove
that the Bedrock service role can invoke the model or write vectors; a successful
job is the final operational check.

Terraform creates `ingestion_runner_policy_arn`. Set `ingestion_runner_role_name`
to attach it to an existing operator IAM role, or attach the output policy via
your IAM/SSO administration. An existing deployment identity with these rights
can run immediately. The policy permits only eight document object uploads,
lock reads/writes/deletion, bucket inspection/listing, vector-index inspection,
and Bedrock configuration/job APIs. The knowledge-base service role separately
reads the configured prefix and invokes embeddings/writes vectors. The ingestion
identity needs no document-delete permission. Reading Terraform outputs also
requires the operator's existing backend read permissions, separate from this policy.

The parser and embedding/chunk settings above intentionally match the Phase 1
plan. The runner rejects incompatible deployed settings instead of silently
indexing with a different configuration. S3 Vectors limits custom metadata to
1 KiB; the runner checks the seven prepared fields against this limit.
See [AWS vector-store requirements](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-setup.html).

For environments without local Terraform state access, set every required value
in `.env` using [example.env](../example.env):

```dotenv
AWS_REGION=us-east-1
KNOWLEDGE_BUCKET=your_actual_bucket
KNOWLEDGE_POC_PREFIX=approved/aws_poc/
BEDROCK_KNOWLEDGE_BASE_ID=YOURKB1234
BEDROCK_DATA_SOURCE_ID=YOURDS1234
KNOWLEDGE_INGESTION_TIMEOUT_SECONDS=900
```

```sh
PYTHONPATH=src uv run --locked --env-file .env python scripts/ingest_poc.py
```

When `--terraform-dir` is supplied, its output overrides these six settings.

## Revisions, inventory and serialization

Each run copies the corpus to a temporary snapshot and validates all PDFs and
sidecars before any AWS write. Only the four PDF/sidecar pairs enter the indexed
prefix; review notes, questions, source JSON and README files stay local.

S3 object names use stable policy IDs: `POC_AUTO_001.pdf`, `POC_AUTO_002.pdf`,
`POC_PROPERTY_001.pdf`, `POC_PROPERTY_002.pdf`, plus their `.metadata.json`
sidecars. The actual document ID/version stays in the PDF and metadata.
A revised local filename such as `auto_user_1_v2.pdf` replaces
`POC_AUTO_001.pdf`; it does not add a second source. Old S3 object versions remain
recoverable through bucket versioning, but are not separate current sources for
Bedrock ingestion. Bedrock syncs source changes incrementally; verify superseded
content is absent in step 4. See [AWS data-source updates](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-ds-update.html).

To revise a policy, edit `documents.json`, regenerate the PDFs, remove the
superseded local PDF/sidecar, regenerate sidecars, update question fixtures and
the metadata review record, then run the same ingestion command. The current
allowlist requires exactly four policies, so additions or removal of a policy
fail before upload and require an explicit code/Terraform inventory review.
Unexpected remote objects also block sync; the runner never deletes them or
cleans a whole prefix. No source cleanup is needed for normal revisions.

A conditional S3 `If-None-Match: *` write takes a shared lock at
`ingestion_control/<kb_id>/<source_id>/run_lock.json`, outside the indexed prefix.
Every runner targeting this data source must use this command. The lock has no
expiry, so a slow process cannot silently lose ownership. Release uses the
acquired ETag with `If-Match`. See [AWS conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html)
and [conditional deletes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-deletes.html).

The command uploads the full validated snapshot before starting ingestion. A
partial upload failure releases the lock and starts no job; rerun to repair all
eight objects. A terminal job failure releases the lock and records the failure.
Timeout, polling errors or an uncertain start retain the lock. Do not use console
sync, `bedrock_smoke.py ingest`, a scheduled sync, or other writers on this POC data
source: they do not participate in the lock and can ingest a partial upload.
This POC does not offer an atomic online cutover while a sync is in progress.

If migrating an already-ingested data source from the old broad `approved/`
prefix, inspect existing content first. Narrowing a prefix is not proof that old
embeddings have been removed. Rebuild/clean the existing index through a reviewed
migration and verify retrieval before using it for this POC. Do not delete data
outside the managed inventory. `DELETE` controls embedding removal when deleting
the data-source resource; it does not itself perform that migration.

## Retained-lock recovery

Do not clear a lock while its runner could still upload or its AWS job is active.
Stop/confirm termination of the original process first, then inspect the run report
and lock object. The lock contains the run ID, KB/source IDs and durable client token.
Use the report's values and the same region/profile in these commands:

```sh
aws bedrock-agent get-ingestion-job --region REGION \
  --knowledge-base-id KB_ID --data-source-id SOURCE_ID --ingestion-job-id JOB_ID
```

If the start response was lost, list jobs and match description `poc_run_<run_id>`:

```sh
aws bedrock-agent list-ingestion-jobs --region REGION \
  --knowledge-base-id KB_ID --data-source-id SOURCE_ID
```

For a report with a start attempt but no known job ID, retry the original
`start-ingestion-job` using the **same** `--client-token RUN_ID` and
`--description poc_run_RUN_ID` to recover its idempotent response. Do not change
the token or upload again while resolving that attempt. Only do this after
confirming all eight uploads completed in that run's report. AWS documents
[StartIngestionJob idempotency](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_StartIngestionJob.html).

Wait for `COMPLETE`, `FAILED` or `STOPPED` and inspect document failures. If the
process crashed before starting ingestion, verify there is no active job. Once
both the old process and all jobs are stopped, read the lock, confirm its run ID,
and obtain its ETag. Delete only that exact lock with the same ETag:

```sh
aws s3api get-object --region REGION --bucket BUCKET --key LOCK_KEY /tmp/poc_run_lock.json
aws s3api delete-object --region REGION --bucket BUCKET --key LOCK_KEY --if-match 'ETAG_FROM_GET'
```

Do not use recursive S3 deletion. Rerun the normal command after correcting the
failure. A process crash may leave a lock even if the local report was not updated;
treat the remote lock as authoritative and inspect before retrying.

## Verification

```sh
PYTHONPATH=src:. uv run --locked python -m unittest discover -s tests/unit -v
terraform fmt -check -recursive infra/aws/terraform
terraform -chdir=infra/aws/terraform/development validate
terraform -chdir=infra/aws/terraform/development test
```

Tests cover invalid/stale corpus, partial uploads, overlapping runs, live config
mismatch, paginated active jobs, failed/stopped jobs, document failures, timeouts,
lost start/poll responses, repeat runs, revised document IDs and unknown inventory.
These are local tests using AWS doubles/mocked Terraform providers. The runner's
JSON report supplies step 3 observability; CloudWatch metrics, dashboards, alarms
and alert delivery remain step 8 work.
