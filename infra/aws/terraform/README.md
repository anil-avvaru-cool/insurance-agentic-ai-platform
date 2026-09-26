# Phase 1 AWS Terraform

These roots define the offline foundation and opt-in query infrastructure described in the [Phase 1 plan](../../../docs/PHASE_1_AWS_POC_PLAN.md).

## Phase 1 POC high-level steps

Follow this deployment order. Development infrastructure is applied in two stages:
the offline foundation first, then the query API after offline validation passes.

| Step | Action | Reference for details |
|---|---|---|
| 1 | **Deploy bootstrap infrastructure.** Create the Terraform state bucket, grant state access, and migrate bootstrap state to S3. | [Bootstrap and plan](#bootstrap-and-plan), including [state access](#grant-state-access-with-the-aws-cli). |
| 2 | **Deploy development offline infrastructure.** Provision document storage, the Bedrock Knowledge Base, vector index, and IAM permissions with `enable_query_api = false`. Attach the ingestion and validation policies to the approved operators. | [Development offline deployment](#development-offline-deployment). |
| 3 | **Ingest offline documents and verify.** Upload validated PDFs and metadata, complete ingestion, and verify retrieval, source references, document replacement, and owner/LOB filtering. Retain the validation reports. | [Offline ingestion runbook](../../../docs/OFFLINE_INGESTION.md) and [indexing validation requirements](../../../docs/PHASE_1_AWS_POC_PLAN.md#4-configure-and-validate-document-indexing). |
| 4 | **Deploy the online query API.** After offline validation passes, attest with `index_validation_passed = true`, build the Lambda ZIP, configure the operator identity, and set `enable_query_api = true`. Review and apply a fresh development plan. | [Phase 1 query deployment](#phase-1-query-deployment). |
| 5 | **Test online RAG queries.** Run question fixtures, review answers and citations, and complete authentication, controlled-failure, and CloudWatch checks. Retain the acceptance evidence. | [Online RAG testing runbook](../../../docs/ONLINE_RAG_TESTING.md), [query acceptance checks](#phase-1-query-deployment), and [completion criteria](../../../docs/PHASE_1_AWS_POC_PLAN.md#completion-criteria). |

These steps describe the workflow; they do not establish deployment or acceptance
status. See [pending work](../../../docs/PHASE_1_PENDING_WORK.md) for remaining
implementation and live verification.

## Infrastructure scope

- `bootstrap` manages the Terraform state bucket.
- `development` defines 22 resources by default: the original 13 offline resources, a validation-runner policy, an ingestion log group, six ingestion/index metric filters, and a dashboard. Enabling the query API adds 24 resources. Each configured operator policy attachment adds one.
- Setting `ingestion_runner_role_name` adds one policy attachment to an existing operator role. Otherwise attach the exported policy through your identity system before ingestion.
- RDS checkpoints, custom VPC networking, SQS, ECS roles, ECR and the AgentCore runtime are outside this POC and have been removed from these roots.
- API Gateway, ZIP Lambda deployment, operator-only IAM authentication, and CloudWatch observability are defined. The query handler and reproducible artifact build are included; ingestion telemetry emission and live acceptance checks remain application work, so infrastructure alone does not complete Phase 1.
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

Follow this order: apply bootstrap to create the state bucket, grant bootstrap
state access, migrate bootstrap state to S3, grant development state access,
then initialize, plan, review and apply development. Development does not need
to be applied before granting state access. The deployment IAM role or user
must already exist; the state-access helper does not create it.

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

- Before migrating, grant the bootstrap deployment identity access to the
  `bootstrap` state key using the [AWS CLI helper below](#grant-state-access-with-the-aws-cli)
  or the account's deployment identity management. If the identity already has
  the required permissions, no additional grant is needed.
- Using the bootstrap deployment identity's credentials, run:

  ```sh
  terraform -chdir=infra/aws/terraform/bootstrap init -migrate-state -backend-config=bootstrap.s3.tfbackend
  ```

- Keep the override and backend config available to each bootstrap operator; future checkouts must configure that remote backend before planning.
- Verify the remote state before securely disposing of local state copies.
- Never recreate bootstrap resources from an empty local state.
- Copy `development/development.s3.tfbackend.example` to `development/development.s3.tfbackend` and fill it in.
- Before initializing the development backend, grant the development deployment
  identity access to the `development` state key using the
  [AWS CLI helper below](#grant-state-access-with-the-aws-cli) or the account's
  deployment identity management. If the identity already has the required
  permissions, no additional grant is needed. Workload roles have no state access.
- Using the development deployment identity's credentials, initialize and plan:

  ```sh
  terraform -chdir=infra/aws/terraform/development init -reconfigure -backend-config=development.s3.tfbackend
  terraform -chdir=infra/aws/terraform/development plan -out=development.tfplan
  terraform -chdir=infra/aws/terraform/development show development.tfplan

  # Save text file for easy review
  terraform -chdir=infra/aws/terraform/development show -no-color development.tfplan > tfout.txt

  # Save image file for easy review dependencies
  terraform -chdir=infra/aws/terraform/development graph | dot -Tpng > tfgraph.png
  ```

- After reviewing the concrete plan, an authorized operator can apply it:

  ```sh
  terraform -chdir=infra/aws/terraform/development apply development.tfplan
  ```

- The backend uses [native S3 locking](https://developer.hashicorp.com/terraform/language/backend/s3).

### Grant state access with the AWS CLI

Use [`scripts/grant_terraform_state_access.sh`](../../../scripts/grant_terraform_state_access.sh)
to add or update an inline policy on an existing deployment IAM role or user.
Before running it:

1. Install and configure the AWS CLI with a profile authorized to perform
   `iam:PutRolePolicy` (for a role) or `iam:PutUserPolicy` (for a user) on the
   target identity. The examples call this profile `admin`; replace it with
   your actual profile name.
2. Set `YOUR_STATE_BUCKET` to the bucket name in your `.s3.tfbackend` file.
   Supply only the name, without `s3://` or an ARN.
3. Identify the existing deployment role or user Terraform will use for backend
   access. Supply its IAM name, not its ARN or an STS session ARN.
4. Run the appropriate command below from the repository directory. Grant
   bootstrap access before migrating bootstrap state, and development access
   before initializing the development backend.

To identify your deployment user or role, run this with the profile Terraform
will use for backend access (replace `YOUR_DEPLOYMENT_PROFILE`):

```sh
aws sts get-caller-identity --profile YOUR_DEPLOYMENT_PROFILE
```

For example, an IAM user might return:

```json
{
  "UserId": "AIDAEXAMPLEUSERID",
  "Account": "123456789012",
  "Arn": "arn:aws:iam::123456789012:user/alice"
}
```

Use the returned `Arn` to choose the helper arguments:

| Example ARN | Helper arguments |
|---|---|
| `arn:aws:iam::123456789012:user/alice` | `development user alice` |
| `arn:aws:sts::123456789012:assumed-role/MyRole/session` | `development role MyRole` |
| Assumed role whose name starts with `AWSReservedSSO_` | Manage access through IAM Identity Center permission sets instead of this helper. |

For example, if your deployment profile uses `alice` and your backend bucket is
`example-terraform-state-123456789012`, grant access with:

```sh
AWS_PROFILE=admin bash scripts/grant_terraform_state_access.sh \
  example-terraform-state-123456789012 development user alice
```

Replace the example bucket and profile with your actual values. Here, `admin`
authorizes the IAM change and `alice` receives state access. `TerraformBootstrap`,
`TerraformDevelopment`, and `YOUR_DEPLOYMENT_USER` below are example names to
replace with existing identities; neither these Terraform roots nor the helper
creates those deployment identities.

The arguments are `BUCKET bootstrap|development role|user IDENTITY_NAME`:

```sh
# Replace the profile, bucket and deployment identity names.
AWS_PROFILE=admin bash scripts/grant_terraform_state_access.sh \
  YOUR_STATE_BUCKET bootstrap role TerraformBootstrap

AWS_PROFILE=admin bash scripts/grant_terraform_state_access.sh \
  YOUR_STATE_BUCKET development role TerraformDevelopment

# Alternatively, grant development state access to an IAM user.
AWS_PROFILE=admin bash scripts/grant_terraform_state_access.sh \
  YOUR_STATE_BUCKET development user YOUR_DEPLOYMENT_USER
```

The profile authorizes the IAM change; the named role or user receives the policy.
The script immediately applies the policy in the credentials' account. Repeating
the same command replaces the same inline policy, named
`TerraformState-<bucket>-<bootstrap|development>`.

| Resource | Granted permissions |
|---|---|
| State bucket | `s3:ListBucket` |
| `<root>/terraform.tfstate` | `s3:GetObject`, `s3:PutObject` |
| `<root>/terraform.tfstate.tflock` | `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` |

Here, `<root>` is `bootstrap` or `development`. An S3 key is an object's name
inside the bucket. The `.tflock` object prevents concurrent Terraform operations
from modifying the same state. Terraform creates it when acquiring the lock
and deletes it when releasing the lock; do not create it yourself.

After the script succeeds, use the deployment identity's credentials to run the
backend initialization and plan commands above. The `admin` profile used to
grant permissions does not automatically select Terraform's deployment identity.

This helper assumes the standard AWS partition, a bucket in the same account,
the `default` Terraform workspace, and the state keys in the backend examples.
It does not grant infrastructure deployment permissions or override explicit
denies. For IAM Identity Center roles, manage access through their permission
sets instead. Bootstrap state access must be granted before remote migration.

## Offline policy ingestion

Knowledge document bucket versioning defaults to `false` for the development POC.
The POC supports this setting: uploads, reads, and ingestion continue normally.
Set `knowledge_bucket_versioning_enabled = true` in development's `terraform.tfvars`
to enable versioning. Setting it to `false` sets the bucket's versioning status to
`Suspended`: the bucket remains usable, but new uploads do not accumulate version
history. New uploads receive a `null` version ID, and another upload to the same
key replaces that `null` version without preserving it for rollback. Versions
previously created while versioning was enabled remain stored; suspending
versioning does not delete them. Run ingestion again after replacing documents
to update the knowledge base.
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

## Development offline deployment

1. Set `enable_query_api = false` in the development `terraform.tfvars`.
   Follow [Bootstrap and plan](#bootstrap-and-plan) to initialize, plan, review,
   and apply the offline infrastructure.
2. Attach the exported ingestion policy to the ingestion operator and the separate validation
   policy to a trusted validation operator. The latter can retrieve all owners'
   documents for isolation testing; never grant it to API users.
3. Follow the [offline ingestion runbook](../../../docs/OFFLINE_INGESTION.md)
   to ingest documents and validate retrieval, source references, document
   replacement, and owner/LOB isolation. Retain the validation reports and keep
   the query API disabled until validation passes.

## Phase 1 query deployment

Complete [development offline deployment](#development-offline-deployment) and
its validation checks before proceeding.

1. Set `index_validation_passed = true` after reviewing the retained offline
   validation reports. This is an operator attestation, not an automated
   verification of those reports. Repeat validation after corpus or indexing changes.
2. Set `query_operator_arn` to your exact IAM user, role, or root ARN in this
   account. Use `aws sts get-caller-identity` to verify the credentials. For an
   assumed role, configure its IAM role ARN, not an STS session ARN. No Cognito
   users or JWT tokens are required. The REST API requires IAM signatures and
   explicitly denies all other principals using `aws:PrincipalArn`; even a root
   ARN is matched as an exact identity, not an account-wide grant.
3. Build the query Lambda ZIP with `scripts/build_query_lambda.sh` (it writes
   `build/lambda/query.zip`) to the contract below. Configure `query_lambda_zip`
   (absolute path recommended), `query_lambda_handler`, and `query_operator_arn`.
   Set `enable_query_api = true`, generate a new saved plan, review, and apply it.
   Terraform hashes the ZIP to detect code changes. No placeholder handler is shipped.
4. Use the [online runner](../../../docs/ONLINE_RAG_TESTING.md) with your existing
   AWS credentials. Each invocation requires `--case-id` and runs exactly one
   fixture. Run separate invocations to cover both synthetic customers and LOBs,
   paired owner questions, and unsupported questions. The runner checks response
   shape, request IDs, citations, expected amounts, and insufficient-information
   behavior; retain its reports and review answer meaning and citation support.
5. Complete the acceptance checks that the online runner does not perform:
   missing/invalid signatures, invalid customer/question/LOB inputs, rejection of
   another AWS principal, a controlled backend failure, and CloudWatch log,
   metric, and dashboard evidence. Confirm gateway rejections do not invoke
   Lambda or Bedrock. Testing another principal requires separate AWS
   credentials; if unavailable, record that acceptance gate as pending. It is
   required for Phase 1 completion. Preserve the offline retrieval and replacement
   reports from offline validation as well; the online runner does not perform those checks.

The REST API has one `POST /query` method at stage `poc`, 2 requests/second with
burst 5, a 29-second integration timeout, and a default 28-second Lambda timeout.
Measure model latency before acceptance. The endpoint remains publicly reachable,
with unauthorized invocation denied at API Gateway. The operator selects either
synthetic customer; customer login authorization is outside this POC's scope.

REST API access logs require a regional API Gateway CloudWatch role. This root
manages `aws_api_gateway_account.query`, its logging role and scoped policy. This
is an account/region-wide setting: inspect `aws apigateway get-account` first;
import/reconcile existing configuration before applying if already managed. The
scoped logging role supports this POC log group; coordinate before sharing the
regional setting with other APIs. Verify actual log delivery after apply.

Migration from an earlier deployed HTTP API replaces the endpoint URL. Update
`RAG_QUERY_ENDPOINT` from the new Terraform output. Remove obsolete `create_cognito`,
`jwt_issuer`, `jwt_audience`, `jwt_scopes`, and `owner_by_subject` tfvars. Review a
fresh plan for old API/Cognito deletions before applying. No state moves are valid
between HTTP and REST API resource types. Keep the API disabled until offline
validation passes; do not set `index_validation_passed` merely to produce a plan.

The RAG answer model is configured with `bedrock_rag_answer_model_id` and exported as
`bedrock.rag_answer_model_id`. Update existing tfvars and `TF_VAR_` overrides to this name.
The query Lambda receives `BEDROCK_RAG_ANSWER_MODEL_ID`; the separate language adapter
continues to use `BEDROCK_MODEL_ID`.
The embedding model is configured with `bedrock_embedding_model_id` in
`terraform.tfvars` (default `amazon.titan-embed-text-v2:0`) and exported as
`bedrock.embedding_model_id`. It supplies the knowledge base model ARN and ingestion
IAM permissions. The selected model must support the configured 1,024-dimensional
float32 vectors.

### Lambda artifact contract

The ZIP must contain the configured Python 3.12 x86_64 handler and dependencies at
its import root. The default is `query.py` exporting `handler(event, context)`.
The packaged `src/apps/query_lambda/query.py` is this handler. The repository's existing FastAPI
and AgentCore applications are not this handler.
The existing Bedrock smoke retrieval helper does not enforce owner/LOB isolation
and must not be used as the production query authorization path.

Handle REST API Lambda proxy payloads. Read the verified IAM identity from
`requestContext.identity.userArn` and compare it to `QUERY_OPERATOR_ARN` (including
STS sessions for the approved role). The gateway resource policy is the primary
access boundary. Validate `question`, supported `lob`, and a body `owner_id` of
exactly `customer_one` or `customer_two`; apply both customer and LOB filters to
every retrieval. The customer selection is test input, not a user identity.
Return answer, citations, and request ID; return insufficient information when
retrieved evidence does not support an answer.

Terraform supplies `BEDROCK_KNOWLEDGE_BASE_ID`, `BEDROCK_RAG_ANSWER_MODEL_ID`,
`QUERY_OPERATOR_ARN`, `KNOWLEDGE_RESULT_COUNT`, `MODEL_MAX_TOKENS`, `MODEL_TEMPERATURE`, and
`QUERY_DEADLINE_SECONDS`. Lambda supplies `AWS_REGION`. Enforce the overall deadline
across retrieval, generation and SDK retries; the existing 120-second smoke-client
read timeout is unsuitable. Terraform's timeout and token settings do not enforce
these application behaviors. The operator ARN is deployment configuration stored
in state, not a secret; do not include credentials.

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
| `event: authorization_failed` | Lambda rejected a missing or unapproved AWS identity. |
| `request_id` | API request ID on every query event for correlation. |

API access-log filters count 401/403 responses, including pre-Lambda rejections.
Native API/Lambda metrics supply request counts, errors, latency and throttles.
The dashboard includes these and custom metrics. Missing custom metrics mean no
matching events have arrived, not proof of zero failures. Alarms remain out of scope.
