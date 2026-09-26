# Live online RAG testing

Run [test_online_rag.py](../scripts/test_online_rag.py) against the deployed Phase 1 HTTPS `/poc/query` endpoint. This exercises API Gateway IAM authentication, the query Lambda, Bedrock Knowledge Base retrieval, and answer generation. Requests invoke paid AWS services. It does not upload or change policies.

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
uv run --locked --env-file .env python scripts/test_online_rag.py --case-id auto_user_1_v1_comprehensive_deductible
# Alternatively, select an existing profile explicitly:
uv run --locked --env-file .env python scripts/test_online_rag.py --case-id auto_user_1_v1_comprehensive_deductible --profile your-profile --region us-east-1
```

The runner uses boto3's credential chain and signs each request with AWS Signature Version 4 for `execute-api`, including session tokens when applicable. It obtains current credentials for each signed request. The operator must have permission to invoke the configured API. Requests explicitly select one synthetic customer:

```json
{"question":"What is my collision deductible?","lob":"auto","owner_id":"customer_one"}
```

Only `customer_one` and `customer_two` are accepted. The handler applies customer and LOB filters to every retrieval. This validates synthetic customer document filtering, **not customer identity isolation**: the approved operator can select either customer.

The runner requires `--case-id` and executes exactly one matching question from `tests/fixtures/aws_poc/questions.json` (or `--fixtures PATH`). Omitted, unknown, or duplicate matching IDs fail before AWS credential lookup or API requests. There is no run-all mode, and authentication-negative and invalid-input checks are not appended. Choose another case ID to test another question in a separate invocation. It checks response shape, request IDs, allowed citation documents, citation LOB/source/evidence IDs, expected monetary amounts, and the controlled insufficient-information response. A live check with a different valid AWS principal requires separate credentials and is explicitly recorded as not run. With such credentials, a signed request must return 403 with no Lambda/Bedrock execution; verify this with gateway and Lambda logs.

Reports are written to gitignored `online_rag_reports/<unique-id>.json`; use `--report PATH` to select another location. Credentials and signing authorization values are redacted. The report contains synthetic answers, expected answers, supporting passages, errors and request IDs. Exit code 1 means an automated check failed; 0 means the automated checks passed, **not full Phase 1 acceptance**. Each invocation sends one request without retries, so throttling and service failures remain visible.

Review each answer against the expected answer and supporting passages, including negation, limits, exclusions, and whether each citation actually supports the answer. Monetary matching alone is not semantic evaluation. Use request IDs to verify CloudWatch events separately. Replacement checks, injected backend failures and CloudWatch verification are outside this runner.

For a direct Knowledge Base retrieval diagnostic without deploying the API, `scripts/bedrock_smoke.py retrieve --text "..."` remains available; it does not validate customer/LOB isolation or the authenticated online path.
