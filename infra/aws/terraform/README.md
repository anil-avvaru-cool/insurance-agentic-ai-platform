# Phase 1B Terraform foundation

These roots provision development prerequisites only: an encrypted, versioned,
private S3 state bucket with TLS enforcement; private encrypted PostgreSQL RDS;
SQS with a restricted DLQ; and separate ECS API, worker and action service roles.
Optional Bedrock resources now add S3 document/vector storage, a knowledge base,
ECR and an AgentCore smoke runtime. See the [deployment guide](../../docs/BEDROCK_DEVELOPMENT.md)
for image publishing, tfvars and model scripts. The application still uses SQLite
for business state; application migration and ECS/API deployment remain open.

Configuration is explicit in ignored `terraform.tfvars` and backend files copied
from the examples. Terraform does not automatically load the application `.env`;
use AWS environment credentials or an AWS profile for the deployment identity.
Never copy application tokens, model keys or database passwords into Terraform.
All resource labels use underscores; AWS names that forbid underscores (S3/RDS)
use lowercase alphanumeric names. AWS region identifiers retain AWS syntax.

## Validate without an AWS account

Use Terraform 1.10 or later (below 2.0). AWS provider 6.27.0 is pinned with committed
checksums in each root. From the repository directory:

```sh
terraform fmt -check -recursive infra/aws/terraform
terraform -chdir=infra/aws/terraform/bootstrap init -backend=false
terraform -chdir=infra/aws/terraform/bootstrap validate
terraform -chdir=infra/aws/terraform/bootstrap test
terraform -chdir=infra/aws/terraform/development init -backend=false
terraform -chdir=infra/aws/terraform/development validate
terraform -chdir=infra/aws/terraform/development test
```

Tests use a mocked AWS provider and plan only. They establish configuration
invariants, not AWS availability, permissions, routing, failover or connectivity.
To see the resources Terraform would create, change or destroy in your AWS
account, configure real credentials, variables and state as described below,
then run the corresponding `terraform plan` command. `terraform test` does not
show that account-specific plan.

## Bootstrap and plan

Before deployment, record the account, region, owner, deployment identity and
state bucket owner. Use a dedicated development AWS identity. Both providers
restrict the target account; also configure the backend account restriction.
Copy each `terraform.tfvars.example` to `terraform.tfvars` in its own directory
and replace the account and backend placeholders. Select an available PostgreSQL engine version and
matching parameter family in the chosen region. Examples are not deployable.

The bootstrap root initially uses local state. Keep that state protected until
migration. Preview the real resource changes before applying:

```sh
terraform -chdir=infra/aws/terraform/bootstrap init
terraform -chdir=infra/aws/terraform/bootstrap plan -out=bootstrap.tfplan
terraform -chdir=infra/aws/terraform/bootstrap show bootstrap.tfplan
```

After reviewing the plan, an authorized operator can apply it:

```sh
terraform -chdir=infra/aws/terraform/bootstrap apply bootstrap.tfplan
```

Move bootstrap state into the created bucket: add an ignored `remote_override.tf`
file in the bootstrap root containing:

```hcl
terraform {
  backend "s3" {}
}
```

Also create an ignored `bootstrap.s3.tfbackend` with bucket, region, allowed_account_ids,
`key = "bootstrap/terraform.tfstate"`, `encrypt = true`, and
`use_lockfile = true`. Run:

```sh
terraform -chdir=infra/aws/terraform/bootstrap init -migrate-state -backend-config=bootstrap.s3.tfbackend
```

Keep the override and backend config available to each bootstrap operator;
future checkouts must configure that remote backend before planning. Verify the
remote state before securely disposing of local state copies. Never recreate
bootstrap resources from an empty local state.

Copy `development/development.s3.tfbackend.example` to
`development/development.s3.tfbackend`, fill it in, then:

