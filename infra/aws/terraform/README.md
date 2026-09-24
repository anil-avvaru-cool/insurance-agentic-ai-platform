# Phase 1 AWS Terraform

These roots define the offline foundation and opt-in query infrastructure described in the [Phase 1 plan](../../../docs/PHASE_1_AWS_POC_PLAN.md).

- `bootstrap` manages the Terraform state bucket.
- `development` defines 22 resources by default: the original 13 offline resources, a validation-runner policy, an ingestion log group, six ingestion/index metric filters, and a dashboard. Enabling the query API adds 19 resources; optional Cognito adds two. Each configured operator policy attachment adds one.
- Setting `ingestion_runner_role_name` adds one policy attachment to an existing operator role. Otherwise attach the exported policy through your identity system before ingestion.
- RDS checkpoints, custom VPC networking, SQS, ECS roles, ECR and the AgentCore runtime are outside this POC and have been removed from these roots.
- API Gateway, ZIP Lambda deployment, JWT authentication configuration, optional Cognito, and CloudWatch observability are defined. The query handler and reproducible artifact build are included; ingestion telemetry emission and live acceptance checks remain application work, so infrastructure alone does not complete Phase 1.
- Configuration is explicit in ignored `terraform.tfvars` and backend files copied from the examples. Terraform does not load the application `.env`.
- Use AWS environment credentials or a deployment profile. Do not put application tokens or database passwords in Terraform.

The previous 39-resource development plan is obsolete. Generate and review a fresh plan before applying. If an older configuration was already deployed, inspect its state and any proposed deletions separately; this repository cleanup does not migrate or delete deployed infrastructure.

## Validate without an AWS account

- Use Terraform 1.10 or later (below 2.0).
- AWS provider 6.27.0 is pinned with committed checksums in each root.
- From the repository directory:

  ```sh
  terraform fmt -check -recursive infra/aws/terraform
  terraform -chdir=infra/aws/terraform/bootstrap init -backend=false
  terraform -chdir=infra/aws/terraform/bootstrap validate
  terraform -chdir=infra/aws/terraform/bootstrap test
  terraform -chdir=infra/aws/terraform/development init -backend=false
  terraform -chdir=infra/aws/terraform/development validate
  terraform -chdir=infra/aws/terraform/development test
  ```

- Tests use a mocked AWS provider and plan only.
- They establish configuration invariants, not AWS availability, permissions, routing, failover or connectivity.
- To see the resources Terraform would create, change or destroy in your AWS account, configure real credentials, variables and state as described below, then run the corresponding `terraform plan` command.
- `terraform test` does not show that account-specific plan.

## Bootstrap and plan

- Before deployment, record the account, region, owner, deployment identity and state bucket owner.
- Use a dedicated development AWS identity.
- Both providers restrict the target account; also configure the backend account restriction.
- Copy each `terraform.tfvars.example` to `terraform.tfvars` in its own directory and replace the account and backend placeholders.
- Examples are not deployable.
- The bootstrap root initially uses local state.
- Keep that state protected until migration.
- Preview the real resource changes before applying:

  ```sh
  terraform -chdir=infra/aws/terraform/bootstrap init
  terraform -chdir=infra/aws/terraform/bootstrap plan -out=bootstrap.tfplan
  terraform -chdir=infra/aws/terraform/bootstrap show bootstrap.tfplan
  ```

- After reviewing the plan, an authorized operator can apply it:

  ```sh
  terraform -chdir=infra/aws/terraform/bootstrap apply bootstrap.tfplan
  ```

- Move bootstrap state into the created bucket: add an ignored `remote_override.tf` file in the bootstrap root containing:

  ```hcl
  terraform {
    backend "s3" {}
  }
  ```

- Also create an ignored `bootstrap.s3.tfbackend` similar to following and replace correct values.
  ```sh
  bucket = "xxx"
  key = "bootstrap/terraform.tfstate"
  encrypt = true
  use_lockfile = true
  region = "us-east-1"
  allowed_account_ids = ["123"]
  ```

- Run:

  ```sh
  terraform -chdir=infra/aws/terraform/bootstrap init -migrate-state -backend-config=bootstrap.s3.tfbackend
  ```

