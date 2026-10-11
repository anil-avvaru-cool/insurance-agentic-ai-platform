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
  intentionally suspended and `force_destroy = true` for these POCs.
- S3 backend access requires AWS credentials, including for GCP/Azure POCs;
  provisioning also requires credentials for the target cloud.
- Keep actual account IDs, bucket names, credentials, backend inputs, state,
  plans, and local variables in ignored files. Document placeholders only.
- Enable native S3 locking with `use_lockfile = true`; scope access to each
  POC's state and lock objects.

## Existing directory migration

- Bootstrap moved to `common_state/aws/bootstrap` and retains
  `bootstrap/terraform.tfstate`.
- Development moved to `pocs/aws_bedrock` and retains
  `development/terraform.tfstate`. Its environment remains `development` to
  preserve resource names. Existing `development.s3.tfbackend` filenames remain.
- Local backend inputs, variables, provider caches, and lockfiles move with their
  roots. No remote state migration, apply, or destroy is needed for this rename.
- Discard old saved plans; generate a fresh plan from the new root before applying.

With refreshed AWS credentials, reconfigure using the existing ignored inputs:

```bash
terraform -chdir=infra/common_state/aws/bootstrap init -reconfigure -backend-config=bootstrap.s3.tfbackend
terraform -chdir=infra/pocs/aws_bedrock init -reconfigure -backend-config=development.s3.tfbackend
terraform -chdir=infra/pocs/aws_bedrock plan
```

Confirm the backend keys still match and review any proposed changes. Do not
initialize against an empty state or change backend keys during this rename.
See the [Bedrock runbook](pocs/aws_bedrock/README.md) for deployment steps.
