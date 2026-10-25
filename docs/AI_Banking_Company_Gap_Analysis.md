# Banking Company — Principal Software Engineer: Gap Analysis and POCs

Review date: October 25, 2026. Scope: repository evidence against the supplied [JD](JD_AI_Banking_Company.md), not an assessment of the author's full professional experience.

## Assessment

The GCP inference plan is a useful foundation for this role: reproducible vLLM deployment, streaming, GPU telemetry, workload benchmarking, one controlled optimization, and two-GPU tensor parallelism. The JD extends substantially beyond that lab into a reusable, multi-tenant inference platform and its operation across teams.

**Highest priorities:** complete the measured baseline; build a tenant-aware inference gateway and policy router; demonstrate quality-gated quantization and safe rollout; exercise SLOs, overload, and recovery; establish governed AI-assisted engineering workflows.

Repository code and runbooks provide starting components. The reviewed GCP documents explicitly describe a proposed deployment and do not claim performance results. Implementation files do not establish successful deployment, production scale, or operational experience. No live cloud inspection or benchmark execution was performed for this review.

## Evidence reviewed

| Source | Evidence and relevance |
| --- | --- |
| [Inference plan](gcp/PHASE_1_INFERENCE_PLAN.md) | Single L4/BF16 baseline, controlled tuning, cost methodology, two-GPU learning lab |
| [Inference implementation guide](gcp/PHASE_1_INFERENCE_FIG.md) | Architecture, telemetry readiness gate, 16 workload cells and 48 measured runs, artifact and cleanup requirements |
| [GCP Terraform](../infra/pocs/gcp_inference/README.md), [serving](../infra/pocs/gcp_inference/serving/README.md), [benchmark runbook](../infra/pocs/gcp_inference/serving/BENCHMARK.md) | Existing IaC, deployment templates, dashboard and benchmark preparation; execution evidence remains required |
| [Repository README](../README.md), [architecture](ARCHITECTURE.md), [Bedrock adapter](../src/adapters/models/bedrock.py) | Python application, validation, human review and managed-provider integration; application workflows differ from inference platform controls |
| [AWS POC](aws/PHASE_1_AWS_POC_PLAN.md), [online evaluation](aws/ONLINE_RAG_EVALUATION.md), [judge evaluation](aws/RAG_JUDGE_EVALUATION.md) | Reusable corpus, evidence capture and evaluation patterns; live deployment/judge baseline remain pending in reviewed documentation |
| [Model access ADR](adr/0002_cloud_managed_model_access.md), [self-hosted inference exception](adr/0003_controlled_self_hosted_inference.md), [agent guidance](../Agents.md) | Managed-service policy, permitted vLLM learning work, configuration and repository constraints |
| [Databricks POC](aws/databricks_poc_plan.md) | Supporting data engineering exercise; lower priority for this inference-focused JD |

## JD coverage and gaps

“Partial” means scoped plans or reusable components exist; it does not mean the JD capability has been demonstrated. “Missing” means no substantive evidence found in the reviewed material.

