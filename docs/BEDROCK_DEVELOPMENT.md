# Bedrock and AgentCore development resources

This increment prepares deployable Terraform and a small model/retrieval runtime.
It does not move the claims application into AWS. No account-backed plan, apply,
image build/push, ingestion or model invocation was executed during implementation.

## Configuration to fill in

Local ignored files have been created alongside their tracked examples:

- `infra/terraform/bootstrap/terraform.tfvars`
- `infra/terraform/development/terraform.tfvars`
- `infra/terraform/development/development.s3.tfbackend`

Replace `000000000000`, the VPC/subnet placeholders and the state bucket name
consistently. Confirm the owner, existing private network, PostgreSQL engine version
and final snapshot name. Examples use `us-east-1`, `db.t4g.micro`, 20 GiB, single AZ,
seven-day RDS backups and deletion protection. `16.6`/`postgres16` is a matching
example pair, not a guarantee that AWS still permits new instances on that minor
version; inspect `aws rds describe-db-engine-versions --engine postgres --region us-east-1`.
Use an available PostgreSQL 16 version. Never put credentials or passwords in tfvars.

The new configuration uses Nova Lite for regional Converse calls and Titan Text
Embeddings v2 with 1024 dimensions. Changing the embedding model/dimension requires
a coordinated index replacement and reingestion; these two values are intentionally
paired in Terraform locals. Regional model access and availability must be checked
in your account before applying. Inference profiles are not supported by this
initial IAM configuration; they require explicit profile and destination model ARNs.
See the [Nova Lite model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html).

## Resources and boundaries

`enable_bedrock = true` adds a private, versioned, AES256 encrypted document bucket,
a dedicated encrypted S3 vector bucket/index, a Bedrock knowledge base and S3 data
source, ingestion IAM role, immutable ECR repository and AgentCore execution role.
The source includes only `approved/`. Text and Bedrock metadata are non-filterable;
custom `audience` and `approved` fields support the smoke retrieval filter.
The index and knowledge base both use 1024 dimensions and cosine similarity.
See [AWS vector store prerequisites](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-setup.html).

`enable_agentcore_runtime = true` additionally creates an HTTP AgentCore runtime
and grants the existing worker role invocation permission. The runtime accepts
`{"operation":"converse","text":"..."}` or `{"operation":"retrieve","text":"..."}`.
It has no claim submission tools, application business state, SQS consumer or RDS
credentials. The worker's actual invocation adapter remains to be implemented.

The runtime uses managed PUBLIC outbound networking and default IAM inbound
authentication. It is not an anonymously callable API. It has no VPC/database
connectivity. `/ping` and `/invocations` implement the
[AWS HTTP container contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html).
Do not expose the container directly to users; local container execution has no
AWS front-door IAM enforcement. Account deployment permissions, including scoped
`iam:PassRole`, must be provided by your operator identity. Workload policies do
not grant operator deployment permissions. The knowledge role has embedding, source
read and index access; the runtime has selected model invocation and KB retrieval.
See [KB IAM requirements](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-permissions.html)
and [AgentCore runtime IAM](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html).

## First deployment: storage, knowledge base and ECR

Follow the [Terraform bootstrap/state runbook](../infra/terraform/README.md) first.
Keep `enable_agentcore_runtime = false` and `agentcore_image_digest = ""`.
After reviewing the development plan, apply it and inspect the resource IDs:

```sh
terraform -chdir=infra/terraform/development plan -out=development.tfplan
terraform -chdir=infra/terraform/development apply development.tfplan
terraform -chdir=infra/terraform/development output -json bedrock
```

This creates an empty knowledge base. Terraform does not upload documents or run
an ingestion job. IAM propagation or region/model availability can still cause a
live create to fail; inspect the actual AWS failure before retrying the plan.

## Build and enable the runtime

Requires Docker with buildx/ARM64 support, AWS CLI, jq and an ECR publishing identity.
Run from the repository root. Use a new image tag for every build because tags are
immutable. The Dockerfile copies only the smoke runtime source and locked package
metadata; no `.env`, SQLite databases or application tokens are copied.

