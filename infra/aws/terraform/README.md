# Phase 1 AWS Terraform

These roots provision the offline foundation described in the [Phase 1 plan](../../../docs/PHASE_1_AWS_POC_PLAN.md).

- `bootstrap` manages the Terraform state bucket.
- `development` manages 13 resources: document storage and its security/versioning settings, S3 Vectors storage/index, Bedrock Knowledge Base/data source, the knowledge-base role/policy, and the ingestion-runner policy.
- Setting `ingestion_runner_role_name` adds one policy attachment to an existing operator role. Otherwise attach the exported policy through your identity system before ingestion.
- RDS checkpoints, custom VPC networking, SQS, ECS roles, ECR and the AgentCore runtime are outside this POC and have been removed from these roots.
- API Gateway, Lambda, verified authentication/owner mapping, and CloudWatch observability remain required implementation work. This offline foundation alone does not complete Phase 1.
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
