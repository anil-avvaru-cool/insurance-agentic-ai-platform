# Deploy Qwen3-4B on the GKE lab

Run from the repository root. These manifests implement section 5 of the
[inference guide](../../../../docs/gcp/PHASE_1_INFERENCE_FIG.md).
Prerequisites: `kubectl`, `gcloud` with its GKE auth plugin, `envsubst` (gettext),
and the provisioned [GKE lab](../README.md#apply-and-verify). They do not create
GPU nodes, cluster-wide monitoring, or a public endpoint. Kubernetes resource names use hyphens
where required by DNS naming rules.

## 1. Connect and check capacity

```bash
terraform -chdir=infra/pocs/gcp_inference output -raw get_credentials_command
# Run the printed gcloud command.
kubectl config current-context
kubectl get nodes -L cloud.google.com/gke-nodepool,cloud.google.com/gke-accelerator
kubectl describe nodes -l cloud.google.com/gke-nodepool=gpu
```

Confirm the intended lab context, one L4 node, `nvidia.com/gpu: 1` allocatable,
its taint, and sufficient remaining CPU, RAM and ephemeral storage. Requests are
2 CPUs, 10 GiB RAM and 25 GiB ephemeral storage; limits are 3 CPUs, 12 GiB RAM
and 40 GiB ephemeral storage. These are starting values for `g2-standard-4`,
not measured fit guarantees. Memory-backed shared memory counts against RAM;
leave room for system pods and loading overhead. The node disk must accommodate
container images plus cache/log storage. Adjust only after inspecting capacity.

## 2. Pin and review configuration

```bash
cp -n infra/pocs/gcp_inference/serving/example.env infra/pocs/gcp_inference/serving/.env
# Select latest stable release from https://github.com/vllm-project/vllm/releases
# Example: v0.32.0
# Search the same tag in docker https://hub.docker.com/r/vllm/vllm-openai/tags
# Example: Verify digest with command: docker buildx imagetools inspect vllm/vllm-openai:v0.32.0
# Edit serving/.env with your reviewed image digest and model/tokenizer commits.
# Model commit history: https://huggingface.co/Qwen/Qwen3-4B/commits/main
# Usually use the same snapshot commit for model and tokenizer.
set -a
source infra/pocs/gcp_inference/serving/.env
set +a
[[ "$VLLM_IMAGE" =~ ^vllm/vllm-openai@sha256:[a-f0-9]{64}$ ]] || { echo 'Invalid image digest'; exit 1; }
[[ "$MODEL_COMMIT" =~ ^[a-f0-9]{40}$ ]] || { echo 'Invalid model commit'; exit 1; }
[[ "$TOKENIZER_COMMIT" =~ ^[a-f0-9]{40}$ ]] || { echo 'Invalid tokenizer commit'; exit 1; }
: "${GPU_POOL:?Set GPU_POOL}"
mkdir -p infra/pocs/gcp_inference/serving/rendered
envsubst '${VLLM_IMAGE} ${MODEL_COMMIT} ${TOKENIZER_COMMIT} ${GPU_POOL}' \
  < infra/pocs/gcp_inference/serving/deployment.yml \
  > infra/pocs/gcp_inference/serving/rendered/deployment.yml
cat infra/pocs/gcp_inference/serving/rendered/deployment.yml
```

Use Bash for these commands; validation failures exit that shell. `.env` and
`rendered/` are ignored. Do not apply the unrendered deployment template or the
whole directory. Pin a release whose documentation supports Qwen3 and Responses
API streaming; record the release version corresponding to the digest. If Docker
is available locally, inspect the exact image before deployment:

```bash
docker run --rm --entrypoint python3 "$VLLM_IMAGE" \
  -m vllm.entrypoints.openai.api_server --help
```

Verify the manifest flags against that help. Prefix caching and chunked prefill
use the pinned release's defaults: record their effective values from startup
logs. GPU memory utilization is 0.90, sequence cap 32, and batched-token budget
4096; these are initial settings, not promised sustainable concurrency.

The public model requires no Hugging Face token. Nodes need outbound HTTPS to
fetch the image and model. Cache uses disk-backed `emptyDir`: container restarts
retain it, pod replacement/deletion loses it and downloads again. Shared memory
is a separate 1 GiB memory-backed volume. No PVC or persistent disk is created.

## 3. Validate and deploy

```bash
kubectl apply --dry-run=client -f infra/pocs/gcp_inference/serving/namespace.yml
kubectl apply -f infra/pocs/gcp_inference/serving/namespace.yml
kubectl apply --dry-run=server -f infra/pocs/gcp_inference/serving/rendered/deployment.yml
kubectl apply --dry-run=server -f infra/pocs/gcp_inference/serving/service.yml
kubectl apply -f infra/pocs/gcp_inference/serving/rendered/deployment.yml
kubectl apply -f infra/pocs/gcp_inference/serving/service.yml
kubectl -n inference-lab rollout status deployment/qwen3 --timeout=35m
kubectl -n inference-lab get pods -o wide
kubectl -n inference-lab logs deployment/qwen3
kubectl -n inference-lab get endpointslices -l kubernetes.io/service-name=qwen3
```

The startup probe allows approximately 30 minutes for download/loading. Readiness
keeps the Service from routing to an unloaded model. One replica and `Recreate`
release the single GPU before starting a replacement; updates interrupt service.
Dry-run validates API configuration, not model fit or runtime compatibility.

## 4. Check inference

```bash
kubectl -n inference-lab port-forward service/qwen3 8000:8000
```

Keep that terminal open. In a second terminal, run both generation requests from
[section 6](../../../../docs/gcp/PHASE_1_INFERENCE_FIG.md#6-two-generation-smoke-tests).
Also check health and metrics:

```bash
curl --fail-with-body http://127.0.0.1:8000/health
curl --fail-with-body http://127.0.0.1:8000/v1/models
curl --fail-with-body http://127.0.0.1:8000/metrics
kubectl -n inference-lab exec deployment/qwen3 -- nvidia-smi
```

Require successful non-streaming and streaming generation before benchmarking.
Create the separate CPU client using [benchmark_client.yml](benchmark_client.yml)
and the [benchmark runbook](BENCHMARK.md), including result export and cleanup.
The ClusterIP has no public authentication boundary; use synthetic lab prompts.
`/metrics` availability alone does not install a collector or GPU telemetry;
complete section 7 before measuring load.

After successful smoke tests, follow
[section 7.3](../../../../docs/gcp/PHASE_1_INFERENCE_FIG.md#73-configure-managed-scraping-of-vllm)
to configure vLLM scraping with [pod_monitoring.yml](pod_monitoring.yml).
Managed Prometheus must be enabled and its `PodMonitoring` CRD available:

```bash
kubectl apply --dry-run=server -f infra/pocs/gcp_inference/serving/pod_monitoring.yml
kubectl apply -f infra/pocs/gcp_inference/serving/pod_monitoring.yml
kubectl -n inference-lab describe podmonitoring qwen3
```

The manifest selects `app: qwen3` in `inference-lab` and scrapes `/metrics` on
the named `http` container port every 30 seconds. Keep that interval fixed
across experiments and avoid duplicate scrape configurations. Complete section
7's ingestion and GPU telemetry checks before benchmarking; applying this
manifest alone does not verify collection.

## 5. Troubleshoot, update and remove

```bash
kubectl -n inference-lab describe pods -l app=qwen3
kubectl -n inference-lab get events --sort-by=.metadata.creationTimestamp
kubectl -n inference-lab logs deployment/qwen3 --tail=200
# Use for a restarted container; errors if no previous container exists:
kubectl -n inference-lab logs deployment/qwen3 --previous --tail=200
```

- `Pending`: check pool selector, taint, driver/device-plugin readiness and
  allocatable resources. Another pod may already hold the only GPU.
- `ImagePullBackOff`: verify digest, registry access and NAT/egress.
- Download/revision errors: verify public snapshot commits and model egress.
- `OOMKilled` / eviction: inspect node/pod RAM and disk; shared memory counts
  toward RAM. Do not raise limits beyond node capacity.
- CUDA OOM: inspect startup logs, reduce sequence/token budgets or GPU memory
  utilization as appropriate, and record the change before repeating smoke tests.
- Responses errors: verify the pinned release supports the endpoint and request
  fields; do not silently switch API or upgrade the image during comparisons.

For an update, edit the template or local pins, rerender, repeat server dry-run
and apply, then repeat rollout checks and both smoke tests. Export logs and run
artifacts before replacing or deleting the pod.

```bash
kubectl delete -f infra/pocs/gcp_inference/serving/pod_monitoring.yml --ignore-not-found
kubectl delete -f infra/pocs/gcp_inference/serving/service.yml
kubectl delete -f infra/pocs/gcp_inference/serving/rendered/deployment.yml
# Delete the dedicated namespace only after exporting all artifacts:
kubectl delete -f infra/pocs/gcp_inference/serving/namespace.yml
```

Deleting workloads leaves the GPU VM billable. Follow the
[Terraform cleanup runbook](../README.md#cleanup) to remove the lab infrastructure.

References: [vLLM Kubernetes deployment](https://docs.vllm.ai/en/latest/deployment/k8s/),
[GKE GPU pools and drivers](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/gpus).
