# GCP inference POC

Terraform for section 4 of the [inference guide](../../../docs/gcp/PHASE_1_INFERENCE_FIG.md).
Creates a zonal GKE Standard cluster, one CPU node, one L4 node, dedicated VPC,
private nodes, Cloud NAT, node service account/IAM, and managed Prometheus.
Serving manifests, metric scrape resources, GPU telemetry and benchmarks follow
in sections 5–8; enabling Prometheus alone does not collect those metrics.

## Configure

- Copy `terraform.tfvars.example` to ignored `terraform.tfvars` if missing.
- Replace project ID and `master_authorized_cidrs` with your public IPv4 `/32`.
- Copy `gcp.s3.tfbackend.example` to ignored `gcp.s3.tfbackend`; supply the verified
  shared bucket and AWS account ID. Keep the dedicated GCP state key.
- Existing project must have billing enabled. The operator needs permission to
  enable APIs, manage networking/GKE/service accounts and grant project IAM.
- Authenticate AWS for S3 and Google Application Default Credentials for Terraform:

```bash
gcloud auth login
gcloud auth application-default login
```

- Verify regional L4 and G2 CPU quotas, capacity and current prices including
  NAT, CPU nodes, disks, logging and cluster fees. Record session budget and
  teardown time. No automatic shutdown or budget enforcement is configured.
- Check all CIDRs for overlap, including the control-plane range `172.16.0.0/28`.
- Cloud names replace underscores with hyphens where Google requires them.
- The REGULAR release channel selects a supported GKE version; outputs record
  the deployed version. Pin serving image/model revisions before provisioning.
- GPU autoscaling is disabled; upgrades use zero surge and one unavailable node.
  Avoid runs during maintenance; auto-repair/auto-upgrade can interrupt serving.

## Validate and plan

Run from the repository root:

```bash
terraform -chdir=infra/pocs/gcp_inference fmt -check -recursive
terraform -chdir=infra/pocs/gcp_inference init -backend-config=gcp.s3.tfbackend
terraform -chdir=infra/pocs/gcp_inference validate
terraform -chdir=infra/pocs/gcp_inference test
terraform -chdir=infra/pocs/gcp_inference plan -input=false -out=gcp.tfplan
terraform -chdir=infra/pocs/gcp_inference show gcp.tfplan
```

Review one GPU node in one zone, the CPU count, networking and all billable
resources. GKE briefly creates a default CPU pool during cluster creation and
then removes it. The two dedicated pools remain. Preserve the provider lockfile.
Do not reuse an older saved plan after changing configuration.

## Apply and verify

Apply only the reviewed saved plan when ready to start the billable lab:

```bash
terraform -chdir=infra/pocs/gcp_inference apply gcp.tfplan
terraform -chdir=infra/pocs/gcp_inference output get_credentials_command
```

Run the printed credentials command, then:

```bash
kubectl config current-context
kubectl get nodes -o wide
kubectl get nodes -L cloud.google.com/gke-nodepool
kubectl describe nodes
```

Verify the lab context, one CPU node, one GPU node and `nvidia.com/gpu: 1` on
that node. The GPU pool has `nvidia.com/gpu=present:NoSchedule`; serving pods
must tolerate it and select the GPU pool. Benchmark/monitoring pods select CPU.
The private nodes use NAT for public images/model downloads; no serving load
balancer or public inference endpoint is provisioned.

## Cleanup

Export experiment artifacts first, then review and apply a dedicated destroy plan:

```bash
terraform -chdir=infra/pocs/gcp_inference plan -destroy -out=destroy.tfplan
terraform -chdir=infra/pocs/gcp_inference show destroy.tfplan
terraform -chdir=infra/pocs/gcp_inference apply destroy.tfplan
```

Verify cluster, nodes, disks and NAT are gone and check delayed billing. Enabled
project APIs intentionally remain enabled; the existing project and shared AWS
state bucket are not owned or destroyed by this root.

## Module structure

The root owns API enablement, provider/backend configuration, deployment inputs,
and public outputs. `modules/network` owns the VPC, subnet, secondary ranges and
optional router/NAT. `modules/gke` owns node identity/IAM, the cluster and both
node pools. Modules inherit the root Google provider. The subnet output waits
for NAT so cluster creation retains its download-egress dependency.

`migrations.tf` maps the previous root resource addresses into the modules,
including counted router/NAT instances. Existing state should show address moves
without resource replacement from this refactor. Keep the same backend and
review a fresh plan before applying; do not apply an older saved plan.

Mocked tests cover GKE settings, networking, optional NAT and rejected baseline
inputs. GPU upgrades require zero surge and one unavailable node.
