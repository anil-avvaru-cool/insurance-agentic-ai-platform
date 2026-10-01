# RAG judge evaluation

## Purpose

Evaluate six insurance API answers with an Amazon Bedrock LLM judge using actual captured retrieval evidence. Measure correctness, faithfulness, and appropriate handling of insufficient information (custom score: 0 = fail, 1 = pass). Four cases should answer; two should acknowledge missing information or decline another owner's question.

## Prerequisites

- Deploy and validate the ingested corpus and query API. Enable `enable_evaluation_capture` and `enable_rag_judge` in development Terraform, configure both supported regional evaluator model IDs, and grant the operator API, capture-read and judge permissions.
- Populate `.env` from [example.env](../../example.env). Copy the `rag_judge_environment` and `evaluation_capture_environment` Terraform outputs; set the query endpoint, deployed ZIP hash, answer model/KB IDs, and all judge pricing, budget and token bounds. Pricing must be dated within 30 days.
- Use a unique dataset S3 key and local report directory for each new run. Commands below run from the repository root. `capture` and `submit` invoke paid services; Terraform does not submit jobs.

## Run steps

1. **Prepare locally:** validate fixtures and estimate costs.

   ```bash
   uv run --locked --env-file .env python scripts/evaluate_rag.py prepare --output evaluation_reports/baseline/prepared.json
   ```

2. **Capture API answers and export:** capture up to six paid requests, then validate exact evidence, isolation and citations before writing JSONL.

   ```bash
   uv run --locked --env-file .env python scripts/evaluate_rag.py capture --prepared evaluation_reports/baseline/prepared.json --output evaluation_reports/baseline/captures.json
   uv run --locked python scripts/evaluate_rag.py export --prepared evaluation_reports/baseline/prepared.json --captures evaluation_reports/baseline/captures.json --output evaluation_reports/baseline/export
   ```

3. **Upload and submit one paid judge job:** evaluates the supplied answers without calling the query API again.

   ```bash
   uv run --locked --env-file .env python scripts/evaluate_rag.py upload --prepared evaluation_reports/baseline/prepared.json --export evaluation_reports/baseline/export --state evaluation_reports/baseline/upload.json
   uv run --locked --env-file .env python scripts/evaluate_rag.py submit --prepared evaluation_reports/baseline/prepared.json --export evaluation_reports/baseline/export --state evaluation_reports/baseline/submission.json
   ```

   If submission has an ambiguous failure, rerun the same `submit` command with the same files to reuse its saved token. Keep the input and state files intact.

4. **Check status and collect:** repeat `status` periodically; run `collect` once status is `Completed`. Inspect failure messages before considering a new job.

   ```bash
   uv run --locked --env-file .env python scripts/evaluate_rag.py status --state evaluation_reports/baseline/submission.json --output evaluation_reports/baseline/status.json
   uv run --locked --env-file .env python scripts/evaluate_rag.py collect --state evaluation_reports/baseline/submission.json --output evaluation_reports/baseline/results
   ```

5. **Review:** inspect `evaluation_reports/baseline/results/report.json` and raw artifacts. Record review notes for each case; compare the separate answerable and abstention summaries. Missing scores remain incomplete. Acceptance requires all 18 scores and human review; complete scores alone do not mean answers passed.

Deployment and a paid baseline remain pending. Verify evaluator access, empty-retrieval handling and result format in the first live run. See the [detailed operator runbook](BEDROCK_RAG_JUDGE_LOCAL.md) for configuration, recovery and offline checks.