```sh
terraform -chdir=infra/aws/terraform/development init -reconfigure -backend-config=development.s3.tfbackend
terraform -chdir=infra/aws/terraform/development plan -out=development.tfplan
terraform -chdir=infra/aws/terraform/development show development.tfplan
```

Review the concrete plan before an authorized apply. State identities need
`s3:ListBucket` on the bucket, `s3:GetObject`/`s3:PutObject` on their state key,
and `s3:GetObject`/`s3:PutObject`/`s3:DeleteObject` on its `.tflock` key. Grant
these through the account's deployment identity management, scoped separately
for bootstrap and development; workload roles have no state access. The backend
uses [native S3 locking](https://developer.hashicorp.com/terraform/language/backend/s3).

## Network and runtime handoff

The development root creates a VPC (`10.42.0.0/16`) with DNS enabled and two
private `/24` subnets in separate available AZs. Both subnets use an explicit
route table containing only the local VPC route; no public IP assignment,
internet gateway, NAT gateway, or VPC endpoints are configured. Outputs expose
the resulting VPC and subnet IDs. Before deploying workloads in these subnets,
add an approved outbound HTTPS path and private access to required AWS services.
The current AgentCore smoke runtime uses public network mode, not these subnets.

Attach the output checkpoint client security group only to authorized database
clients and migration tasks. It permits TCP 5432 to the database group only;
workload HTTPS/service egress needs a separately reviewed group. RDS requires
TLS; clients should use `sslmode=verify-full` and the current RDS CA bundle.
The database is single-AZ development infrastructure, with seven-day backups
and final snapshots; it does not establish production availability.

RDS manages the administrator secret in Secrets Manager; Terraform exposes its
ARN, never retrieves its value. A separately authorized migration operator must
retrieve it, run checkpoint schema setup from the spike runbook, and provision a
restricted runtime database user and secret. No workload has administrator-secret
access. Database grants, secret delivery and runtime identities are not yet wired.
See [RDS provider arguments](https://registry.terraform.io/providers/hashicorp/aws/6.27.0/docs/resources/db_instance).

The API role can only send to the task queue; the worker can receive, delete,
change visibility and read queue attributes. The action service role has no
permissions until its core sandbox contract is approved. ECS container execution
roles remain later work; the optional AgentCore identity is defined separately. SQS has a five-receive DLQ threshold,
300-second visibility and long polling. The future worker must extend visibility,
retain idempotency, implement retries and establish a staffed DLQ recovery path.
These queue settings do not implement a distributed outbox or worker.

## Teardown

Stop producers/workers and reconcile tasks before teardown. Record a unique final
snapshot identifier. Set `db_deletion_protection = false`, review and apply that
change, then review `terraform plan -destroy -out=teardown.tfplan` in development
before an authorized apply. RDS retains a final snapshot; account for snapshots,
automated backups and retained secrets when reviewing residual costs. Queue
deletion loses messages, so export or reconcile pending work first.

For a POC, the state bucket can be removed after development is destroyed. The
bootstrap bucket uses `force_destroy = true`, so destroying it deletes all object
versions, including old state files. Download any state history you need before
teardown, and confirm no other Terraform root uses the bucket.

If bootstrap state was migrated into this bucket, move it back to local state
before destroying the bucket. Remove the ignored `bootstrap/remote_override.tf`
file, then run `terraform -chdir=infra/aws/terraform/bootstrap init -migrate-state`
and accept the state migration prompt. Confirm the local bootstrap state contains
the bucket before continuing. Keep that local state file until the destroy is
complete. Then review and apply a bootstrap destroy plan:

```sh
terraform -chdir=infra/aws/terraform/bootstrap plan -destroy -out=bootstrap_destroy.tfplan
terraform -chdir=infra/aws/terraform/bootstrap apply bootstrap_destroy.tfplan
```

Do not start bootstrap from empty local state: Terraform would lose track of the
bucket. A failed development destroy may leave resources behind, so check its
result before deleting the state bucket.
