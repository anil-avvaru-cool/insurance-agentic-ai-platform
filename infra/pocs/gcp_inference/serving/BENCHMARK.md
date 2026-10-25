# Benchmark client on the CPU pool

Run local commands from the repository root in Bash. Complete serving smoke
checks and section 7 telemetry in the [inference guide](../../../../docs/gcp/PHASE_1_INFERENCE_FIG.md)
before measured load. The client is a pod on the CPU pool; enter its container
with `kubectl exec`. Node SSH is unnecessary.

## 1. Configure and render locally

Use the serving runbook's ignored `.env`; if it already exists, add
`BENCHMARK_IMAGE` from `example.env`. Choose a CPU-compatible image for the
**same vLLM release** as the server and record both versions/digests. Inspect the
reviewed tag using `docker buildx imagetools inspect` and set its digest in `.env`.
The template overrides the image entrypoint to keep a client available; it does
not start a model server or request a GPU. Verify the image supports the CPU
node architecture/instruction set and contains Bash, tar, and the benchmark CLI.
See [vLLM CPU images](https://docs.vllm.ai/en/latest/getting_started/installation/cpu/).

```bash
set -a
source infra/pocs/gcp_inference/serving/.env
set +a
[[ "$BENCHMARK_IMAGE" =~ ^vllm/vllm-openai-cpu@sha256:[a-f0-9]{64}$ ]] || { echo 'Invalid benchmark image digest'; exit 1; }
[[ "$TOKENIZER_COMMIT" =~ ^[a-f0-9]{40}$ ]] || { echo 'Invalid tokenizer commit'; exit 1; }
mkdir -p infra/pocs/gcp_inference/serving/rendered
envsubst '${BENCHMARK_IMAGE} ${TOKENIZER_COMMIT}' \
  < infra/pocs/gcp_inference/serving/benchmark_client.yml \
  > infra/pocs/gcp_inference/serving/rendered/benchmark_client.yml
cat infra/pocs/gcp_inference/serving/rendered/benchmark_client.yml
```

## 2. Deploy and verify placement locally

```bash
kubectl config current-context
kubectl get nodes -l workload=cpu -L cloud.google.com/gke-nodepool
kubectl describe nodes -l workload=cpu
kubectl apply --dry-run=server -f infra/pocs/gcp_inference/serving/rendered/benchmark_client.yml
kubectl apply -f infra/pocs/gcp_inference/serving/rendered/benchmark_client.yml
kubectl -n inference-lab rollout status deployment/benchmark-client --timeout=15m
kubectl -n inference-lab get pods -l app=benchmark-client -o wide
kubectl -n inference-lab exec -it deployment/benchmark-client -- /bin/bash
```

Confirm the lab context and namespace from serving setup. Require the displayed
pod node to be in the CPU pool. Requests are 1 CPU/2 GiB RAM/2 GiB ephemeral
storage; limits are 2 CPUs/4 GiB/8 GiB. Check available CPU node capacity alongside
system/monitoring workloads before applying. If Pending, inspect pod events and
node capacity; do not move the client onto the GPU node. Large images also need
node disk headroom. Watch client CPU/RAM and throttling during load; adjust
resources consistently across comparisons if the client saturates.

## 3. Validate inside the client shell

```bash
set -euo pipefail
command -v tar
python3 -c 'from importlib.metadata import version; print(version("vllm"))' > /results/vllm_version.txt
vllm bench serve --help > /results/bench_help.txt
for flag in openai-responses --extra-body --tokenizer --result-dir --result-filename --save-detailed; do
  grep -F -- "$flag" /results/bench_help.txt > /dev/null || { echo "Missing CLI support: $flag"; exit 1; }
done
python3 - <<'PYTHON'
import json
from urllib.request import urlopen
base = "http://qwen3.inference-lab.svc.cluster.local:8000"
with urlopen(base + "/health", timeout=30) as response:
    print("health:", response.status)
with urlopen(base + "/v1/models", timeout=30) as response:
    models = json.load(response)
assert any(model["id"] == "Qwen/Qwen3-4B" for model in models["data"]), models
print(models)
PYTHON
python3 - <<'PYTHON'
import os
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="Qwen/Qwen3-4B",
    revision=os.environ["TOKENIZER_COMMIT"],
    local_dir="/client_cache/tokenizer",
    allow_patterns=["*.json", "*.txt", "*.model", "*.jinja"],
)
PYTHON
```

Compare `vllm_version.txt` with the serving image's installed version; stop on
mismatch. CLI help must pass on the pinned image before running load. The network
check verifies cluster DNS, service routing and model availability. Nodes need
egress for the image and tokenizer download. Only tokenizer/config files are
downloaded, not model weights. Use this local pinned tokenizer in every run.

Run the [section 8.4 example](../../../../docs/gcp/PHASE_1_INFERENCE_FIG.md#84-validate-the-benchmark-command)
inside this shell. First change `--num-prompts 200` to `--num-prompts 1` and
`--result-filename validation.json` to check Responses streaming and inspect errors
before the full synthetic validation. This is not a measured baseline. Follow
sections 8.3 and 8.5 for frozen corpus, warmup, run IDs, repetitions and telemetry.
Keep commands, corpus checksums, UTC run windows and configuration alongside the
JSON results. Use a unique `--result-filename` for every run to avoid overwrites.
CLI options must match the [pinned release's help](https://docs.vllm.ai/en/stable/cli/bench/serve/).

## 4. Export and clean up locally

Exit the client shell, then copy results before replacing/deleting its pod:

```bash
mkdir -p infra/pocs/gcp_inference/serving/rendered/benchmark_results
BENCHMARK_POD=$(kubectl -n inference-lab get pod -l app=benchmark-client -o jsonpath='{.items[0].metadata.name}')
: "${BENCHMARK_POD:?No benchmark client pod found}"
kubectl -n inference-lab cp "${BENCHMARK_POD}:/results/." \
  infra/pocs/gcp_inference/serving/rendered/benchmark_results
ls -lh infra/pocs/gcp_inference/serving/rendered/benchmark_results
# After verifying the exported results:
kubectl delete -f infra/pocs/gcp_inference/serving/rendered/benchmark_client.yml
```

Results and tokenizer cache use disk-backed `emptyDir`. Container restarts keep
them; pod replacement/deletion loses them. Export after each run and preserve a
copy outside `rendered/` for the experiment report. `rendered/` is git-ignored.
[`kubectl cp`](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_cp/)
requires tar in the client image. Export before serving cleanup deletes the
namespace. Removing the client does not stop node billing; use the Terraform
cleanup runbook when the lab is finished.
