# Phase 1: GCP LLM Inference Plan

Status: planned; no cloud resources have been deployed as part of this document.

## Objective

Build practical experience with LLM inference optimization by deploying a small open-weight model with vLLM on Google Kubernetes Engine (GKE), establishing a reproducible performance baseline, and demonstrating one measured optimization. Phase 1 establishes the foundation for deeper experiments with larger models and additional optimization techniques.

## Initial configuration

| Item | Initial choice |
|---|---|
| Model | `Qwen/Qwen3-4B` |
| Serving engine | vLLM, with a pinned container version |
| Model precision | BF16 baseline |
| Cloud platform | GCP, GKE Standard |
| GPU node | One `g2-standard-4`: one NVIDIA L4 with 24 GB VRAM, 4 vCPUs, 16 GB system RAM |
| Infrastructure | Terraform |
| Replicas | One |
| Maximum context | 4,096 tokens, including prompt and output |
| Generation behavior | Thinking mode disabled initially; fixed generation settings for comparison |
| Region | Select a lower-cost US region after checking GPU availability, quota, and regional pricing |

The model has approximately 8 GB of BF16 weights. Remaining GPU memory must accommodate the KV cache, runtime overhead, and intermediate tensors; supported concurrency must be measured. Pin the model revision and record all serving settings.

## Estimated cloud cost

Planning estimate in USD for an on-demand, single-GPU GKE Standard setup, recorded on October 10, 2026:

| Component | Approximate cost per hour |
|---|---:|
| `g2-standard-4`, including its L4 GPU | $0.71 |
| GKE cluster management, before eligible free-tier credit | $0.10 |
| Disk, light logging, and optional small system node | $0.05–$0.15 |
| Practical planning total | $0.85–$1.00 |

Budget approximately $9–$10 for a 10-hour lab or $620–$730 for 730 hours of continuous operation. These are estimates, not a quote; regional pricing, network traffic, load balancers, logging volume, and the final node topology can change the total. The VM price already includes the GPU.

Before deployment, verify current regional prices and GPU quota, choose a session budget, and configure a billing alert. Billing alerts do not enforce a spending cap. Remove the GPU node after each lab session; idle nodes still incur charges. Account for any remaining cluster, disk, networking, and logging charges after removing the node.

## Implementation plan

### 1. Provision and deploy

- Use Terraform to define the required GCP services, GKE cluster, GPU node pool, service accounts, permissions, and supporting resources.
- Record project, region, zone, machine type, storage, and node counts as explicit configuration.
- Deploy one vLLM replica with the initial configuration above and verify GPU access and model readiness.
- Use an internal endpoint with a local port-forward for the first lab unless external access is needed.
- Document repeatable provisioning, deployment, access, and cleanup commands.

### 2. Verify two generations

- Send two generation requests: one non-streaming and one streaming.
- Confirm successful responses, nonempty output, expected model identity, and token usage where available.
- Capture request settings, responses, and relevant startup/request logs as smoke-test evidence.
- Treat these requests as functional validation; they do not establish performance.

### 3. Instrument the service

- Collect vLLM metrics through Prometheus-compatible monitoring, plus GPU telemetry and GKE logs.
- Observe time to first token, inter-token latency, end-to-end latency, throughput, queued/running requests, KV-cache usage, GPU utilization, and GPU memory.
- Use logs to investigate startup failures, request errors, timeouts, and out-of-memory conditions.
- Keep metric names and dashboards aligned with the pinned vLLM version.

### 4. Establish a reproducible baseline

- Use vLLM serving benchmark tooling against the deployed endpoint.
- Test short and long prompts and short and long outputs, staying within the 4,096-token total context limit.
- Sweep concurrency through 1, 4, 16, and 32; record failures or saturation rather than assuming all levels are sustainable.
- Fix the prompt corpus, model revision, tokenizer, generation settings, and hardware. Record actual input/output token counts, request count, and benchmark duration.
- Warm up before measurement and report cold-start behavior separately. Repeat measured runs sufficiently to assess variability.
- Save benchmark commands, raw results, serving configuration, and charts.

Report:

| Metric | Purpose |
|---|---|
| Time to first token | Responsiveness before streaming starts |
| Inter-token latency | Streaming speed and consistency |
| p50/p95 end-to-end latency | Typical and slower request completion times |
| Aggregate output tokens/second | Serving throughput for the recorded workload |
| Successful requests and errors | Reliability under load |
| GPU utilization, memory, and KV-cache usage | Evidence of resource bottlenecks |
| Cost per million output tokens | Estimated cost efficiency for the measured workload |

Calculate estimated cost per million output tokens as `(total hourly serving cost / successful output tokens per hour) * 1,000,000`. State which infrastructure costs are included and how the hourly token rate was derived.

### 5. Demonstrate one optimization

- Inspect the baseline to identify a bottleneck and write a hypothesis before changing configuration.
- Select one experiment: adjust batching limits, compare prefix caching with repeated shared prefixes, or tune chunked prefill for mixed prompt lengths.
- Check the pinned version's defaults first; a feature already enabled requires an explicit comparison or parameter change.
- Change one setting at a time and rerun the same workload, preserving comparable warmup and measurement conditions.
- Report latency, throughput, memory, errors, and cost together. Record regressions as well as improvements.
- Explain why the result occurs and which workloads benefit. A reproducible negative result is useful evidence; do not claim an improvement unless measurements support it.

### 6. Document findings and clean up

- Produce a short report with the baseline, experiment hypothesis, configuration change, results, charts, and limitations.
- Preserve benchmark artifacts and document how to reproduce the experiment.
- Remove lab resources when finished and verify what remains billable.

## Completion criteria

- Terraform configuration and deployment instructions are reviewable and reproducible.
- Qwen3-4B serves successfully through vLLM on one L4-backed GKE node.
- Both generation smoke tests pass, including streaming.
- Logs and serving/GPU metrics are available for diagnosis.
- The baseline covers the planned workload and concurrency matrix, with failures recorded.
- One controlled optimization experiment has repeatable before/after evidence and an explanation of its tradeoffs.
- A results report records configuration, performance, estimated cost, and limitations.
- Cleanup instructions are verified and remaining charges are documented.

## Follow-up learning

After Phase 1, explore quantization with a small quality evaluation, larger models that create meaningful memory pressure, KV-cache precision, replica scaling, and multi-GPU parallelism. Add speculative decoding or prefill/decode disaggregation when the workload and hardware justify them. A small-model deployment alone does not establish deep experience with all inference optimization techniques.

## References

- [Qwen3-4B model card](https://huggingface.co/Qwen/Qwen3-4B)
- [GKE GPU serving with vLLM](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/serve-llama-gpus-vllm)
- [vLLM benchmark tooling](https://github.com/vllm-project/vllm/blob/main/docs/benchmarking/cli.md)
- [vLLM optimization and tuning](https://docs.vllm.ai/en/latest/configuration/optimization/)
- [GCP accelerator-optimized VM pricing](https://cloud.google.com/products/compute/pricing/accelerator-optimized)
- [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing)
