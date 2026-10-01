# Bedrock judge operator runbook

- Local implementation is ready; deployment, evaluator access, actual captures, service output/empty-context verification, and the paid baseline remain pending.
- `prepare`, `export`, `reserve`, and `summarize` are offline. `capture` sends up to six paid API requests; `submit` starts a paid evaluation. `upload`, `status`, and `collect` access AWS/S3.
- Use `.env` and [example.env](../../example.env). Set every `JUDGE_*` value, including both evaluator IDs and separate `JUDGE_CUSTOM_JUDGE_*` rates/bounds. Rates must be operator-reviewed and dated within 30 days. Bounds include context, references and judge prompt overhead.
- Estimate: six capture requests, twelve built-in assessments and six custom assessments. Eighteen assessments is not a promise about internal invocation count. The USD budget and safety multiplier gate initial preparation/submission; they are not AWS billing caps.

## Deployment preparation

- In `infra/aws/terraform/development/terraform.tfvars`, set `enable_rag_judge = true`, `judge_evaluator_model_id`, and `judge_custom_evaluator_model_id` to supported regional foundation models. Inference profiles require additional IAM configuration and are not covered by this Terraform setup.
- Set `judge_operator_role_name` to an existing operator role, or attach the exported `rag_judge_operator_policy_arn` through your identity system. The operator also needs the existing API invocation/capture-read permissions for capture.
- Judge storage uses private S3, SSE-S3 encryption, TLS-only access and `force_destroy = false`. The Bedrock service role reads `datasets/`, writes `results/`, and accesses the configured evaluator models. No new Knowledge Base is created. This setup does not use customer-managed KMS keys.
- Enable the query API and `enable_evaluation_capture`, build the query ZIP and review its deployment as described in [evidence capture](ONLINE_RAG_EVALUATION.md#exact-evidence-capture-for-judge-evaluation).

```bash
terraform -chdir=infra/aws/terraform/development validate
terraform -chdir=infra/aws/terraform/development test
# User deployment: review the saved plan, then apply it yourself.
terraform -chdir=infra/aws/terraform/development plan -input=false -out=development.tfplan
terraform -chdir=infra/aws/terraform/development show development.tfplan
# After deployment, copy these outputs into .env:
terraform -chdir=infra/aws/terraform/development output -json rag_judge_environment
terraform -chdir=infra/aws/terraform/development output -json evaluation_capture_environment
```

- Also set `RAG_QUERY_ENDPOINT`, `JUDGE_DEPLOYMENT_ID` (deployed ZIP hash), `JUDGE_MODEL_ID` and `JUDGE_KNOWLEDGE_BASE_ID`. Verify ingestion matches the local corpus before capture. AWS credentials use the standard profile/role chain.
- Use a unique `JUDGE_DATASET_S3_URI` under `datasets/` for each new run, for example `datasets/baseline_001.jsonl`. Upload refuses to replace different content at an existing key.
- `JUDGE_RAG_SOURCE_ID=insurance_api` is the precomputed source label, independent of the deployed KB ID. It appears in both dataset rows and the request.

## Prepare and capture

```bash
uv run --locked --env-file .env python scripts/evaluate_rag.py prepare --output evaluation_reports/baseline/prepared.json
# Paid: six selected baseline questions, no API retries; stops on a failed check.
uv run --locked --env-file .env python scripts/evaluate_rag.py capture --prepared evaluation_reports/baseline/prepared.json --output evaluation_reports/baseline/captures.json
uv run --locked python scripts/evaluate_rag.py export --prepared evaluation_reports/baseline/prepared.json --captures evaluation_reports/baseline/captures.json --output evaluation_reports/baseline/export
```

- `prepare` validates fixtures/PDFs, records hashes and costs, and saves an SDK-validated request with a stable token. Service naming is checked separately because SDK shape validation does not check regex patterns; job names use lowercase letters/digits.
- `capture` records each response as it arrives and refuses to overwrite its report. A failed capture retains partial evidence and exits nonzero. A new capture run incurs additional API cost; it does not resume automatically.
- `export` requires exactly six successful responses and checks timestamps, deployment/model/KB identity, captured filters, owner/LOB/document isolation, exact generation context, citation references and usage. It never substitutes fixture passages for retrieved evidence.
- Empty retrieval stays empty. `manifest.json` flags service verification and retains row hashes, owner/LOB associations and pending review fields. These are local records, not extra AWS dataset fields.
- Optional existing ledger: `uv run --locked python scripts/evaluate_rag.py reserve --prepared evaluation_reports/baseline/prepared.json --ledger evaluation_reports/budget.sqlite3`. It is not required by this workflow. All reservations using it must share a budget and database; there is no settlement/release mechanism.

## Upload and submit one job

```bash
uv run --locked --env-file .env python scripts/evaluate_rag.py upload --prepared evaluation_reports/baseline/prepared.json --export evaluation_reports/baseline/export --state evaluation_reports/baseline/upload.json
# Paid: three metrics across the six supplied answers; no additional API capture.
uv run --locked --env-file .env python scripts/evaluate_rag.py submit --prepared evaluation_reports/baseline/prepared.json --export evaluation_reports/baseline/export --state evaluation_reports/baseline/submission.json
```

- `submit` verifies S3 bytes against the local export and saves region, request/token, manifest and dataset hash before calling Bedrock; it then saves the returned ARN.
- If submission times out or returns an ambiguous failure, rerun the **same submit command with the same files**. Recovery reuses the saved request/token even after pricing expires. Once an ARN is recorded, repeat submission returns that ARN without creating another job.
- Keep the input key and all local files intact while a job runs. Do not prepare a new run to retry an ambiguous submission. Run one command per state file at a time.

## Status, collection and review

```bash
uv run --locked --env-file .env python scripts/evaluate_rag.py status --state evaluation_reports/baseline/submission.json --output evaluation_reports/baseline/status.json
# Run after status is Completed:
uv run --locked --env-file .env python scripts/evaluate_rag.py collect --state evaluation_reports/baseline/submission.json --output evaluation_reports/baseline/results
# Optional offline regeneration from downloaded artifacts; use a new output file:
uv run --locked python scripts/evaluate_rag.py summarize --export evaluation_reports/baseline/export --results evaluation_reports/baseline/results/artifacts --output evaluation_reports/baseline/review.json
```

- Status preserves failure messages; inspect them before considering another paid job. No polling or automated reruns occur.
- Collection downloads only `results/<saved_job_name>/<job_id>/`, including custom metric definitions, and retains raw artifacts plus `job.json`, `downloads.json` and `report.json`. Use a new local output directory to collect again.
- Summary associates `inputRecord` with validated row hashes, not file ordering. It reads `automatedEvaluationResult.scores` (`metricName`, `result`, available `explanation`/`reason`), including separate per-metric files. Unknown service formats/rows are recorded as incomplete; raw artifacts remain available for first-run inspection. Duplicate case/metric results fail explicitly.
- Scores must be finite numbers; the custom metric must be 0 or 1. Missing/unavailable scores remain null. `scores_complete` means all 18 scores exist, not that answers passed. Summary exits 1 for incomplete results.
- Review every case's correctness, faithfulness, custom score and explanations. Add `review_notes`, reviewer and review decision locally. Separate custom summaries cover all six, the two abstention cases, and four answerable cases. An explicit exclusion is answerable.
- Baseline acceptance requires the completed paid job, all 18 scores and saved human review. Judge scores alone do not prove retrieval isolation or citation support. Account evaluator availability and handling of empty passages remain live verification steps.
- Reports are gitignored under `evaluation_reports/`; retain them privately. No automatic output retention/deletion is configured. Archive required artifacts before disabling resources; a nonempty judge bucket prevents teardown.

## Offline checks

```bash
PYTHONPATH=src:. uv run --locked python -m unittest discover -s tests/unit -q
terraform -chdir=infra/aws/terraform/development validate
terraform -chdir=infra/aws/terraform/development test
```

AWS references: [custom judge configuration](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-evaluation-create-randg-custom.html), [service role](https://docs.aws.amazon.com/bedrock/latest/userguide/judge-service-roles.html), [result artifacts](https://docs.aws.amazon.com/bedrock/latest/userguide/model-evaluation-report-s3.html).