| JD capability | Current coverage | Gap to demonstrate | Experiment objective |
| --- | --- | --- | --- |
| High-throughput serving, batching, scheduling, streaming, caching | Partial: detailed vLLM lab and manifests | Measured saturation, mixed arrivals, cancellation, fairness and sustained load | reproducible inference baseline, tenant-aware GenAI gateway and SDK, SLOs, overload, autoscaling and recovery |
| Gateway: authentication, authorization, quotas, shaping, policy hooks | Partial: application auth and AWS IAM query endpoint | Inference-specific identity, model entitlement, token budgets, bounded admission and shared API | tenant-aware GenAI gateway and SDK |
| Intelligent routing across open and vendor models | Missing: selected Bedrock adapter and isolated vLLM lab | Versioned quality/cost/latency policies, approved fallback and circuit breakers | policy-based multi-backend routing |
| GPU/KV-cache efficiency and prefill/decode tuning | Partial: telemetry and one proposed tuning experiment | Profiling evidence, cache hit rates, allocator/fragmentation diagnosis and workload-specific tuning | reproducible inference baseline, GPU profiling and advanced decode optimization |
| INT8/INT4 compression with preserved quality | Deferred follow-up | Compatible format selection, calibration where needed, evaluation, rollout and rollback | quality-gated quantization |
| Distributed inference and disaggregated serving | Partial: two-GPU tensor parallelism planned | Actual communication measurements, separate prefill/decode workers and KV transfer/offload | GPU profiling and advanced decode optimization, prefill/decode disaggregation and KV offload |
| Multi-tenancy, backpressure, priorities and tail latency | Missing at inference layer | Noisy-neighbor isolation, queue bounds, admission fairness and p99 under overload | tenant-aware GenAI gateway and SDK, SLOs, overload, autoscaling and recovery |
| Autoscaling across GPU/CPU fleets | Baseline intentionally fixed at one replica | Queue-based pod scaling, node provisioning, cold starts, capacity limits and draining | SLOs, overload, autoscaling and recovery |
| SLOs/SLAs and operational excellence | Partial: metrics and troubleshooting runbooks | SLO definitions, error budgets, capacity envelope, incident drills and bounded remediation | SLOs, overload, autoscaling and recovery |
| Performance and cost observability | Partial: latency histograms, throughput, GPU/KV memory and estimated cost | Per-tenant attribution, routing traces, cache hits, rejected/cancelled demand and regression gates | tenant-aware GenAI gateway and SDK, policy-based multi-backend routing, SLOs, overload, autoscaling and recovery |
| Registry/artifacts, canary, A/B and shadow traffic | Partial: image/model pins; single replica uses `Recreate` | Versioned release bundle, quality gates, shadow isolation, canary and tested rollback | quality-gated quantization, safe model delivery and developer self-service |
| SDK/service integrations and reusable platform components | Partial: Python adapters, API contracts and tests | Stable inference SDK, streaming/error contracts, compatibility and developer onboarding | tenant-aware GenAI gateway and SDK, safe model delivery and developer self-service |
| Security, data handling, supply chain and resiliency | Partial: scoped identities, deterministic checks and revision pins | Tenant-aware cache controls, inference policy enforcement, artifact provenance and failure tests | tenant-aware GenAI gateway and SDK, safe model delivery and developer self-service, governed agentic engineering workflow |
| Agentic AI engineering adoption and governance | Missing as an engineering operating model | Authorized tools, review controls, auditable changes and cross-team adoption evidence | governed agentic engineering workflow |
| Principal-level influence and business outcomes | Architecture and plans provide communication samples | Decision ownership, stakeholder alignment, adoption and measured business outcomes | All; especially safe model delivery and developer self-service, governed agentic engineering workflow |
| 7+ years and production experience | Not assessable from repository | Employment/project history and verifiable delivery/operations examples | Experience narrative |

## Recommended POCs

These are proposed learning experiments. Targets below are lab acceptance criteria, not Banking Company requirements or achieved results. Freeze performance/quality thresholds before running each comparison. Effort estimates are hands-on engineering days after access and quota are available; provisioning delays are additional.

### Complete the reproducible inference baseline

- **Priority/dependency:** first; existing Phase 1 scope. Approximately 3–5 days, one L4 initially.
- Execute the existing four workload shapes × four concurrency caps × three repetitions, retaining failed/skipped cells. Complete one hypothesis-driven batching, prefix-cache or chunked-prefill experiment.
- Preserve client/server timing boundaries, actual token lengths, pins, UTC windows, raw results, GPU/RAM telemetry and full declared serving cost.
- **Acceptance:** both smoke tests pass; telemetry readiness gate passes; all 48 baseline runs have results or documented exclusion; matched optimization runs support a decision with variability and regressions reported.
- Complete the planned two-GPU lab afterward as separate model/hardware evidence. Do not interpret 4B versus 14B as an isolated optimization.

### Tenant-aware GenAI gateway and SDK

