# Phase 1B deployment spike

Started September 13, 2026 with PostgreSQL checkpoint integration and Terraform
foundation roots. Both roots validate and five mocked Terraform plan tests pass. No cloud
resources have been provisioned and the deployment gate remains open.

## Checkpoint slice

Add `CHECKPOINT_BACKEND=sqlite` to an existing `.env` to preserve the local
configuration. For PostgreSQL, set `CHECKPOINT_BACKEND=postgres` and deliver
`CHECKPOINT_POSTGRES_DSN` through the environment. Use a dedicated checkpoint
database and the approved TLS connection parameters. Do not put credentials in
Terraform inputs or tracked files.

Install the locked dependencies and run schema setup once with a migration
identity before starting API/worker processes:

```sh
uv sync --locked
PYTHONPATH=src uv run --locked --env-file .env python -m workflows.checkpoints
```

Request processing opens checkpoint connections but never runs PostgreSQL DDL.
The schema setup command follows the documented
[PostgresSaver setup requirement](https://docs.langchain.com/oss/python/langgraph/add-memory).
Provision the runtime database grants separately after migration. Connection
pooling and distributed per-conversation serialization remain later work.

To verify against an isolated synthetic test database, supply
`CHECKPOINT_TEST_POSTGRES_DSN` and run:

```sh
PYTHONPATH=src uv run --locked --env-file .env python tests/evaluation/run_postgres.py
```

This runs the existing 22 journey tests with PostgreSQL planning/review
checkpoints and temporary SQLite application/core databases. It creates the
checkpoint schema and retains synthetic checkpoint rows for inspection; use a
disposable database. Missing settings or failed connections fail the command.
Recreated application objects/connections exercise logical recovery; process
kill, network interruption and RDS failover need a deployed test.

## Remaining deployment sequence

1. Record the AWS account, primary region, deployment identity, private subnet
   and security group references, outbound HTTPS route, and state bucket owner.
2. Configure and review the [Terraform foundation](../infra/aws/terraform/README.md):
   bootstrap/development roots, encrypted state with locking, private database,
   SQS/DLQ and service identities are implemented. Account-backed plan/apply and
   network verification remain pending.
3. Package API/worker and implement the AgentCore invocation adapter. Validate
   its [HTTP service contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html),
   authentication, architecture and private dependency access.
4. Migrate application persistence and queue dispatch sufficiently to run the
   authenticated synthetic journey without relying on a shared local disk.
5. Provision the small approved Bedrock/S3 Vectors corpus; record ingestion,
   retrieval references, metadata filters and withdrawal verification.
6. Record authenticated queue execution, restart/resume, network and retrieval
   evidence with a reviewed Terraform plan and resource teardown procedure.

Account/network decisions and a real PostgreSQL endpoint are still missing.
The 1A live-model evaluation is also pending independently of this spike.
