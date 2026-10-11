# GCP inference POC

Proposed Terraform root for the [inference guide](../../../docs/gcp/PHASE_1_INFERENCE_FIG.md).
No Terraform resources or deployment are defined here yet.

- Use the shared AWS S3 bucket with a dedicated key such as
  `pocs/gcp_inference/terraform.tfstate` and native S3 locking.
- Configure actual backend values in ignored local files; keep examples generic.
- Resolve the guide's cloud-managed inference requirement before provisioning.