- **Priority/dependency:** high; can begin with fake backends while reproducible inference baseline runs. Approximately 4–6 days; CPU work plus one GPU for end-to-end checks.
- Expose a versioned inference contract with non-streaming and streaming support. Derive tenant identity from validated credentials; enforce tenant/model entitlements, context/output limits, request rate, token budgets, deadlines and bounded queues.
- Reserve estimated token budget at admission and reconcile actual usage; bound concurrent reservations. Define cancellation, timeout and partial-stream billing behavior.
- Provide a small Python SDK, stable error schema, correlation IDs, policy hooks and per-tenant usage/cost records. Keep prompts and credentials out of ordinary logs.
- Test two synthetic tenants, including one abusive tenant. Separate cache namespaces or otherwise prevent unauthorized reuse and data exposure; test output isolation and timing-risk assumptions.
- **Acceptance:** invalid identity/entitlement is rejected before backend invocation; configured limits hold under concurrent requests; overload returns documented errors; disconnect releases work; valid tenant traffic meets its predefined latency budget under noisy-neighbor load.
- **Artifacts:** contract, SDK examples, isolation/load results and tenant cost reconciliation. Provider charges and allocated shared GPU cost must remain separately identified.

### Policy-based multi-backend routing

- **Priority/dependency:** high; tenant-aware GenAI gateway and SDK plus a task-specific quality corpus. Approximately 4–6 days.
- Connect the isolated vLLM lab and a managed Bedrock backend through explicit adapters. Account for regional/network latency. Normalize only the supported API subset; do not assume Responses API and Converse semantics are interchangeable.
- Begin with deterministic policies using tenant entitlement, task class, data policy, context size, observed health, latency and cost. Add learned routing only if it beats this baseline on held-out tasks.
- Fail closed when no approved backend is available. Add circuit breakers and bounded retries before streaming begins; never silently restart an emitted stream against another model.
- **Acceptance:** compare fixed-backend and routed policies on the same held-out corpus; report quality, p95 latency, successful throughput and cost. Demonstrate denied fallback, backend timeout, breaker opening/recovery and routing-decision traceability.
- **Decision gate:** adopt only if the predefined quality floor and reliability constraints hold and the selected cost/latency objective improves. A larger model is not automatically the quality reference.

### Quality-gated quantization

