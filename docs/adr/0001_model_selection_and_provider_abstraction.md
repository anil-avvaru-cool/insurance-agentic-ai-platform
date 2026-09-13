# ADR 0001: Configurable model selection, starting with GPT-5.4 mini

Date: 2026-09-13  
Status: Accepted for the POC; integration is not yet implemented.

## Context

The insurance POC needs intent interpretation, structured intake extraction,
tool calling, and answers grounded in approved documents. Model quality,
pricing, latency, and availability change over time. Choosing a starting model
must not permanently bind the domain or orchestration to that model or provider.

Previous plans assumed Bedrock generation and used Nova Lite v1 as a cost
example. This decision supersedes that generation assumption; AWS hosting and
the planned retrieval stack remain applicable.

## Decision

Start with `gpt-5.4-mini` through the OpenAI Responses API. This is the initial
POC selection, not a permanent model standard or a production approval.

Keep model access behind an application-owned adapter under `src/adapters/`.
The adapter translates provider requests, responses, tool calls, usage, and
errors into shared application contracts. Domain rules and LangGraph workflow
logic must not depend on a provider SDK or a particular model identifier.
Implement the OpenAI adapter first; add other providers when needed.

Select the provider and model through required configuration, with planned keys
`LLM_PROVIDER`, `LLM_MODEL`, and `OPENAI_API_KEY`. Local development uses `.env`
and a documented `example.env`; deployed credentials use Secrets Manager.
Missing required configuration must fail fast, with no silent model fallback.
These keys will be added when the adapter is implemented.

Keep AWS application hosting and Bedrock Knowledge Bases retrieval with Titan
Text Embeddings V2 and S3 Vectors. Retrieved passages feed the configured
generation adapter. An embedding model change is a separate decision because
it can require reindexing. OpenAI API generation requires outbound connectivity
and separate OpenAI billing and data-processing configuration.

Deterministic Python code continues to enforce urgency rules, authorization,
validation, confirmation, and action eligibility. A model change cannot change
these responsibilities.

## Responses API rationale and implementation notes

Use Responses API rather than Chat Completions for the initial OpenAI
integration. OpenAI recommends Responses for new projects; Chat Completions
remains supported. Responses fits the planned multi-turn reasoning and tool
calling workflows and provides optional built-in tools. Model integration has
not yet been implemented, so this is an initial API choice rather than a
migration of existing calls.

- Keep Responses request and output types, tool-call translation, streaming
  events, usage, and errors inside the OpenAI adapter. Shared application
  contracts must remain independent of the provider API.
- Keep LangGraph and application-owned durable storage responsible for workflow
  state, customer confirmation, and action execution. A model tool call is a
  proposed action; deterministic authorization and validation still apply.
- Start with application-managed conversation context and `store: false`.
  Replay the relevant messages, tool calls, tool results, and reasoning items
  needed for continuation. OpenAI-hosted conversation state is optional and is
  not the system of record. Disabling response storage does not by itself
  establish Zero Data Retention.
- Continue using Bedrock Knowledge Bases for retrieval and pass approved
  retrieved passages to Responses. Choosing Responses does not require adopting
  OpenAI file search or other hosted tools.
- Handle Responses-specific tool schemas, tool-result call identifiers, and
  typed streaming events explicitly in the adapter. Validate these contracts
  when implementing it; Chat Completions handlers are not drop-in replacements.

The tradeoff is provider-specific adapter work. Keep that work isolated so
future provider changes do not require rewriting business rules. Measure
quality, latency, and cost through the existing evaluation plan rather than
assuming the API choice alone improves them.

## How model choices evolve

Reassess the selection when new models, material price changes, measured quality
or latency problems, or availability changes warrant it. Evaluate candidates
against the same versioned synthetic cases and approved-source corpus:

- Intake extraction accuracy, including unknown and conflicting facts.
- Valid structured outputs and correct tool names and arguments.
- Grounded answers, citations, and appropriate handling of missing evidence.
- Injection resistance and preservation of authorization boundaries.
- End-to-end latency, throttling, retries, and task completion rate.
- Cost per completed journey, including repeated context, reasoning tokens,
  retries, and any provider tool charges.

Compare candidates with the current model using explicit acceptance thresholds.
Record the evaluation results and selected provider/model version before a
controlled rollout. Pin a tested snapshot where supported, retain the previous
configuration for rollback, and record model, prompt, schema, and rule versions
with each release. Do not automatically switch to newly released models or
route failures to an unevaluated provider.

Record subsequent selections in a new ADR that references this one; retain the
decision history. Price alone is insufficient if task quality regresses.

## Cost basis and consequences

At the published standard OpenAI API rates checked on 2026-09-13, GPT-5.4 mini
costs $0.75 per million input tokens and $4.50 per million output tokens.
For illustration, 20,000 uncached input tokens and 3,000 total billed output
tokens across a complete conversation cost $0.0285, or $28.50 for 1,000
conversations. This is a workload assumption, not a spending cap; include
reasoning in billed output and account for retries and regional pricing where
applicable. Infrastructure, retrieval, embeddings, and additional tool fees
are excluded. Recheck rates before deployment.

The existing AWS cost worksheet uses Nova Lite v1 generation and therefore does
not represent the total cost of this selection. Recalculate its generation line
and combined AWS/OpenAI budget before provisioning.

This approach allows model replacement without rewriting business rules, but
adapters still require compatibility testing: configuration alone cannot make
different providers' APIs and behavior interchangeable. The POC must establish
quality through evaluations; no comparative superiority is assumed.

## Alternatives considered

- Claude Haiku 4.5 on Bedrock: a candidate for later comparison; not the initial
  choice selected for this POC.
- Nova Lite v1: the prior cost placeholder, without task-quality approval.
- Hardcoded model calls in workflow nodes: simpler initially, but make provider
  changes and consistent evaluation harder.

## References

- [OpenAI Responses API migration and comparison guide](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [GPT-5.4 mini capabilities and pricing](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
- [Phase 1 implementation guide](../PHASE_1_IMPLEMENTATION_GUIDE.md)
- [Existing AWS cost worksheet](../PHASE_1_AWS_COST_ESTIMATE.md)
