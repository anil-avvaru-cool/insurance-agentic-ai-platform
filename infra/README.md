# Infrastructure POCs

```text
infra/
├── aws_delete_me/              # Legacy files retained for review
├── common_state/aws/bootstrap/  # Shared S3 state infrastructure
└── pocs/
    ├── aws_bedrock/             # Existing AWS Bedrock Terraform root
    └── gcp_inference/           # Proposed GCP lab; not provisioned
```

- Use one independent Terraform root and remote state key per POC. Future Azure
  POCs can use `pocs/azure_inference` with their own key in the shared bucket.
- `aws_delete_me` retains the legacy AgentCore Dockerfile and local runtime
  variables for review; it is outside the active Terraform roots.
- Bootstrap manages the state bucket, not POC resources. Bucket versioning is
  intentionally suspended and `force_destroy = false` for these POCs.
- S3 backend access requires AWS credentials, including for GCP/Azure POCs;
  provisioning also requires credentials for the target cloud.
- Keep actual account IDs, bucket names, credentials, backend inputs, state,
  plans, and local variables in ignored files. Document placeholders only.
- Enable native S3 locking with `use_lockfile = true`; scope access to each
  POC's state and lock objects.

## Fresh-start state layout

Use the default Terraform workspace and mirror each root's repository path:

| Terraform root | S3 state key |
| --- | --- |
| `infra/common_state/aws/bootstrap` | `infra/common_state/aws/bootstrap/terraform.tfstate` |
| `infra/pocs/aws_bedrock` | `infra/pocs/aws_bedrock/terraform.tfstate` |
| `infra/pocs/gcp_inference` | `infra/pocs/gcp_inference/terraform.tfstate` |

- The operator reports that the previous S3 buckets were deleted. Recreate the
  shared bucket before initializing POC backends.
- Confirm surviving cloud resources and review local state, backend caches,
  overrides and saved plans before using empty state. Reconcile any surviving
  resources rather than provisioning duplicates.
- Bootstrap starts with local state; migrate its newly created state into S3
  after the bucket exists. Do not migrate stale state from the previous setup.
- Configure each POC's backend with its dedicated key and matching IAM access.
- Bedrock's resource environment and backend filename remain `development`;
  these do not determine its S3 key.
- Generate and review fresh plans before applying. Follow the
  [Bedrock bootstrap runbook](pocs/aws_bedrock/README.md#bootstrap-and-plan).
