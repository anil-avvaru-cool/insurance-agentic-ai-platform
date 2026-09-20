# Phase 1B Terraform foundation

For the short setup, test and teardown path, start with [Phase 1: start here](../../../docs/PHASE_1_START_HERE.md). This document is the detailed infrastructure reference.

- These roots provision development infrastructure and a smoke runtime: an encrypted, versioned, private S3 state bucket with TLS enforcement; private encrypted PostgreSQL RDS; SQS with a restricted DLQ; and separate ECS API, worker and action service roles.
- The `development` infrastructure root includes mandatory S3 document/vector storage, a Bedrock knowledge base, ECR and runtime IAM.
- The separate `runtime` root creates the mandatory AgentCore smoke runtime and worker invocation policy after the ARM64 image is published.
- Deployment order: apply infrastructure, build/push the image (no Terraform apply), then apply runtime with its required image digest. Bootstrap the state bucket first.
- See the [deployment guide](../../../docs/BEDROCK_DEVELOPMENT.md) for image publishing, tfvars and model scripts.
- The application still uses SQLite for business state; application migration and ECS/API deployment remain open.
- Configuration is explicit in ignored `terraform.tfvars` and backend files copied from the examples.
- Terraform does not automatically load the application `.env`; use AWS environment credentials or an AWS profile for the deployment identity.
- Never copy application tokens, model keys or database passwords into Terraform.
- All resource labels use underscores; AWS names that forbid underscores (S3/RDS) use lowercase alphanumeric names.
- AWS region identifiers retain AWS syntax.

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
  terraform -chdir=infra/aws/terraform/runtime init -backend=false
  terraform -chdir=infra/aws/terraform/runtime validate
  terraform -chdir=infra/aws/terraform/runtime test
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
- Select an available PostgreSQL engine version and matching parameter family in the chosen region.
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

