# Local Bedrock judge preparation

- No deployed resources or AWS credentials are required by these commands. No inference, upload, or job submission occurs.
- Set all `JUDGE_*` inputs in `.env` using [example.env](../../example.env). Use current, operator-reviewed rates and a positive USD budget. Pricing must be at most 30 days old.
- Token bounds must cover the six initial requests and both judge metrics, including judge prompt overhead, context and reference answers. Include supporting AWS costs and a safety multiplier of at least one. Estimates are gates, not AWS billing caps.
- Placeholder deployment IDs and ARNs can be used for local preparation only; SDK validation does not establish account permissions, model availability or actual deployment identity.

```bash
uv run --locked --env-file .env python scripts/evaluate_rag.py prepare --output evaluation_reports/baseline/prepared.json
uv run --locked python scripts/evaluate_rag.py reserve --prepared evaluation_reports/baseline/prepared.json --ledger evaluation_reports/budget.sqlite3
uv run --locked python scripts/evaluate_rag.py export --prepared evaluation_reports/baseline/prepared.json --captures evaluation_reports/baseline/captures.json --output evaluation_reports/baseline/export
PYTHONPATH=src:. uv run --locked python -m unittest discover -s tests/unit -q
```

- `prepare` verifies all fixtures/PDFs, records corpus/fixture hashes, estimates costs, and stores an SDK-validated `CreateEvaluationJob` request with a stable idempotency token. It does not reserve money.
- `reserve` atomically reserves the estimate. All concurrent local runs must share the same ledger and total budget. Duplicate IDs fail. Reservations persist indefinitely; unresolved costs cannot be reused. No automatic release or cost settlement is implemented. This ledger does not coordinate different machines.
- `export` accepts a report containing exactly the six baseline results in any order. Each result must contain a successful HTTP response, its capture descriptor hash, and `evaluation_evidence` in the existing query Lambda capture schema. Top-level `fixture_sha256` and `corpus_sha256` must match `prepared.json`. These hashes bind local inputs; deployed corpus equivalence still requires ingestion verification.
- Existing opt-in online capture reports now record both hashes. A future budget-gated six-request capture command must assemble the report. Do not use repeated one-case commands as a replacement for that runner.
- Export checks capture timestamps and configured deployment/model/KB IDs, context limits/fidelity, filters, document isolation, exact citation references, and complete usage. It rejects failed, stale, duplicate or incomplete samples.
- Empty actual retrieval remains empty. `manifest.json` flags the need to verify Bedrock handling before paid submission. Fixture passages never replace retrieved evidence.
- `dataset.jsonl` follows the [AWS precomputed retrieve-and-generate schema](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-evaluation-prompt-retrieve-generate.html). `manifest.json` associates rows by SHA-256 and request/case IDs and provides six human-review records. Scores and reviews remain pending.
- Reports and budget ledgers are gitignored. Keep them in a private operator workspace; retain the shared ledger across runs.

Still pending: deployed ingestion/capture verification, scoped evaluation IAM/Terraform, budget-gated six-request capture, upload/submission/reconciliation/status/stop/collection, actual cost settlement, evaluator availability and empty-retrieval service checks, and paid baseline/human review. Do not submit the prepared request directly to bypass these gates.
