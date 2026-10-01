# Online RAG evaluation

Run [test_online_rag.py](../../scripts/test_online_rag.py) against the deployed Phase 1 HTTPS `/poc/query` endpoint. This exercises API Gateway IAM authentication, the query Lambda, Bedrock Knowledge Base retrieval, and answer generation. Requests invoke paid AWS services. It does not upload or change policies.

Prerequisites: the corpus has been ingested and validated, the query API is deployed, and your local AWS credentials identify the configured `query_operator_arn`. No Cognito users, passwords, or JWT tokens are needed. The API resource policy explicitly denies invocation by every other principal, including other identities in the same AWS account. The endpoint is publicly reachable; unauthorized requests are rejected before Lambda. Account administrators who can change these controls can change access.

Configure `query_operator_arn` in Terraform using the IAM user or role ARN you intend to use. `aws sts get-caller-identity` shows your current identity. For assumed-role credentials, configure the IAM role ARN (including its path), not the STS session ARN. A role grants access to everyone allowed to assume it. An exact root ARN in the policy's `aws:PrincipalArn` condition permits only that root identity, not the entire account. AWS credentials remain outside Terraform.

Use the Terraform `query_endpoint` output for the full URL. Set this in your gitignored `.env`:

```dotenv
RAG_QUERY_ENDPOINT=https://YOUR_API.execute-api.YOUR_REGION.amazonaws.com/poc/query
AWS_DEFAULT_REGION=us-east-1
# Optional, when using a named local AWS profile:
# AWS_PROFILE=your-profile
```

From the repository root:

```sh
uv run --locked --env-file .env python scripts/test_online_rag.py --case-id auto_user_1_v2_comprehensive_deductible
# Alternatively, select an existing profile explicitly:
uv run --locked --env-file .env python scripts/test_online_rag.py --case-id auto_user_1_v2_comprehensive_deductible --profile your-profile --region us-east-1
```

The runner uses boto3's credential chain and signs each request with AWS Signature Version 4 for `execute-api`, including session tokens when applicable. It obtains current credentials for each signed request. The operator must have permission to invoke the configured API. Requests explicitly select one synthetic customer:

```json
{"question":"What is my collision deductible?","lob":"auto","owner_id":"customer_one"}
```

Only `customer_one` and `customer_two` are accepted. The handler applies customer and LOB filters to every retrieval. This validates synthetic customer document filtering, **not customer identity isolation**: the approved operator can select either customer.

The runner requires `--case-id` and executes exactly one matching question from `tests/fixtures/aws_poc/questions.json` (or `--fixtures PATH`). Omitted, unknown, or duplicate matching IDs fail before AWS credential lookup or API requests. There is no run-all mode, and authentication-negative and invalid-input checks are not appended. Choose another case ID to test another question in a separate invocation. It checks response shape, request IDs, allowed citation documents, citation LOB/source/evidence IDs, expected monetary amounts, and the controlled insufficient-information response. A live check with a different valid AWS principal requires separate credentials and is explicitly recorded as not run. With such credentials, a signed request must return 403 with no Lambda/Bedrock execution; verify this with gateway and Lambda logs.

Reports are written to gitignored `online_rag_reports/<unique-id>.json`; use `--report PATH` to select another location. Credentials and signing authorization values are redacted. The report contains synthetic answers, expected answers, supporting passages, errors and request IDs. Exit code 1 means an automated check failed; 0 means the automated checks passed, **not full Phase 1 acceptance**. Each invocation sends one request without retries, so throttling and service failures remain visible.

Review each answer against the expected answer and supporting passages, including negation, limits, exclusions, and whether each citation actually supports the answer. Monetary matching alone is not semantic evaluation. Use request IDs to verify CloudWatch events separately. Replacement checks, injected backend failures and CloudWatch verification are outside this runner.

Follow [CloudWatch RAG evaluation metrics](CLOUDWATCH_RAG_EVAL_METRICS.md) to correlate
request IDs with API/Lambda logs, inspect metrics, and retain telemetry evidence.

For a direct Knowledge Base retrieval diagnostic without deploying the API, `scripts/bedrock_smoke.py retrieve --text "..."` remains available; it does not validate customer/LOB isolation or the authenticated online path.

## Exact evidence capture for judge evaluation

Implemented prerequisites; AWS deployment and live capture verification remain pending.

1. Validate the current corpus and the six-case manifest without AWS calls:

   ```sh
   uv run --locked python scripts/validate_judge_baseline.py
   ```

   This checks all 36 fixtures against the current PDF passages/metadata and prints
   corpus, fixture, and manifest hashes. User 1 Auto is v2 with a $750 collision
   deductible. The six baseline IDs are in `tests/fixtures/aws_poc/judge_baseline.json`.

2. Build the Lambda ZIP using `scripts/build_query_lambda.sh`. In development
   Terraform, set `enable_evaluation_capture = true` alongside the existing query
   API configuration, review the plan, and deploy. Terraform defines a separate
   private encrypted capture bucket, 30-day capture retention, Lambda write-only
   access to `captures/`, and read access for the configured query operator.
   Capture is disabled by default. The bucket is outside the KB ingestion source.

3. Copy `QUERY_CAPTURE_BUCKET` and `QUERY_CAPTURE_PREFIX` from the
   `evaluation_capture_environment` Terraform output into `.env`. Run one explicit
   capture using the existing paid online diagnostic command:

   ```sh
   uv run --locked --env-file .env python scripts/test_online_rag.py --case-id auto_user_1_v2_collision_deductible --capture-evidence
   ```

   The signed request includes `capture_evidence: true`. The runner downloads the
   artifact from the configured bucket/prefix, verifies its hash and request/answer
   association, checks captured document ownership, and embeds it as
   `evaluation_evidence` in the local report. A missing or invalid capture fails
   the check. Ordinary requests retain the original response shape and do not
   write capture artifacts.

Captures contain original retrieval results, exact generation evidence, evidence
IDs, final API answer/citations, selected owner/LOB, filters, model settings, token
usage when available, request ID, and deployment ZIP hash. Full evidence stays out
of CloudWatch logs. The handler rejects missing/mismatched ownership metadata,
more than the configured result count, oversized passages/context, and answers
that hit the output token limit. Limits are configured through
`query_max_passage_chars` (6,000), `query_max_context_chars` (24,000), and
`query_max_tokens` (512); evidence is not silently truncated. Capture write failures
return HTTP 503 with `capture_failed`; the request is not retried automatically.

Retain local reports before the configured S3 retention expires. Disabling capture
plans removal of the capture resources; the bucket cannot be destroyed while
nonempty. Archive required evidence and explicitly empty only this dedicated
bucket before teardown, or retain the resources and stop requesting captures.

This single-case diagnostic does not submit a judge job or implement its budget
ledger. The six-case capture, validated JSONL export, evaluator permissions, submission,
and result summary are implemented in the [judge operator runbook](BEDROCK_RAG_JUDGE_LOCAL.md).
Deployment and the paid baseline remain pending. Single-case diagnostic captures
do not constitute completion of the Phase 1 judge baseline.