- **Priority/dependency:** high; reproducible inference baseline and task-specific evaluation. Approximately 3–5 days, one L4; use two GPUs only for a justified follow-up.
- Compare BF16 with one supported INT8 or INT4/weight-only candidate of the same model lineage. Pin quantized artifact provenance, tokenizer and any calibration data; keep calibration and evaluation sets separate.
- Select the format after checking model, L4 hardware and pinned engine compatibility. Available formats and kernels vary; use the [vLLM compatibility guidance](https://docs.vllm.ai/en/latest/features/quantization/).
- Reuse AWS evaluation patterns, but add enough held-out tasks to detect relevant regressions. The six-case judge baseline alone cannot establish quantization quality.
- **Acceptance:** predeclare tolerable quality loss and protected cases; report task quality, schema validity, memory, p95 TTFT, throughput and cost on matched workloads. For example, require no new protected-case failures and at most a two-percentage-point task pass-rate loss, with uncertainty reported.
- Produce a rollback-ready candidate bundle for safe model delivery and developer self-service even if the result rejects quantization. Smaller weights do not guarantee lower latency.

### SLOs, overload, autoscaling and recovery

- **Priority/dependency:** high; reproducible inference baseline and tenant-aware GenAI gateway and SDK. Approximately 4–6 days; temporarily budget two GPU replicas for scaling/failover.
- Define availability, TTFT and completion SLOs by workload/tenant tier. Specify eligible requests, latency boundaries, measurement window and treatment of policy rejects, overload, cancellations and partial streams.
- Extend the closed-loop concurrency matrix with scheduled arrival-rate ramps, bursts, mixed lengths and a soak test. Report offered load, queue time, dropped demand and p99; avoid hiding overload through client slowdown.
- Scale from queue/in-flight/token-demand signals, then measure pod readiness, model load, node provisioning and scale-down draining. Keep fixed-hardware measurements separate.
- Inject worker termination, GPU OOM, backend timeout and unavailable capacity. Test alerts and bounded remediation with cooldown and escalation.
- **Acceptance:** publish the maximum arrival rate meeting chosen SLOs; queues remain bounded above it; warm-replica and cold-capacity recovery times are measured; no retry storm occurs; an incident drill produces a timeline and runbook correction.
- Report achieved lab SLOs separately from any proposed contractual SLA. A short test does not demonstrate long-term availability.

### Safe model delivery and developer self-service

- **Priority/dependency:** medium; tenant-aware GenAI gateway and SDK and quality-gated quantization. Approximately 3–5 days.
- Create a release manifest covering model/tokenizer commits, image digest, engine configuration, evaluation corpus, benchmark artifacts and policy version. Add provenance, license review and dependency/image scanning.
- Exercise synthetic shadow traffic, then a tenant-scoped canary with quality/error/latency rollback gates. Shadow output must not become customer output or execute tools; account for duplicate inference cost.
- Use an explicit release controller or routing configuration: one GPU and `Recreate` cannot demonstrate overlapping canary replicas.
- **Acceptance:** deliberately bad release is blocked or rolled back; in-flight streams have defined behavior; previous artifact/configuration is recoverable. A second sample client onboards through the documented SDK and entitlement process without bespoke gateway changes.
- **Artifacts:** CI gates, compatibility tests, rollback drill, onboarding guide and one-page decision record.

### GPU profiling and advanced decode optimization

- **Priority/dependency:** medium; reproducible inference baseline. Approximately 3–5 days; GPU topology determines scope.
- Profile prefill-heavy and decode-heavy workloads; collect GPU traces and CPU flame graphs. Separate compute, memory, scheduling and communication bottlenecks.
- Test one justified change: compilation/acceleration, KV-cache configuration, optimized sampling or compatible speculative decoding. Hold model quality and workload controls constant and include compilation/draft-model overhead.
- A TensorRT-style comparison is optional after verifying model/API/hardware support; follow [NVIDIA performance tuning guidance](https://nvidia.github.io/TensorRT-LLM/performance/performance-tuning-guide/index.html).
- **Acceptance:** link a profiler observation to a measured change in latency/throughput/memory and explain regressions. Record cache hit/miss data and allocator evidence where available; GPU allocated memory alone does not measure fragmentation. Kernel modification is warranted only by an identified bottleneck.

### Prefill/decode disaggregation and KV offload

- **Priority/dependency:** advanced; reproducible inference baseline and GPU profiling and advanced decode optimization. Approximately 5–8 days; at least two compatible GPU workers, preferably a separate multi-node/network experiment.
- Begin with a model that fits independently on each worker. Compare one prefill worker plus one decode worker against equal-total-GPU colocated serving/replicas.
- Pin the KV-transfer connector and validate support before provisioning. Record topology, link bandwidth, KV-transfer time, TTFT, inter-token latency, throughput and total cost.
- Explore KV offload separately to avoid confounding changes. Include transfer failure, stale-state isolation and backpressure tests.
- **Acceptance:** matched mixed-length workloads show when disaggregation helps or loses; report transfer overhead and failure recovery. Same-node results do not establish multi-node behavior. vLLM currently labels [disaggregated prefilling experimental](https://docs.vllm.ai/en/latest/features/disagg_prefill/).
- Two-GPU tensor parallelism shards computation; it does not demonstrate separate prefill/decode workers.

### Governed agentic engineering workflow

- **Priority/dependency:** high; start alongside reproducible inference baseline. Approximately 3–5 days for a pilot, followed by adoption observation.
- Pilot an enterprise-authorized assistant for PR review, test suggestions, release readiness or incident triage. Use synthetic repository examples and least-privilege access.
- Define allowed tools/data, human approval before merge/deployment, independent validation, prompt-injection handling, secret controls and an auditable record of suggestions, checks, reviewer decisions and outcomes.
- Evaluate at least ten representative seeded changes/incidents, including insecure suggestions and misleading repository instructions. Agents must not approve their own work or bypass checks.
- **Acceptance:** prohibited actions/data access are blocked; accepted changes link to human review and validation; report defect detection, false positives, review time and escaped defects against a manual baseline.
- Produce reusable standards and an adoption proposal. Insurance workflow human review is useful background but does not establish AI-assisted SDLC governance or multi-team adoption.

## Execution order and scope choices

| Stage | Work | Exit evidence |
| --- | --- | --- |
| 1 | reproducible inference baseline; start governed agentic engineering workflow pilot | Reproducible GPU results and governed engineering process |
| 2 | tenant-aware GenAI gateway and SDK → policy-based multi-backend routing; quality-gated quantization | Tenant controls, routing tradeoffs and quality/performance comparison |
| 3 | SLOs, overload, autoscaling and recovery → safe model delivery and developer self-service | Capacity/SLO report, incident drill and rollback/self-service demo |
| 4 | GPU profiling and advanced decode optimization → prefill/decode disaggregation and KV offload | Profiler-backed optimization and distributed-serving tradeoffs |

- Keep the existing Phase 1 lab small; add separate follow-up plans rather than making every JD capability a prerequisite for its completion.
- If time is limited, prioritize the inference baseline, tenant-aware gateway, policy-based routing, quality-gated quantization, SLO/recovery experiments and governed agentic engineering workflow. Databricks, additional RAG breadth and larger-model-only deployments provide less direct evidence for this JD than gateway, routing and inference operations.
- Run CPU/fake-backend tests first. Provision extra GPUs only for the relevant comparison, verify regional capacity/pricing, set a session budget and teardown time, and export evidence before cleanup. No new hourly price is assumed here.
- Configure through `.env`/`example.env`; keep secrets, raw prompts and environment-specific endpoints out of committed artifacts. Follow repository naming, UV and no-commit guidance; do not enable POC bucket versioning.

## Decisions to resolve before integration

- **Model-access policy:** [ADR 0003](adr/0003_controlled_self_hosted_inference.md) amends ADR 0002 with a scoped self-hosted inference exception. Cloud-managed inference remains the application default. Approved vLLM deployments are permitted for isolated experiments and the tenant-aware gateway and policy-based routing experiments using synthetic/public evaluation data. Application integration requires separate adapter validation and quality acceptance. Backend selection and fallback must follow explicit policy; unapproved substitution remains prohibited. The application provider allowlist remains unchanged.
- **State dependency:** the GCP guide uses an AWS S3 backend and requires recreating shared state infrastructure. It is therefore a dual-cloud provisioning dependency despite the broader independent-cloud architectural goal. Record this lab exception and reconcile surviving resources before fresh initialization.
- **API compatibility:** verify the pinned server and benchmark client support the chosen Responses fields and streaming behavior. Gateway and Bedrock adapters require their own contract tests.
- **Evidence quality:** planned charts, Terraform tests and synthetic functional checks cannot substantiate production scale, business adoption or historical experience. Retain failures and negative optimization results.

## Principal-level evidence package

- For each POC: problem, hypothesis, alternatives, architecture decision, pinned configuration, reproducible command, raw evidence, tradeoff decision and remaining risks.
- Provide an executive scorecard: cost per successful task, SLO-compliant goodput, quality pass rate, tenant fairness, recovery time and onboarding effort. Keep token cost alongside task quality and business usefulness.
- Present a roadmap with owners, dependencies and success criteria; collect actual reviewer/consumer feedback. A solo POC supports an adoption proposal, not a claim of enterprise adoption.
- Pair the portfolio with truthful professional examples of system ownership, production incidents, mentoring and stakeholder influence. Repository work cannot replace the JD's experience requirements.

## External documentation check

Official documentation was checked during this review to ground tool choices. Recheck against pinned versions before implementation; these links do not certify the repository's deployment.

- [vLLM production metrics](https://docs.vllm.ai/en/latest/usage/metrics/): verify metric availability and names for the selected release.
- [GKE Inference Gateway overview](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/about-gke-inference-gateway): candidate endpoint-selection infrastructure. Endpoint selection alone does not establish a quality/cost-aware model router or complete tenant governance.
- [TensorRT LLM quantization](https://nvidia.github.io/TensorRT-LLM/latest/features/quantization.html): candidate toolchain for compatible model/hardware combinations; select through evaluation rather than format availability alone.