- Also create an ignored `bootstrap.s3.tfbackend` with bucket, region, allowed_account_ids, `key = "bootstrap/terraform.tfstate"`, `encrypt = true`, and `use_lockfile = true`.
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
  ```

- Review the concrete plan before an authorized apply.
- State identities need `s3:ListBucket` on the bucket, `s3:GetObject`/`s3:PutObject` on their state key, and `s3:GetObject`/`s3:PutObject`/`s3:DeleteObject` on its `.tflock` key.
- Grant these through the account's deployment identity management, scoped separately for bootstrap and development; workload roles have no state access.
- The backend uses [native S3 locking](https://developer.hashicorp.com/terraform/language/backend/s3).

## Runtime deployment

The runtime root uses its own backend key (`runtime/terraform.tfstate`). Export
`development` output `runtime_inputs` to the ignored runtime
`infrastructure.auto.tfvars.json`, publish the image, and supply its immutable
digest in runtime tfvars. Follow the [deployment and migration guide](../../../docs/BEDROCK_DEVELOPMENT.md).
Existing combined deployments must transfer runtime ownership before a runtime apply.
Later image releases need only image publishing and a runtime apply.

## Network and runtime handoff

- The development root creates a VPC (`10.42.0.0/16`) with DNS enabled and two private `/24` subnets in separate available AZs.
- Both subnets use an explicit route table containing only the local VPC route; no public IP assignment, internet gateway, NAT gateway, or VPC endpoints are configured.
- Outputs expose the resulting VPC and subnet IDs.
- Before deploying workloads in these subnets, add an approved outbound HTTPS path and private access to required AWS services.
- The current AgentCore smoke runtime uses public network mode, not these subnets.
- Attach the output checkpoint client security group only to authorized database clients and migration tasks.
- It permits TCP 5432 to the database group only; workload HTTPS/service egress needs a separately reviewed group.
- RDS requires TLS; clients should use `sslmode=verify-full` and the current RDS CA bundle.
- The database is single-AZ development infrastructure, with seven-day backups and final snapshots; it does not establish production availability.
- RDS manages the administrator secret in Secrets Manager; Terraform exposes its ARN, never retrieves its value.
- A separately authorized migration operator must retrieve it, run checkpoint schema setup from the spike runbook, and provision a restricted runtime database user and secret.
- No workload has administrator-secret access.
- Database grants, secret delivery and runtime identities are not yet wired.
- See [RDS provider arguments](https://registry.terraform.io/providers/hashicorp/aws/6.27.0/docs/resources/db_instance).
- The API role can only send to the task queue; the worker can receive, delete, change visibility and read queue attributes.
- The action service role has no permissions until its core sandbox contract is approved.
- ECS container execution roles remain later work; the AgentCore identity is defined separately.
- SQS has a five-receive DLQ threshold, 300-second visibility and long polling.
- The future worker must extend visibility, retain idempotency, implement retries and establish a staffed DLQ recovery path.
- These queue settings do not implement a distributed outbox or worker.

## Teardown

The helper [terraform_teardown.py](../../../scripts/terraform_teardown.py) generates
plans without editing your normal `terraform.tfvars`. Run the commands below from
the repository directory with UV, Terraform and AWS CLI installed, and the existing
development backend initialized. Use the deployment credentials for this account.
Set `AWS_PROFILE` if you use named profiles; set `AWS_REGION` and `AWS_ACCOUNT_ID`
to the same values as your development tfvars.

### Stop workloads and reconcile tasks

1. Stop accepting new requests and disable scheduled jobs, retry producers,
   ingestion jobs and external callers. Suspend any service autoscaling and
   deployment automation that could restart workloads.
2. Stop producers first, leaving workers running to finish accepted work.
   This root currently creates IAM roles, not ECS services, so there are no
   Terraform-managed ECS workloads to stop. If you deployed ECS services separately,
   this example stops a replica producer service (replace the environment values):

   ```sh
   export AWS_PROFILE=your_development_profile
   export AWS_REGION=us-east-1  # replace with your deployment region
   export AWS_ACCOUNT_ID=123456789012  # replace with your account
   export ECS_CLUSTER=your_cluster
   export PRODUCER_SERVICE=your_api_service
   export WORKER_SERVICE=your_worker_service
   aws ecs update-service --cluster "$ECS_CLUSTER" --service "$PRODUCER_SERVICE" --desired-count 0
   aws ecs wait services-stable --cluster "$ECS_CLUSTER" --services "$PRODUCER_SERVICE"
   ```

3. Reconcile application records against completed side effects and queue work.
   For example, if a task is still marked `processing` but its downstream action
   succeeded, record that outcome before retrying; if it failed, retry through
   the approved idempotent recovery path or record an approved cancellation.
   Resolve DLQ messages individually and retain an audit record of their outcomes.
   A queue count alone cannot establish business completion. There is no distributed
   worker/outbox reconciliation command in this repository yet.
4. Check visible, in-flight and delayed messages in **both** queues:

   ```sh
   uv run --locked python scripts/terraform_teardown.py check
   ```

   The helper refuses to prepare plans while any counter is nonzero. It does not
   receive, delete or purge messages. SQS counters are approximate: after producers
   stop, allow at least a minute for counters to settle and repeat the check after
   workers finish. Use application records to establish completion as well.
5. Stop workers after reconciliation, then repeat the queue check. For separately
   deployed ECS replica workers:

   ```sh
   aws ecs update-service --cluster "$ECS_CLUSTER" --service "$WORKER_SERVICE" --desired-count 0
   aws ecs wait services-stable --cluster "$ECS_CLUSTER" --services "$WORKER_SERVICE"
   uv run --locked python scripts/terraform_teardown.py check
   ```

   Also stop standalone tasks and local processes using their actual supervisor;
   scaling an ECS service does not stop those. If you never deployed producers or
   workers, verify that no external client sends messages, then check both queues.
   See [ECS UpdateService](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_UpdateService.html)
   and [SQS queue attributes](https://docs.aws.amazon.com/cli/latest/reference/sqs/get-queue-attributes.html).

### Destroy runtime first

After stopping callers and reconciling workloads, review and apply a runtime
destroy plan as described in the [deployment guide](../../../docs/BEDROCK_DEVELOPMENT.md#teardown-order).
The helper below manages only development; it does not destroy runtime. Complete
any existing-state migration first so no runtime objects are left unmanaged.

### Prepare the final snapshot and destroy development

After completing reconciliation, run:

```sh
uv run --locked python scripts/terraform_teardown.py prepare --reconciled
terraform -chdir=infra/aws/terraform/development show teardown_prepare.tfplan
# After reviewing every change in the plan:
terraform -chdir=infra/aws/terraform/development apply teardown_prepare.tfplan
```

The helper records `db_deletion_protection = false` and a timestamp plus UUID
snapshot name, for example `final20260919t143000a4e58984d50b4e81a760c9c4f115662a`,
in ignored `development/teardown.tfvars.json`. It explicitly passes this file to
Terraform; normal plans do not load it automatically. Re-running the helper reuses
the identifier. Keep the file until teardown and snapshot verification finish.
The preparation plan must be successfully applied **before** planning destruction.
It is a full plan: investigate unrelated changes before applying.

```sh
uv run --locked python scripts/terraform_teardown.py destroy_plan --reconciled
terraform -chdir=infra/aws/terraform/development show teardown.tfplan
# Recheck immediately before applying the reviewed destroy plan:
uv run --locked python scripts/terraform_teardown.py check
terraform -chdir=infra/aws/terraform/development apply teardown.tfplan
```

`--reconciled` is your confirmation that the workload and business checks above
are complete; the script cannot infer this from AWS. Saved-plan applies execute
without another Terraform confirmation. Keep workloads stopped throughout.
If destruction fails, retain state and the snapshot identifier, inspect the failure,
and generate a fresh destroy plan before retrying. If a snapshot was already created,
check RDS before choosing a new identifier; do not delete a retained snapshot to retry.
For a later, separate deployment, archive the old teardown variables and plans before
running `prepare` so it generates a new identifier.

RDS creates the final snapshot during deletion, not during preparation. After a
successful destroy, use the identifier printed by the helper to verify retention:

```sh
aws rds describe-db-snapshots --db-snapshot-identifier YOUR_RECORDED_IDENTIFIER \
  --query 'DBSnapshots[0].{Identifier:DBSnapshotIdentifier,Status:Status,Created:SnapshotCreateTime}'
