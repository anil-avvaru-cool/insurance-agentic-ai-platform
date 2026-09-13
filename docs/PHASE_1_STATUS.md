# Phase 1 implementation review

Reviewed September 13, 2026. Resumed and completed the interrupted local 1A
implementation. The synthetic journey gate passes; live natural-language quality
evaluation remains unverified because no model API key is configured.

## Implemented in this increment

| Area | Working local behavior | Evidence |
|---|---|---|
| HTTP contracts | Create/resume conversations, accept messages and confirmations, read tasks, list/decide reviews | FastAPI OpenAPI and integration tests |
| Ownership | Customer ownership checked for conversations, tasks, policies, vehicles, locations, contacts and claims; employee-only review routes | Cross-customer and role-denial tests |
| Intake | Explicit sourced facts, partial drafts, optimistic versions, exact draft confirmation | Domain and stale-confirmation tests |
| Workflow | Persistent SQLite LangGraph planning and employee interrupt/resume; authoritative application recovery across separate commits | Restart, orphan-checkpoint and rolled-back decision tests |
| Queue | Atomic task/outbox acceptance, request deduplication, serialized local workers | Duplicate and replay tests |
| Submissions | Durable original snapshot and action ID, independent synthetic receipts, timeout reconciliation | External-success/local-crash and timeout tests |
| Urgency | Priority handoff before complete intake, sticky minimum urgency, new urgent facts accepted during uncertain submission | Early urgency and pending-submission update tests |
| Review | Accept/amend/reject/request-information, stale version rejection, decision deduplication, reviewer audit, current context | Review branch and follow-up tests |
| Service | Authorized synthetic policy/claim status; fixed report-loss guidance; unsupported-question employee handoff | Service lookup, access and fallback tests |
| Interfaces | Customer form, natural-language input, pre-auth help and employee queue; resume and task refresh | Chromium end-to-end walkthrough passed |
| Language | Configurable OpenAI Responses adapter, strict sourced extraction, unconfirmed facts, conflicts and safe fallback | Mock transport and workflow tests; nine-case live evaluation runner ready |
| Catalogs | Versioned team routing and customer source selection with audience, approval and effective-date filters | Withdrawal/access/expiration tests |
| Pre-auth help | Status-only urgency handoff, capability-based retries and attachment to one authenticated owner | Deduplication and cross-owner denial tests |

A reviewed recommendation is the final local next step. The synthetic adapter
does not assign claims. Receipts explicitly identify the original submitted
draft version; subsequent changes are context for employee review and are not
silently written to the core.

## Still pending

| Milestone | Remaining work / dependency |
|---|---|
| 1A live-model validation | Run the nine synthetic language evaluation cases with a configured model API key; offline mocks do not establish extraction accuracy or service-selection quality |
| 1B deployment spike | AWS account/region and networking decisions; Terraform roots and backend; ECS/API Gateway, AgentCore adapter, PostgreSQL checkpoints, SQS; Bedrock knowledge base and S3 Vectors ingestion/retrieval verification |
| 1C staging | Real identity and delegated employee scope; approved claims sandbox; isolated action service identity; constrained evidence upload/quarantine/scanning; distributed outbox/leases/retries/DLQ; telemetry; CI/release automation; recovery and RAG/security evaluations |
| 1D pilot | Approved rules/catalogs and language; staffed employee queue and deadlines; pilot cohort, numerical quality/latency/cost gates; production configuration, restore rehearsal and owner acceptance |
| 1E property | Property schema, habitability/hazard rules, fixtures and evaluated routing after auto gates |

No AWS resources were provisioned and no pilot or complete Phase 1 acceptance is
claimed. SQLite persistence verifies the local business recovery contract; it
includes actual LangGraph SQLite checkpoint recovery, but does not establish
PostgreSQL recovery or AWS durability.
The HTTP evidence-upload endpoint is deliberately not exposed until protected
storage is implemented.

## Verification

Verified this increment: **13 unit tests, 22 integration tests and one Chromium
browser journey passed**. The browser exercised pre-auth help, authenticated
intake, draft confirmation, a mock receipt, employee acceptance and customer
resume with no JavaScript errors. The browser test ran outside the execution
sandbox because it requires localhost sockets. Chromium used the Ubuntu 24.04
fallback build on Ubuntu 26.04, with missing runtime libraries extracted in
`/tmp/insurance_browser_libs`; no system packages were installed.

Run the unittest and browser commands in [README](../README.md). Tests exercise
actual ASGI routes and temporary application/core/checkpoint databases. Provider
transport tests use mocked responses and require no credentials.

The opt-in [language evaluation runner](../tests/evaluation/run_language.py) covers
explicit facts, injury negation, uncertainty, references, service sources, coverage
fallback and prompt injection. It was checked to fail clearly without a key;
**no live provider evaluation was run**. The adapter uses exact quote checks and
keeps extracted facts unconfirmed; quote presence alone does not prove semantic
correctness. Live quality, latency and cost gates remain necessary before enabling
this path for real customers.

Implementation references: [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
and [FastAPI bearer authentication](https://fastapi.tiangolo.com/tutorial/security/first-steps/).
Production PostgreSQL checkpoint/interrupt behavior must additionally satisfy the sources
and acceptance cases in the [implementation guide](PHASE_1_IMPLEMENTATION_GUIDE.md).