```sh
export AWS_REGION=us-east-1
export AGENTCORE_REPOSITORY_URL="$(terraform -chdir=infra/terraform/development output -json bedrock | jq -r .ecr_repository_url)"
export AGENTCORE_IMAGE_TAG=development_20260913_01
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "${AGENTCORE_REPOSITORY_URL%%/*}"
docker buildx build --platform linux/arm64 --provenance=false -f infra/containers/agentcore.Dockerfile -t "$AGENTCORE_REPOSITORY_URL:$AGENTCORE_IMAGE_TAG" --push .
aws ecr describe-images --region "$AWS_REGION" --repository-name "${AGENTCORE_REPOSITORY_URL#*/}" --image-ids imageTag="$AGENTCORE_IMAGE_TAG" --query 'imageDetails[0].imageDigest' --output text
```

Paste the returned `sha256:...` into development tfvars, set
`enable_agentcore_runtime = true`, then review and apply a fresh plan. Terraform
constructs the image URI from its own ECR repository and your immutable digest.
The image must already exist; Terraform cannot verify ARM64 compatibility in an
offline plan. Inspect ECR scan results before enabling it. Container build and
AgentCore startup remain live acceptance checks.

## Model scripts and ingestion

Add the AWS probe settings from `example.env` to your existing `.env`; preserve
existing application configuration. Fill KB ID, data source ID and runtime ARN
from `terraform output -json bedrock`. Use AWS profile/role credentials, not model
API keys. Run commands from the repository root:

```sh
PYTHONPATH=src uv run --locked --env-file .env python scripts/bedrock_smoke.py models
PYTHONPATH=src uv run --locked --env-file .env python scripts/bedrock_smoke.py converse --text 'Describe a synthetic auto intake draft in one sentence.'
PYTHONPATH=src uv run --locked --env-file .env python scripts/bedrock_smoke.py embed --text 'Synthetic auto intake draft'
```

These commands call AWS and can incur charges. `models` lists the regional catalog;
a successful Converse/embedding invocation is the actual access check. The embedding
probe returns dimensions/token count rather than dumping the vector.

For a synthetic ingestion test, upload the two fixture objects with an operator
identity that can write to the document bucket:

```sh
export KNOWLEDGE_BUCKET="$(terraform -chdir=infra/terraform/development output -json bedrock | jq -r .knowledge_bucket)"
aws s3 cp tests/fixtures/knowledge/synthetic_service.txt "s3://$KNOWLEDGE_BUCKET/approved/synthetic_service.txt"
aws s3 cp tests/fixtures/knowledge/synthetic_service.txt.metadata.json "s3://$KNOWLEDGE_BUCKET/approved/synthetic_service.txt.metadata.json"
PYTHONPATH=src uv run --locked --env-file .env python scripts/bedrock_smoke.py ingest
PYTHONPATH=src uv run --locked --env-file .env python scripts/bedrock_smoke.py retrieve --text 'What does the demonstration receipt establish?'
PYTHONPATH=src uv run --locked --env-file .env python scripts/bedrock_smoke.py invoke --text 'Describe a synthetic auto intake draft in one sentence.'
```

The fixture's `approved=true` is only a development test label, not business
approval. Never copy this synthetic approval into real documents. Ingestion waits
up to the configured timeout and fails on failed/stopped jobs or document failures.
If it times out, it prints the job ID in the error; the AWS job continues. Inspect
that job before retrying. A successful empty ingestion is not retrieval evidence:
verify nonempty results, source URI, text and metadata against the fixture.

Retrieval returns source content and citations separately from model generation.
The filter is a development demonstration, not the application's catalog approval,
effective-date, withdrawal or customer authorization contract. Implement those
checks and RAG evaluations before integrating real customer traffic. The existing
OpenAI language adapter and nine-case evaluation are unchanged.

## Validation and retention

Offline verification: development Terraform validation and eight mocked plans;
23 unit tests including seven new Bedrock/runtime cases, and all 22 existing
local integration journeys. Docker Desktop is not integrated with this WSL distro,
so the container could not be built locally. These checks do not prove
live IAM permissions, model quality, service quotas, network connectivity or image
startup. Run tests from the repo root:

```sh
terraform fmt -check -recursive infra/terraform
terraform -chdir=infra/terraform/development validate
terraform -chdir=infra/terraform/development test
PYTHONPATH=src:. uv run --locked python -m unittest discover -s tests/unit -v
```

Document buckets, vector buckets and ECR repositories refuse forced deletion.
Data source deletion uses RETAIN; removing it leaves vectors and can leave stale
retrieval content until explicitly cleaned up. Plan retirement of source object
versions, vectors and container images separately. Runtime logs use the AWS
service's log groups; managed log retention/telemetry configuration remains open.
RDS, stored objects/vectors, image storage and logs can cost money while idle.
