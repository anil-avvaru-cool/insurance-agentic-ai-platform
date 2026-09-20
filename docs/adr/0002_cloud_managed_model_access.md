# ADR 0002: Cloud-managed model access only

Date: 2026-09-19  
Status: Accepted; supersedes ADR 0001's direct-provider selection.

## Decision

All generation and embedding inference must use a cloud-managed service, such
as AWS Bedrock, Azure AI Foundry, or Google Cloud Vertex AI. Direct model-vendor
APIs are prohibited, including as a fallback. Hosting the application on a
cloud does not satisfy this requirement if inference leaves for a direct API.

AWS Bedrock Converse is the implemented application language provider. The
existing Bedrock embedding and retrieval probes remain cloud-managed. Azure
and Google Cloud are future adapter implementations, not supported values today.
Model requests remain behind application-owned adapters; authorization,
confirmation, urgency, and action eligibility remain deterministic.

## Configuration and authentication

Set `LLM_PROVIDER=bedrock`, `BEDROCK_MODEL_ID`, `AWS_REGION`,
`LLM_TIMEOUT_SECONDS`, and `LLM_MAX_OUTPUT_TOKENS` in `.env` or deployment
configuration. Missing required settings fail fast. `LLM_PROVIDER=disabled`
keeps the structured offline demonstration available. Other providers fail
configuration validation; no direct-provider credentials or URLs are used.

AWS credentials come from the standard SDK profile/role chain; deployments
use scoped IAM roles with `bedrock:InvokeModel` access to the selected model
and, when applicable, its inference profile and destination model resources.
The AWS SDK resolves regional service endpoints and signs requests.

## Interpretation contract

The adapter uses Converse with a single forced `interpretation` tool to collect
structured data. This is an output format, not an executable business action.
The model must support forced named tool selection. The example model remains
`amazon.nova-lite-v1:0`; this is a development candidate, not quality approval.

The adapter inlines the JSON schema definitions and limits root schema keys
for Nova compatibility. Pydantic validates the full returned contract locally,
and exact evidence checks reject unsupported facts. Truncation, refusals,
unexpected output, SDK errors, and invalid schemas fail safely through the
existing workflow fallback. Usage and model/prompt versions remain recorded.
Application storage and LangGraph retain workflow state.

## Validation and rollout

Offline tests validate the SDK contract, configuration allowlist, evidence
checks, provider failure handling, and insurance workflow controls. Run the
nine-case synthetic live evaluation with an authorized AWS profile/role before
accepting model quality. No automatic model/provider substitution is allowed.
Re-evaluate quality, latency, regional availability, and cost for any new model.
The AWS cost worksheet remains illustrative; refresh prices before deployment.

## References

- [Amazon Nova tool definitions and supported schema](https://docs.aws.amazon.com/nova/latest/userguide/tool-use-definition.html)
- [Bedrock tool choice](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolChoice.html)
- [Prior decision, retained as history](0001_model_selection_and_provider_abstraction.md)