```

Confirm status is `available` and record the identifier in your teardown ticket.
Account for retained snapshots and any remaining backups, secrets or retained
Bedrock storage when reviewing residual costs. The helper leaves bootstrap intact.

### Remove bootstrap only after development teardown

- For a POC, the state bucket can be removed after runtime and development are destroyed.
- The bootstrap bucket uses `force_destroy = true`, so destroying it deletes all object versions, including old state files.
- Download any state history you need before teardown, and confirm no other Terraform root uses the bucket.
- If bootstrap state was migrated into this bucket, move it back to local state before destroying the bucket.
- Remove the ignored `bootstrap/remote_override.tf` file, then run `terraform -chdir=infra/aws/terraform/bootstrap init -migrate-state` and accept the state migration prompt.
- Confirm the local bootstrap state contains the bucket before continuing.
- Keep that local state file until the destroy is complete.
- Then review and apply a bootstrap destroy plan:

  ```sh
  terraform -chdir=infra/aws/terraform/bootstrap plan -destroy -out=bootstrap_destroy.tfplan
  terraform -chdir=infra/aws/terraform/bootstrap apply bootstrap_destroy.tfplan
  ```

- Do not start bootstrap from empty local state: Terraform would lose track of the bucket.
- A failed development destroy may leave resources behind, so check its result before deleting the state bucket.
