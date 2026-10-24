# Phase 1: GCP inference implementation guide

Companion to [PHASE_1_INFERENCE_PLAN.md](PHASE_1_INFERENCE_PLAN.md).
Status: proposed GCP lab; shared S3 state infrastructure must be recreated.
No GCP deployment or performance result is claimed by this document.

## Infrastructure layout and state review

- Use one shared AWS S3 state bucket, managed by
  `infra/common_state/aws/bootstrap`, with one independent state key per root:

  | Terraform root | S3 state key |
  | --- | --- |
  | `infra/common_state/aws/bootstrap` | `infra/common_state/aws/bootstrap/terraform.tfstate` |
  | `infra/pocs/aws_bedrock` | `infra/pocs/aws_bedrock/terraform.tfstate` |
  | `infra/pocs/gcp_inference` | `infra/pocs/gcp_inference/terraform.tfstate` |

- The previous S3 buckets were deleted, according to the operator. Treat this
  as a fresh bootstrap, not a directory rename preserving old remote state.
  Confirm any surviving cloud resources and reconcile them before using empty
  state; bucket deletion alone does not establish that POC resources are gone.
- Review remaining local state, backend caches, overrides and saved plans before
  initialization. Do not reuse stale state or migrate it blindly into the new
  bucket. Create the bucket with local bootstrap state, then migrate that newly
  created state to its S3 key. See the
  [bootstrap runbook](../../infra/pocs/aws_bedrock/README.md#bootstrap-and-plan).
- Keep versioning suspended for POCs and `force_destroy = false`. Enable native
  S3 locking with `use_lockfile = true`; grant access to each root's state and
  `.tflock` objects. Keep the shared bucket until all dependent POCs are removed.
- S3 backend access requires AWS credentials even for the GCP POC; provisioning
  GCP also requires Google Cloud credentials.
- The GCP root now includes provisioning configuration. Follow the
  [GCP Terraform runbook](../../infra/pocs/gcp_inference/README.md) for section 4.
- Keep account IDs, bucket names, endpoints, credentials and raw state out of
  this guide; supply deployment values through ignored local configuration.
- [Agents.md](../../Agents.md) prefers cloud-managed model services and explicitly
  allows inference frameworks such as vLLM. This GKE/vLLM lab is permitted.

After recreating and configuring the shared backend, inspect each initialized
root's state. State describes Terraform's last saved view; it does not prove
endpoint health or current cloud drift. Never use the Bedrock root to provision
or destroy the GCP lab.

## 1. Review and scope

The plan makes sense for learning single-GPU serving: start with functional
validation, establish a repeatable baseline, then test one measured change.
Qwen3-4B with BF16 on an L4 is a reasonable starting hypothesis; verify actual
startup memory and sustainable concurrency rather than treating weight size as
proof that every workload fits. GKE adds useful infrastructure experience but
also setup time and overhead to a small inference lab.

This guide makes the following implementation choices explicit:

- Use a zonal GKE Standard cluster and exactly one GPU node in one zone.
- Keep a small CPU node pool for system and monitoring workloads; include its
  cost. Choose its size after reviewing actual resource requests.
- Pin the serving image by digest, model/tokenizer revisions, and benchmark
  client version before provisioning.
- Use a ClusterIP service and local port-forward for smoke tests. Run measured
  load from a separate CPU client in the cluster to reduce tunnel variability.
- Use local `/v1/responses` for smoke tests and measured load, with support
  verified in the pinned vLLM server and benchmark client.
- Specify four workload shapes, four concurrency caps, and three repetitions.
- Select the optimization after reviewing baseline evidence.

## 2. Architecture and experiment flow

```mermaid
flowchart LR
    TF[Terraform] --> CP[GKE Standard: zonal control plane]
    TF --> CPU[CPU node pool]
    TF --> GPU[GPU pool: one g2-standard-4 / one L4]
    LOCAL[Local smoke-test client] --> PF[kubectl port-forward]
    PF --> SVC[ClusterIP service: port 8000]
    CPU --> CLIENT[Benchmark client]
    CLIENT --> SVC
    SVC --> V[vLLM: one replica / Qwen3-4B BF16]
    GPU --> V
    HF[Pinned model and tokenizer snapshot] --> V
    V --> MET[Serving metrics and logs]
    GPU --> TEL[GPU telemetry]
    MET --> OBS[Monitoring on CPU pool / managed collection]
    TEL --> OBS
    CLIENT --> ART[Raw results and run configuration]
    OBS --> REPORT[Baseline and experiment report]
    ART --> REPORT
```

```mermaid
flowchart TD
    A[Verify quota, price, pins and budget] --> B[Provision and deploy]
    B --> C[Non-streaming and streaming smoke tests]
    C --> D[Confirm metrics and GPU telemetry]
    D --> E[Warm up and measure baseline matrix]
    E --> F[Identify bottleneck and write hypothesis]
    F --> G[Change one serving setting]
    G --> H[Repeat matched workload and measurements]
    H --> I[Report gains, regressions and limitations]
    I --> J[Destroy lab resources and verify remaining charges]
```

## 3. Preflight and reproducibility record

Use a dedicated lab project or clearly isolated resources. Install Terraform,
Google Cloud CLI, the GKE authentication plugin, and kubectl. Authenticate with
the intended project and configure Terraform credentials without committing
credentials or state containing sensitive values.

Record the following in the experiment artifacts before deployment:

| Setting | Required record |
| --- | --- |
| Cloud location | Project ID, region, single zone, quota and available capacity |
| Cluster | GKE version/channel, node image, network and endpoint access |
| Node pools | One GPU node; CPU machine type/count; disk type/size |
| GPU | One L4, driver version, no sharing or time slicing |
| Serving | Image digest, vLLM version, full startup arguments |
| Model | `Qwen/Qwen3-4B`, immutable model and tokenizer commit IDs |
| API | `/v1/responses`, server/client compatibility, `store: false` |
| Generation | Temperature, top-p/top-k, output cap, stop/EOS behavior, seed |
| Load client | Image/version, CPU placement, corpus hash and CLI help |
| Budget | Regional hourly estimate, maximum session duration, billing alert |

Check regional L4 quota, GPU availability and machine pricing. Quota does not
guarantee capacity. The plan's hourly estimate remains provisional: add CPU
nodes, disks, monitoring, networking and cluster management explicitly. Billing
alerts notify; they do not stop spending. Record a teardown time for each lab.
[GPU machine types](https://docs.cloud.google.com/compute/docs/gpus),
[GKE pricing](https://cloud.google.com/kubernetes-engine/pricing).

## 4. Infrastructure to implement

Use the dedicated Terraform configuration in `infra/pocs/gcp_inference` and its
[step-by-step runbook](../../infra/pocs/gcp_inference/README.md). It defines APIs,
networking, GKE, node pools, node identity/IAM and credential-command outputs.
The repository's AWS Terraform configurations are not GCP provisioning commands.

Use one zone for the GPU pool and verify the planned total node count is one;
node counts in multi-zone configurations can multiply across locations. Disable
GPU autoscaling for the initial fixed-hardware comparison. Review upgrade surge
settings because upgrades can temporarily add nodes; avoid upgrades during runs.
Install the supported NVIDIA driver through the chosen GKE configuration and
verify that Kubernetes advertises `nvidia.com/gpu` capacity.
[GKE GPU node pool instructions](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/gpus).

Before applying infrastructure, run Terraform formatting, initialization,
validation, and a saved plan in the new configuration directory. Inspect the
plan's machine types, locations, counts and billable resources. Apply that saved
plan only when ready to start the lab. Preserve the provider lockfile and a
sanitized configuration record.

Obtain credentials using the chosen project, zone and cluster name:

```bash
gcloud container clusters get-credentials CLUSTER_NAME \
  --zone ZONE --project PROJECT_ID
kubectl get nodes -o wide
kubectl describe nodes
```

Replace uppercase placeholders before execution. Verify the current kubectl
context belongs to the lab cluster before applying manifests or cleanup commands.

## 5. Serving deployment

Deploy using the checked-in [serving runbook](../../infra/pocs/gcp_inference/serving/README.md)
and these YAML files:

- [namespace.yml](../../infra/pocs/gcp_inference/serving/namespace.yml): dedicated namespace.
- [deployment.yml](../../infra/pocs/gcp_inference/serving/deployment.yml): pinned-image template, one L4, model cache, shared memory and health probes.
- [service.yml](../../infra/pocs/gcp_inference/serving/service.yml): internal port 8000.
- [example.env](../../infra/pocs/gcp_inference/serving/example.env): copy to ignored local `.env` and supply immutable pins.

The runbook covers credentials, capacity checks, rendering, API dry-run, apply,
rollout, smoke tests, troubleshooting and cleanup. Render the Deployment before
applying it; no cloud deployment has been performed or verified by adding these files.

The manifests create a dedicated namespace, a Deployment named `qwen3`, and a ClusterIP Service
named `qwen3` on port 8000. Use one replica and a `Recreate` deployment strategy
so an update does not wait for a second GPU. Request and limit one
`nvidia.com/gpu`; select the intended GPU pool and tolerate its GPU taint.
Set CPU/memory requests after checking node allocatable resources. The GPU node
has only 16 GB system RAM, so leave room for Kubernetes and loading overhead.

Set these serving arguments in the pinned image's supported syntax:

```text
--model Qwen/Qwen3-4B
--revision MODEL_COMMIT
--tokenizer-revision TOKENIZER_COMMIT
--dtype bfloat16
--max-model-len 4096
--tensor-parallel-size 1
--generation-config vllm
```

Record the effective GPU memory utilization, maximum sequences, batched-token
budget, prefix caching and chunked-prefill settings. Verify arguments against
that image's `--help`; do not silently substitute a newer image. Using
`--generation-config vllm` avoids silently inheriting model generation defaults;
send explicit sampling settings in requests.
[vLLM engine arguments](https://docs.vllm.ai/en/latest/configuration/engine_args/).

Allow model downloads through the configured egress path. Provide a model cache
with enough disk space, and record whether it persists between runs. Configure
shared memory for the container and a startup probe generous enough for the
first download/load; use readiness to prevent traffic before the model loads.
Check pod events, logs, GPU memory and system RAM before raising concurrency.
[GKE serving example](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/serve-llama-gpus-vllm).

## 6. Two generation smoke tests

Once the deployment and service exist, run:

```bash
kubectl -n inference-lab rollout status deployment/qwen3 --timeout=20m
kubectl -n inference-lab logs deployment/qwen3
kubectl -n inference-lab port-forward service/qwen3 8000:8000
```

Leave the port-forward running and use a second terminal for requests. The
Responses API is served locally by vLLM; Qwen3-4B still runs on the lab GPU.
Verify `/v1/responses`, streaming, and all request fields against the pinned
release before deployment. `top_k` and `chat_template_kwargs` are vLLM
extensions. Keep requests stateless with `store: false`; do not use
`previous_response_id` in this lab's baseline.
[vLLM Responses request schema](https://docs.vllm.ai/en/latest/api/vllm/entrypoints/openai/responses/protocol/).

Responses uses `input`, `max_output_tokens`, and typed output/stream events.
[OpenAI Responses migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses).

Run:

```bash
curl --fail-with-body http://127.0.0.1:8000/v1/models

curl --fail-with-body http://127.0.0.1:8000/v1/responses \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen/Qwen3-4B","input":[{"role":"user","content":"Explain an insurance deductible in two sentences."}],"temperature":0.7,"top_p":0.8,"top_k":20,"max_output_tokens":128,"chat_template_kwargs":{"enable_thinking":false},"store":false,"stream":false}'

curl --fail-with-body --no-buffer http://127.0.0.1:8000/v1/responses \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen/Qwen3-4B","input":[{"role":"user","content":"Explain an insurance deductible in two sentences."}],"temperature":0.7,"top_p":0.8,"top_k":20,"max_output_tokens":128,"chat_template_kwargs":{"enable_thinking":false},"store":false,"stream":true}'
```

Save responses and logs. Require the expected model identity and nonempty
`output_text` content within message items in the `output` array. The SDK's
`output_text` helper is not a top-level text field in the raw JSON response.
Inspect `status`, errors, and `incomplete_details`. For streaming, collect
`response.output_text.delta` events and require a terminal `response.completed`
event for this smoke test. Retain and report failed, incomplete, or error events;
a closed connection alone is not successful completion. If the output cap causes
an incomplete response, record it and adjust the smoke-test prompt or cap before
claiming success. Capture `usage.input_tokens` and `usage.output_tokens` from the
response or terminal event where supported; omit Chat Completions
`stream_options`. Thinking is disabled through the chat template parameter,
rather than merely removing a reasoning parser. Verify behavior with the pinned
version.
[Qwen vLLM deployment documentation](https://qwen.readthedocs.io/en/latest/deployment/vllm.html).

## 7. Observability before load

Scrape the serving `/metrics` endpoint using a Prometheus-compatible collector.
Configure GPU telemetry using a supported GKE/DCGM collection path. Confirm real
samples exist before benchmarking; enabling a collector alone is insufficient.
Keep scrape interval and monitoring placement unchanged between comparisons.

Capture TTFT, inter-token latency, end-to-end latency, output throughput,
running/waiting requests, KV-cache use, GPU utilization/memory, and pod/node RAM.
Record exact metric names from the pinned release. Client streaming measurements
include network effects; server metrics describe a different boundary. Preserve
both and state which is used for each reported result.
[vLLM production metrics](https://docs.vllm.ai/en/latest/usage/metrics.html).

## 8. Baseline workload and measurement protocol

| Workload | Target input tokens | Output cap | Total before any chat overhead |
| --- | ---: | ---: | ---: |
| Short prompt / short output | 128 | 128 | 256 |
| Short prompt / long output | 128 | 512 | 640 |
| Long prompt / short output | 2,048 | 128 | 2,176 |
| Long prompt / long output | 2,048 | 512 | 2,560 |

Run each shape with concurrency caps **1, 4, 16 and 32**: 16 cells. Start with
200 measured requests per cell and three repetitions: 48 measured runs. Run 20
unmeasured warmup requests before each run. If variability requires longer runs,
increase counts consistently for both configurations and document the decision.
Capture cold model download/load time separately.

Prepare and freeze a synthetic prompt corpus using the pinned tokenizer. Record
actual lengths after rendering any chat template. Input plus requested output
must remain within 4,096 tokens. Preserve the rendered prompts or token IDs,
their checksum, and order. Use identical data and seeds for matched comparisons.

Use `vllm bench serve` from a client matching the pinned serving version. Save
its help output first and require `openai-responses` and `--extra-body` support.
The following illustrates synthetic Responses load; validate flags with that version and save the generated corpus before
claiming a frozen-corpus comparison:

```bash
vllm bench serve --help
vllm bench serve \
  --backend openai-responses \
  --base-url http://qwen3.inference-lab.svc.cluster.local:8000 \
  --endpoint /v1/responses \
  --model Qwen/Qwen3-4B \
  --dataset-name random \
  --random-input-len 128 --random-output-len 128 \
  --num-prompts 200 --seed 42 \
  --request-rate inf --max-concurrency 1 \
  --extra-body '{"temperature":0.7,"top_p":0.8,"top_k":20,"store":false,"chat_template_kwargs":{"enable_thinking":false}}' \
  --save-result --save-detailed
```

Execute this inside the CPU benchmark client; cluster DNS is not available from
an ordinary local terminal. Adapt the supported dataset loader to replay the
frozen corpus for measured runs. Inspect a sample request to verify that the
client sends Responses `input`, `stream: true`, and `max_output_tokens` matching
each workload's output cap. The extra body preserves the smoke-test sampling,
thinking, and storage settings. Do not put a fixed `max_output_tokens` in the
extra body, because the workload output caps vary.

Send unrendered user content to the endpoint and verify actual token counts after
the server applies the pinned chat template. Configure any client-side dataset
rendering to avoid applying the template twice. Preserve rendered prompts/token
IDs as evidence, alongside the unrendered corpus used for replay. Keep the API,
template, and thinking setting unchanged between baseline and candidate.
Optional raw-completion measurements must be labeled separately and cannot
replace this Responses baseline.

Explicitly record sampling/EOS defaults used by the benchmark. Decide whether to
force the synthetic output length with supported ignore-EOS behavior or allow
early stopping; use the same decision on both sides and report actual generated
tokens. The random example alone is not a representative insurance workload.
[vLLM benchmark CLI](https://docs.vllm.ai/en/latest/cli/bench/serve/).

The infinite request rate with a concurrency cap measures bounded concurrent
load, not a production arrival distribution. Record achieved concurrency,
request rate, duration, errors and timeouts. Check that the CPU client is not
saturated. Preserve failed/saturated cells and stop a run that repeatedly OOMs;
do not silently omit it or report the target cap as achieved concurrency.

Use streaming for client-side TTFT and inter-token timing. Report p50/p95
end-to-end latency, latency distributions, successful output tokens/second and
run-to-run variability. Average time per output token and individual inter-token
latencies are different statistics; label the benchmark's actual outputs.

## 9. Choose one controlled experiment

Write the hypothesis before editing the serving configuration. Select one:

| Baseline observation | Candidate experiment | Required control |
| --- | --- | --- |
| Queueing or poor throughput | Change `max_num_batched_tokens` | Same corpus and concurrency |
| Repeated shared input prefixes | Compare prefix caching off/on | Same shared-prefix corpus and cache warmup |
| Long prefills delay decode | Tune chunked-prefill token budget | Same mixed-length request order |

Check release defaults first. V1 chunked prefill is enabled by default where
possible; enabling an already active feature is not a measured change.
[vLLM tuning documentation](https://docs.vllm.ai/en/latest/configuration/optimization/).

For batching, choose one alternative after inspecting the baseline rather than
guessing that a larger budget is better. For prefix caching, freeze the dedicated
shared-prefix corpus for both configurations, restart/reset cache consistently,
and separate cold-cache from warm-cache results. Do not compare a generic
baseline corpus against a new shared-prefix corpus as evidence of improvement.

Restart the replica if the setting requires it, rerun smoke tests, and use the
same warmup and measurement protocol. Repeat the full matrix for a general
batching change; for a targeted cache/mixed-prompt experiment, repeat the defined
target workload on both sides and state the narrower scope. Alternate baseline
and candidate runs when practical to expose temporal variation.

## 10. Two-GPU learning lab

After completing the Qwen3-4B baseline and controlled optimization, deploy
`Qwen/Qwen3-14B` in BF16 on one `g2-standard-24` node: two L4 GPUs, each with
24 GB VRAM, 24 vCPUs, and 96 GB host RAM. Keep the CPU pool and monitoring.
Verify regional pricing, two-GPU quota and capacity before provisioning; the
single-GPU cost estimate does not apply to this node.

- Qwen3-14B has 14.8 billion parameters: approximately 29.6 GB of BF16 weights
  before KV cache, intermediate tensors and runtime overhead. Weights exceed
  one L4's memory; two L4s are a reasonable starting configuration, not a
  guarantee of sustainable concurrency. Quantization or a larger-memory GPU
  changes the GPU requirement.
- Pin new model/tokenizer revisions and verify support in the serving image.
  Request and limit two `nvidia.com/gpu` devices in one pod; retain one replica
  and `Recreate`. Both GPUs cooperate on each request through tensor parallelism.
- Replace the baseline model and parallelism arguments with:

```text
--model Qwen/Qwen3-14B
--revision MODEL_COMMIT
--tokenizer-revision TOKENIZER_COMMIT
--dtype bfloat16
--max-model-len 4096
--tensor-parallel-size 2
--generation-config vllm
```

- Update smoke-test and benchmark model IDs. Keep thinking disabled and preserve
  sampling settings. Recount prompts with the pinned 14B tokenizer/template.
- Rerun both smoke tests and verify telemetry for each GPU. Start at concurrency
  1, then try 4, 16 and 32 only while memory and errors permit. Use the same four
  workload shapes, warmup, request counts and repetitions; retain failed cells.
- Record per-GPU memory/utilization, KV-cache capacity, startup time, latency,
  throughput, errors and full lab cost. Inspect GPU topology and communication
  behavior; two GPUs do not guarantee lower latency.
- Report 4B versus 14B as a model-and-hardware comparison, not evidence of a
  serving optimization or model quality improvement.

Optional comparison on the same two-GPU node, with identical Qwen3-4B pins and
workloads:

| Configuration | Learning goal |
| --- | --- |
| One 4B replica, one GPU, `TP=1`; second GPU idle | Same-node baseline |
| Two independent 4B replicas, one GPU each, `TP=1` | Replica scaling and load balancing |
| One 4B replica, two GPUs, `TP=2` | Tensor-parallel communication and scaling |

For replica scaling, each GPU holds a complete model and the ClusterIP service
distributes connections between ready pods. Verify requests reach both replicas;
connection reuse can skew traffic. Each request uses one replica. For tensor
parallelism, one model is sharded across both GPUs. Keep CPU/RAM allocations
recorded and comparable, and count both GPUs in cost even when one is idle.

[Qwen3-14B model card](https://huggingface.co/Qwen/Qwen3-14B),
[GCP GPU machine specifications](https://docs.cloud.google.com/compute/docs/gpus),
[vLLM parallelism guidance](https://docs.vllm.ai/en/latest/serving/parallelism_scaling/).

## 11. Results and evidence checklist

Save a run manifest, startup logs, smoke responses, raw benchmark JSON, monitoring
exports and charts under a dated experiment directory. Keep baseline and candidate
results separate with unique run IDs. Export artifacts before deleting clients,
pods, disks or monitoring resources.

Use a comparison table with workload, achieved concurrency, successful requests,
errors, output tokens/second, p50/p95 TTFT and end-to-end latency, inter-token
statistics, peak GPU memory, KV-cache use and estimated cost per million output
tokens. Show per-run values or dispersion alongside aggregate results.

Calculate cost as:

```text
successful_output_tokens_per_hour = successful_output_tokens / measured_seconds * 3600
USD_per_million_output_tokens = hourly_serving_cost / successful_output_tokens_per_hour * 1000000
```

Use elapsed wall time for the whole measured run, including time spent on failed
requests. Count output from successful requests only. Report zero-success runs
as undefined cost efficiency. Include GPU VM, CPU/system nodes, cluster fee,
disk and the declared monitoring/network estimate. Keep full lab-session cost
separate from steady-load extrapolation; warmup and idle time still cost money.

Completion requires reproducible Terraform/manifests, both smoke tests, usable
telemetry, the baseline matrix with failures retained, one controlled comparison,
and a report explaining tradeoffs. A repeatable regression is a valid result.
Do not claim model quality improvement from serving benchmarks alone.

## 12. Cleanup and verification

1. Export artifacts and record the experiment's end time.
2. Stop benchmark jobs and local port-forwards.
3. Generate and review a Terraform destroy plan in the dedicated lab state;
   destroy only resources owned by that configuration.
4. Verify the GKE cluster and GPU/CPU nodes are gone. Inspect disks, snapshots,
   external addresses, load balancers, buckets and retained monitoring/log data.
5. Remove separately created lab resources when no longer needed and record any
   deliberate retention with its estimated cost.
6. Check billing again after usage reporting catches up; immediate absence of a
   billing line is not proof that no charge remains.

Scaling the serving Deployment to zero does not remove a fixed GPU node. Removing
only the GPU pool also leaves the cluster, CPU nodes and supporting resources
billable. Preserve teardown commands and final inventory as completion evidence.
