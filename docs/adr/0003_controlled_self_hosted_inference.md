# ADR 0003: Controlled self-hosted inference exception

Date: 2026-10-25  
Status: Accepted; amends ADR 0002 for the scopes below.

## Decision and scope

Cloud-managed inference remains the insurance application's default. Approved
self-hosted vLLM deployments are permitted for isolated inference experiments,
the tenant-aware inference gateway, and policy-based multi-backend routing
experiments. These scopes use synthetic or public evaluation data only.
Public data must also be licensed and approved for the intended use.

Model licensing and hosting are separate decisions. Open-source or open-weight
models accessed through a cloud-managed inference service can satisfy ADR 0002
without this exception. Self-hosted vLLM on managed Kubernetes requires this
exception; cloud hosting alone does not satisfy ADR 0002.

This decision does not enable vLLM in the insurance application. Its supported
provider settings remain `bedrock` and `disabled`. Direct model-vendor APIs
remain prohibited, including as fallback. Generation and embedding endpoints
must each be approved; approval of one does not authorize the other.

## Deployment approval and boundaries

Before connecting a real backend, record an approved deployment manifest with:

- Owner, purpose, environment, allowed data classes and review date before use.
  Review again before expanding scope or changing model, engine or routing.
- Approved endpoint reference, region and network boundary; keep actual
  environment-specific endpoints and credentials in ignored configuration.
- Model and tokenizer revisions, license/use restrictions, artifact provenance,
  serving image digest, engine settings and evaluation evidence.
- Access policy, resource/token limits, session budget, teardown time and
  disable/rollback procedure. Unregistered backends are denied by default.

Keep backends private and accessible through authenticated, authorized clients
or the gateway. Allowlist exposed API paths; restrict management, profiling and
distributed-worker interfaces to trusted operational access. A vLLM API key
alone is insufficient. Enforce tenant/model entitlements and admission limits;
isolate tenant caches and keep prompts, credentials and sensitive outputs out
of ordinary logs. Configuration uses `.env`/`example.env`, fails fast when
required values are missing, and contains no hardcoded environment endpoints.

## Adapter and application acceptance

Use application-owned adapters with an explicitly supported API subset.
OpenAI-compatible HTTP syntax does not establish Bedrock Converse equivalence.
Validate structured interpretation output, local schema and evidence checks,
timeouts, refusals, truncation, cancellation, errors and streaming behavior
against the pinned model/engine combination. Preserve deterministic business
authorization, confirmation, urgency and action eligibility.

Before enabling insurance application use, record a separate acceptance decision
covering allowed application data, security controls, held-out task quality,
schema/evidence validity, latency, reliability, cost and tested rollback.
Predeclare thresholds and retain negative results. Implement and validate the
adapter and configuration allowlist only after this acceptance gate; this ADR
does not claim that implementation or quality acceptance exists today.

## Routing and fallback

- Start with explicit backend selection. Register approved routes by tenant,
  task, data class, model capability and deployment; version the policy.
- Automatic fallback remains disabled unless separately accepted with tested,
  explicit source/destination routes and the same entitlement/data constraints.
- Fail closed when no approved backend is available. Bound retries by request
  deadline and budget; never restart an emitted stream against another model.
- Record policy version, selected backend/model revision, routing reason,
  usage, errors and correlation ID without raw prompt logging.
- Test denied routes, unavailable backends, timeouts, circuit-breaker recovery
  and disable/rollback before accepting routing behavior.

## Consequences and references

The lab and gateway can demonstrate open-model serving and routing while the
insurance application retains its existing provider contract. Self-hosting
adds responsibility for artifact security, capacity, isolation and recovery.
Deployment registration, adapter implementation and acceptance evidence remain
required work, rather than outcomes established by this policy decision.

- [ADR 0002](0002_cloud_managed_model_access.md)
- [Gap analysis and experiment objectives](../AI_Banking_Company_Gap_Analysis.md)
- [vLLM security guidance](https://docs.vllm.ai/en/latest/usage/security/)
- [vLLM structured outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/)
