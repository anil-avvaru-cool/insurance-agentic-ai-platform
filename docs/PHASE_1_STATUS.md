# Phase 1 implementation review

Reviewed September 13, 2026. The repository previously contained only the auto
intake/confirmation contracts, urgency screening, and nine unit tests.

## Implemented in this increment

| Area | Working local behavior | Evidence |
|---|---|---|
| HTTP contracts | Create/resume conversations, accept messages and confirmations, read tasks, list/decide reviews | FastAPI OpenAPI and integration tests |
| Ownership | Customer ownership checked for conversations, tasks, policies, vehicles, locations, contacts and claims; employee-only review routes | Cross-customer and role-denial tests |
| Intake | Explicit sourced facts, partial drafts, optimistic versions, exact draft confirmation | Domain and stale-confirmation tests |
| Workflow | Pure LangGraph urgency, intake and triage nodes; durable application state across restarts | Local journey and restart tests |
| Queue | Atomic task/outbox acceptance, request deduplication, serialized local workers | Duplicate and replay tests |
| Submissions | Durable original snapshot and action ID, independent synthetic receipts, timeout reconciliation | External-success/local-crash and timeout tests |
| Urgency | Priority handoff before complete intake, sticky minimum urgency, new urgent facts accepted during uncertain submission | Early urgency and pending-submission update tests |
| Review | Accept/amend/reject/request-information, stale version rejection, decision deduplication, reviewer audit, current context | Review branch and follow-up tests |
| Service | Authorized synthetic policy/claim status; fixed report-loss guidance; unsupported-question employee handoff | Service lookup, access and fallback tests |
| Interfaces | Local customer form and employee queue; resume and task refresh | HTTP page check; manual browser walkthrough still required |

A reviewed recommendation is the final local next step. The synthetic adapter
does not assign claims. Receipts explicitly identify the original submitted
draft version; subsequent changes are context for employee review and are not
silently written to the core.

## Still pending

| Milestone | Remaining work / dependency |
|---|---|
| 1A completion | Model/provider adapter and evaluated natural-language extraction; service/workflow integration beyond deterministic fixtures; persistent graph checkpoints and interrupt/resume; pre-auth urgency/help contract; versioned configurable team/content catalogs; browser walkthrough |
| 1B deployment spike | AWS account/region and networking decisions; Terraform roots and backend; ECS/API Gateway, AgentCore adapter, PostgreSQL checkpoints, SQS; Bedrock knowledge base and S3 Vectors ingestion/retrieval verification |
| 1C staging | Real identity and delegated employee scope; approved claims sandbox; isolated action service identity; constrained evidence upload/quarantine/scanning; distributed outbox/leases/retries/DLQ; telemetry; CI/release automation; recovery and RAG/security evaluations |
| 1D pilot | Approved rules/catalogs and language; staffed employee queue and deadlines; pilot cohort, numerical quality/latency/cost gates; production configuration, restore rehearsal and owner acceptance |
| 1E property | Property schema, habitability/hazard rules, fixtures and evaluated routing after auto gates |

No AWS resources were provisioned and no pilot or complete Phase 1 acceptance is
claimed. SQLite persistence verifies the local business recovery contract; it
is not evidence of PostgreSQL/LangGraph checkpoint recovery or AWS durability.
The HTTP evidence-upload endpoint is deliberately not exposed until protected
storage is implemented.

## Verification

Verified this increment: **9 unit tests and 15 integration tests passed**.
Configured API startup and OpenAPI/page delivery also passed. API tests ran
outside the execution sandbox because its asynchronous test-client loop stalled.
A manual browser walkthrough and deployed checks have not been performed.

Run the two unittest commands in [README](../README.md). Tests exercise actual
ASGI routes and separate temporary application/core databases, including process
reconstruction at submission and review boundaries. No cloud or model calls are
required. The UI is served by the API and uses text-only rendering for responses.

Implementation references: [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
and [FastAPI bearer authentication](https://fastapi.tiangolo.com/tutorial/security/first-steps/).
Production checkpoint/interrupt behavior must additionally satisfy the sources
and acceptance cases in the [implementation guide](PHASE_1_IMPLEMENTATION_GUIDE.md).
