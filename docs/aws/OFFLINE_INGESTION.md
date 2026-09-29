# Offline AWS POC ingestion

Step 3 of [the Phase 1 plan](PHASE_1_AWS_POC_PLAN.md) is implemented by
`scripts/ingest_poc.py`. It validates the four reviewed PDFs and current metadata
sidecars, checks live AWS resources, uploads the eight approved source objects,
then starts and monitors one Bedrock ingestion job. Once the runner initializes,
it writes a JSON report and returns nonzero on validation, upload, API, job,
document, or timeout failures. Startup failures while loading Terraform outputs,
parsing settings, or creating AWS clients may exit before a report is created;
inspect the terminal error in that case.
A successful deployed run is still required to accept step 3. Retrieval,
source citations and owner/LOB isolation are separate step 4 acceptance checks.

## Quick start

First complete the [development offline deployment](../../infra/aws/terraform/README.md#development-offline-deployment)
setup and policy attachments. Infrastructure deployment commands are maintained
there; repeat ingestion uses the existing deployment and does not require another
Terraform apply. Keep the query API disabled until offline validation passes.

Use the approved ingestion operator's AWS credentials/profile and an initialized
Terraform backend with read access to the applied development outputs. No model
API keys or application secrets are needed. Run from the repository root:

```sh
# Step 1
uv sync --locked

# Step 2
PYTHONPATH=src uv run --locked python scripts/ingest_poc.py \
  --terraform-dir infra/aws/terraform/development
```

The ingestion command reads `ingestion_environment` directly from Terraform's
applied outputs; there are no bucket names or resource IDs to copy. It uses the
standard AWS credential chain. Select the intended profile (for example, with
`AWS_PROFILE`) and refresh its credentials using your normal login method if
needed. The command does not deploy infrastructure. See the
[Terraform README](../../infra/aws/terraform/README.md) for infrastructure scope,
backend setup, and deployment migration guidance.

Reports default to `ingestion_reports/<timestamp>_<unique_id>.json` (gitignored).
Use `--report PATH` for a chosen location. The report includes run ID, document
hashes, uploaded keys, duration, full ingestion job ID/status/statistics/failure
reasons, and whether the coordination lock was retained. It contains no PDF
content. Preserve the report, especially on timeout or lost AWS responses.
The timeout limits polling; an in-flight SDK call can also take its configured
network timeout/retries. A local timeout does not stop the AWS ingestion job.

## Failures and retries

**A local timeout does not stop the AWS ingestion job.** If a lock is retained,
follow [retained-lock recovery](OFFLINE_INGESTION_REFERENCE.md#retained-lock-recovery)
before retrying. Never clear it while the original process or an AWS job is active.
Use this runner for every sync; console sync, scheduled sync, and
`bedrock_smoke.py ingest` bypass its lock and can ingest a partial upload.

## Live acceptance after ingestion

Retain the successful ingestion report, then complete the Phase 1 plan's
[indexing validation requirements](PHASE_1_AWS_POC_PLAN.md#4-configure-and-validate-document-indexing):
verify all four documents, source references, combined owner/LOB filtering, and
replacement of a revised document. Retain evidence for these checks separately
from the ingestion report. A successful ingestion job does not prove retrieval
correctness or isolation.

Follow the [step-by-step manual index validation runbook](OFFLINE_INDEX_VALIDATION.md)
for commands, expected results, isolation checks, and document replacement.
An automated index-validation command remains
[pending](../PHASE_1_PENDING_WORK.md#offline-ingestion-and-validation-services).
The generic smoke retrieval helper does not establish this acceptance gate.
Keep `enable_query_api = false` and do not set `index_validation_passed = true`
until the live validation evidence has been reviewed. Then follow the
[query deployment instructions](../../infra/aws/terraform/README.md#phase-1-query-deployment).

## Operational reference

- [Configuration, permissions, and setup without Terraform access](OFFLINE_INGESTION_REFERENCE.md#terraform-and-permissions)
- [Policy revisions, inventory, locking, and migration](OFFLINE_INGESTION_REFERENCE.md#revisions-inventory-and-serialization)
- [Retained-lock recovery](OFFLINE_INGESTION_REFERENCE.md#retained-lock-recovery)
- [Local verification and observability limitations](OFFLINE_INGESTION_REFERENCE.md#local-verification)
