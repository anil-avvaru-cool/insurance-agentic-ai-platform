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
terraform fmt -check -recursive infra/terraform
terraform -chdir=infra/terraform/bootstrap init -backend=false
terraform -chdir=infra/terraform/bootstrap validate
terraform -chdir=infra/terraform/bootstrap test
terraform -chdir=infra/terraform/development init -backend=false
terraform -chdir=infra/terraform/development validate
terraform -chdir=infra/terraform/development test
```

Tests use a mocked AWS provider and plan only. They establish configuration
invariants, not AWS availability, permissions, routing, failover or connectivity.

## Bootstrap and plan

Before deployment, record the account, region, owner, deployment identity and
state bucket owner. Use a dedicated development AWS identity. Both providers
restrict the target account; also configure the backend account restriction.
Copy each `terraform.tfvars.example` to `terraform.tfvars` in its own directory
and replace every placeholder. Select an available PostgreSQL engine version and
matching parameter family in the chosen region. Examples are not deployable.

The bootstrap root initially uses local state. Keep that state protected until
migration. After reviewing its plan, an authorized operator can apply it:

```sh
terraform -chdir=infra/terraform/bootstrap init
terraform -chdir=infra/terraform/bootstrap plan -out=bootstrap.tfplan
terraform -chdir=infra/terraform/bootstrap apply bootstrap.tfplan
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
terraform -chdir=infra/terraform/bootstrap init -migrate-state -backend-config=bootstrap.s3.tfbackend
```

Keep the override and backend config available to each bootstrap operator;
future checkouts must configure that remote backend before planning. Verify the
remote state before securely disposing of local state copies. Never recreate
bootstrap resources from an empty local state.

Copy `development/development.s3.tfbackend.example` to
`development/development.s3.tfbackend`, fill it in, then:

```sh
terraform -chdir=infra/terraform/development init -reconfigure -backend-config=development.s3.tfbackend
terraform -chdir=infra/terraform/development plan -out=development.tfplan
```

Review the concrete plan before an authorized apply. State identities need
`s3:ListBucket` on the bucket, `s3:GetObject`/`s3:PutObject` on their state key,
and `s3:GetObject`/`s3:PutObject`/`s3:DeleteObject` on its `.tflock` key. Grant
these through the account's deployment identity management, scoped separately
for bootstrap and development; workload roles have no state access. The backend
uses [native S3 locking](https://developer.hashicorp.com/terraform/language/backend/s3).

## Network and runtime handoff

Supply existing private subnets in two AZs of the same VPC. Terraform rejects
wrong-VPC, single-AZ and public-IP-assignment inputs. Review route tables and
VPC DNS separately: disabling public IP assignment alone does not prove a subnet
is private. No VPC, NAT gateway or endpoints are created. Record the approved
outbound HTTPS path for later workloads and private access to AWS services.

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

Keep bootstrap/state storage for recovery and audit. `prevent_destroy` and
`force_destroy = false` deliberately block routine state bucket destruction.
State retirement requires a separate reviewed archive and retention decision.