- Keep the override and backend config available to each bootstrap operator; future checkouts must configure that remote backend before planning.
- Verify the remote state before securely disposing of local state copies.
- Never recreate bootstrap resources from an empty local state.
- Copy `development/development.s3.tfbackend.example` to `development/development.s3.tfbackend`, fill it in, then:

  ```sh
  terraform -chdir=infra/aws/terraform/development init -reconfigure -backend-config=development.s3.tfbackend
  terraform -chdir=infra/aws/terraform/development plan -out=development.tfplan
  terraform -chdir=infra/aws/terraform/development show development.tfplan

  # Save text file for easy review
  terraform -chdir=infra/aws/terraform/development show -no-color development.tfplan > tfout.txt

  # Save image file for easy review dependencies
  terraform -chdir=infra/aws/terraform/development graph | dot -Tpng > tfgraph.png
  ```

- Review the concrete plan before an authorized apply.
- State identities need `s3:ListBucket` on the bucket, `s3:GetObject`/`s3:PutObject` on their state key, and `s3:GetObject`/`s3:PutObject`/`s3:DeleteObject` on its `.tflock` key.
- Grant these through the account's deployment identity management, scoped separately for bootstrap and development; workload roles have no state access.
- The backend uses [native S3 locking](https://developer.hashicorp.com/terraform/language/backend/s3).

## Offline policy ingestion

Knowledge document bucket versioning defaults to off for the development POC.
Set `knowledge_bucket_versioning_enabled = true` in development's `terraform.tfvars`
to enable it. False sets the S3 status to `Suspended`, which also supports buckets
that previously had versioning enabled; existing versions are retained.
Bootstrap state bucket versioning remains enabled.

The [Step 3 runbook](../../../docs/OFFLINE_INGESTION.md) documents the repeatable CLI,
POC parameters, IAM attachment, stable inventory and failure recovery. The
`ingestion_environment` output supplies all six ingestion settings automatically.
The POC prefix defaults to `approved/aws_poc/`; the data-source deletion policy is
`DELETE`. Review the runbook migration note before changing an already-used source.

## Teardown

Stop ingestion and query callers before preparing a destroy plan. Review the plan
and any retained data before applying it:

```sh
terraform -chdir=infra/aws/terraform/development plan -destroy -out=teardown.tfplan
terraform -chdir=infra/aws/terraform/development show teardown.tfplan
```

Document and vector buckets use `force_destroy = false`. Nonempty buckets may
prevent destruction; explicitly review and authorize removal of documents,
object versions, and vector data before emptying them. The old RDS/SQS teardown
helper does not apply to this foundation and has been removed.

Keep bootstrap and its state bucket until development and any older deployments
using it have been removed. If bootstrap state is stored in that bucket, migrate
it back to local state before planning bootstrap destruction. The bootstrap
bucket uses `force_destroy = true`; destroying it deletes state history as well.

## Phase 1 query deployment

1. Deploy the offline configuration with `enable_query_api = false`. Attach the
   exported ingestion policy to the ingestion operator and the separate validation
   policy to a trusted validation operator. The latter can retrieve all owners'
   documents for isolation testing; never grant it to API users.
2. Use an existing HTTPS JWT issuer with access-token scopes, or set
   `create_cognito = true` and deploy the pool/client while the API remains disabled.
   Cognito uses SRP sign-in (`USER_SRP_AUTH`) and refresh tokens, without a hosted UI
   or client secret. Provision the two synthetic users and set their passwords
   through the identity provider outside Terraform. Read each immutable `sub`;
   put these in `owner_by_subject`, mapped to `customer_one` and `customer_two`.
   Cognito access tokens include `aws.cognito.signin.user.admin`; the route requires
   this scope to exclude ID tokens. For another provider supply `jwt_issuer`,
   `jwt_audience`, and `jwt_scopes` matching that provider's access tokens.
3. Run ingestion and retrieval/source/replacement/owner-and-LOB isolation checks.
   Retain their reports, then set `index_validation_passed = true`. This is an
   operator attestation, not an automated verification of those reports. Repeat
   validation after corpus or indexing changes.
4. Build the query Lambda ZIP with `scripts/build_query_lambda.sh` (it writes
   `build/lambda/query.zip`) to the contract below. Configure `query_lambda_zip`
   (absolute path recommended), `query_lambda_handler`, and the two subject mappings.
   Set `enable_query_api = true`, generate a new saved plan, review, and apply it.
   Terraform hashes the ZIP to detect code changes. No placeholder handler is shipped.
5. Use `query_endpoint` with a bearer access token for deployed tests. Check both
   owners and LOBs, unmapped subjects, invalid/missing tokens, unsupported questions,
   caller-supplied owner IDs, citations, and a controlled failure. Review
   `observability` destinations and confirm telemetry actually arrives.

The API has one `POST /query` route, 2 requests/second with burst 5, a 30-second
integration timeout, and a default 28-second Lambda timeout. These are POC defaults;
measure model latency before acceptance. HTTP API log delivery also requires the
**deployment identity** to have the logging setup permissions documented by
[AWS](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-logging.html),
including Create/Update/Delete/Get/ListLogDelivery and Describe/PutResourcePolicy.
The root supplies a destination-scoped delivery resource policy; it does not manage
or broaden the external deployment identity. Verify actual delivery after apply.
JWT route scopes follow the [AWS authorizer contract](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html).

The RAG answer model is configured with `bedrock_rag_model_id` and exported as
`bedrock.rag_model_id`. Update existing tfvars and `TF_VAR_` overrides to this name.
The query Lambda receives `BEDROCK_RAG_MODEL_ID`; the separate language adapter
continues to use `BEDROCK_MODEL_ID`. Embedding model configuration is separate.

### Lambda artifact contract

The ZIP must contain the configured Python 3.12 x86_64 handler and dependencies at
its import root. The default is `query.py` exporting `handler(event, context)`.
The packaged `src/apps/query_lambda/query.py` is this handler. The repository's existing FastAPI
and AgentCore applications are not this handler.
The existing Bedrock smoke retrieval helper does not enforce owner/LOB isolation
and must not be used as the production query authorization path.

Handle HTTP API payload v2. Read verified `iss` and `sub` exclusively from
`requestContext.authorizer.jwt.claims`; compare `iss` with `JWT_ISSUER` and look up
`sub` in `OWNER_BY_SUBJECT_JSON`. Reject missing/unmapped identities before any
retrieval. Validate the question and supported LOB; apply both `owner_id` and `lob`
filters to every retrieval. Never use a body/header owner ID for authorization.
Return answer, citations, and request ID; return insufficient information when
retrieved evidence does not support an answer.

Terraform supplies `BEDROCK_KNOWLEDGE_BASE_ID`, `BEDROCK_RAG_MODEL_ID`,
`KNOWLEDGE_RESULT_COUNT`, `MODEL_MAX_TOKENS`, `MODEL_TEMPERATURE`, and
`QUERY_DEADLINE_SECONDS`. Lambda supplies `AWS_REGION`. Enforce the overall deadline
across retrieval, generation and SDK retries; the existing 120-second smoke-client
read timeout is unsuitable. Terraform's timeout and token settings do not enforce
these application behaviors. Subject mappings are deployment configuration stored
in state, not secrets; do not include credentials.

### Telemetry contract

Custom metrics use log-derived filters only; do not also publish those metrics
with PutMetricData. Log retention defaults to 14 days. The `observability` output
identifies destinations. The current ingestion CLI still writes local reports;
it needs a CloudWatch log publisher to satisfy this contract. Query telemetry must
be implemented in the query handler. Neither log groups nor filters create events.

Publish one JSON object per log event. Ingestion and validation operators may
CreateLogStream/PutLogEvents only in the ingestion group. Lambda writes JSON to
stdout in its standard text logging mode. Record request IDs and job IDs in logs,
not metric dimensions; omit questions, policy text, tokens and credentials.

| Event/field | Meaning |
|---|---|
| `event: ingestion_completed` or `ingestion_failed` | Emit exactly one terminal event per CLI run, including validation/upload/job/document failure or timeout. |
| `duration_seconds`, `documents_processed`, `documents_failed` | Numeric final run values; include available job ID, status and sanitized failure reason as log-only fields. |
| `event: index_validation_failed` | Failed retrieval, source, replacement or isolation check; record sanitized failure type. Log successful checks too. |
| `retrieval_count` | Numeric total retrieved evidence count once per query. |
| `has_citations`, `insufficient_information` | JSON booleans on the final query event. |
| `input_tokens`, `output_tokens` | Numeric model usage when available, once per query. |
| `event: authorization_failed` | Lambda rejected a missing/unmapped identity. |
| `request_id` | API request ID on every query event for correlation. |

API access-log filters count 401/403 responses, including pre-Lambda rejections.
Native API/Lambda metrics supply request counts, errors, latency and throttles.
The dashboard includes these and custom metrics. Missing custom metrics mean no
matching events have arrived, not proof of zero failures. Alarms remain out of scope.
