# Insurance Agentic AI Platform — Strategy

**Status:** Proposed strategy and planning assumptions.  
**Updated:** September 12, 2026.  
**Repository:** `insurance-agentic-ai-platform`

## Purpose

Build an enterprise-grade agentic AI platform for vehicle and property insurance, targeting a hypothetical portfolio of approximately **20 million vehicle policies and 20 million property policies in force**. Improve customer service and employee capacity while preserving controlled insurance decisions, privacy, and accountable human review.

This is a planning scenario, not a statement about a named insurer or a claim of tested capacity. See [Architecture](ARCHITECTURE.md) for logical design and [Deployment topology](DEPLOYMENT_TOPOLOGY.md) for cloud and infrastructure decisions.

## Portfolio definition

The proposed scale makes sense as an ambitious enterprise design envelope. Its usefulness depends on specifying what is counted and translating that count into demand.

| Measure | Working assumption or required distinction |
|---|---|
| Vehicle portfolio | Approximately 20 million policies in force; a policy may cover more than one vehicle |
| Property portfolio | Approximately 20 million policies in force; product mix and number of insured locations remain to be defined |
| Total policies | Approximately 40 million across the two lines |
| Unique customers/households | Not assumed to equal total policies; bundled households can appear in both lines |
| Claims and service contacts | Annual flow measures derived separately from the portfolio |
| Simultaneous users | Derived from interaction rates and session duration, not from policy counts |
| Cloud allocation | One portfolio envelope; no assumption of three full production copies |

If the intended measure is 20 million insured vehicles and 20 million insured properties, replace the policy assumptions and recalculate workload inputs. Define owned/underwritten versus serviced partner policies as well; available data and decision authority can differ. An equal split is a chosen scenario, not an industry benchmark or inferred market share.

## Business priorities

| Priority | Initial capabilities | Outcome measures |
|---|---|---|
| Customer service | Authorized status, process explanations, reliable employee handoffs | Resolution rate, repeat contacts, cost per resolved request, complaints |
| Claims intake | Structured loss capture and evidence collection | Completion rate, intake accuracy, time to first contact |
| Claims triage assistance | Urgency and team recommendations | Urgent-case misses, agreement/overrides, assignment time |
| Employee productivity | Evidence summaries and missing-information checks | Handling time, rework, backlog, employee acceptance |
| Relevant growth | Optional bundle discovery and approved quote retrieval | Incremental conversion and profitable bundle attachment |
| Underwriting support | Rule/evidence preparation with review | Review capacity, exception quality, adverse-outcome errors |

Prioritize service and intake before autonomous consequential decisions. Triage recommendations require controls because errors can delay help. Cross-sell is optional and should not interrupt a loss journey. Quote engines determine premiums; underwriting assistance must not invent eligibility rules. Fraud indicators require evidence and investigator review.

## Customer trust and operating model

Explain when AI is involved, collect sensitive data through protected forms, and provide an employee path that preserves work already completed. Customer consent to a purchase or change is separate from employee approval of an internal recommendation. Do not optimize containment at the expense of correct resolution or access to help.

Use staged authority: read and summarize, recommend, execute approved low-risk actions, then consider tightly controlled higher-impact workflows. Advancement requires evidence from the relevant line of business and customer journey.

| Owner | Accountability |
|---|---|
| Business product owner | Customer outcome, allowed actions, baseline and benefit measurement |
| Claims/underwriting leads | Approved rules, escalation, evidence standards, reviewer quality |
| Platform engineering | Runtime, workflow, API contracts, Terraform, releases, reliability |
| Security/privacy teams | Identity boundaries, data handling, retention, access testing |
| Model risk and quality owners | Evaluations, model/prompt changes, regression gates, oversight |
| Operations and employee teams | Queue ownership, response expectations, incidents, overrides |

## Capacity planning method

Portfolio counts are the starting point. Establish separate observed or explicitly hypothetical inputs for vehicle and property insurance:

- Service contacts per policy per year and the proportion handled through this platform.
- Claims per policy per year and agent-assisted steps per claim.
- Quote/prospect demand, which cannot be derived from existing policies alone.
- Turns per conversation, model calls and tool calls per turn, and input/output tokens per call.
- Busy-hour concentration, catastrophe uplift, average execution time, document sizes, and retention.
- Downstream claims/rating API limits, employee review capacity, and model quotas.

Use consistent definitions to avoid counting a claims interaction both as a service contact and a separate claim task.

```text
Annual service conversations
  = sum by line(policies × service contacts/policy/year × agent adoption)

Annual claim workflows
  = sum by line(policies × claims/policy/year × workflow adoption)

Peak conversation arrivals/second
  = annual conversations / seconds per year × measured peak factor

Approximate active executions
  = peak execution arrivals/second × mean execution duration in seconds

Model calls/second
  = peak turn arrivals/second × mean model calls/turn
```

An illustrative service-only scenario: 40 million policies × 2 service conversations per policy-year × 25% adoption gives 20 million agent-assisted conversations annually, about 0.63 per second averaged over a 365-day year. A hypothetical 20× peak factor gives about 12.7 conversation starts per second. Neither figure includes claim workflows, prospects, repeated turns, model/tool fan-out, or regional catastrophe concentration. These numbers explain the calculation; they are not a sizing recommendation or forecast.

Build normal, busy-hour, and catastrophe scenarios by line and region. Measure token demand and execution concurrency before choosing instance counts, database partitions, or model quotas. Use synthetic population identifiers to test portfolio lookup scale separately from full LLM load, then test realistic workflow volumes and failure recovery. Never equate storing 40 million identifiers with demonstrating enterprise workload capacity.

## Cloud strategy

Use AWS for phase one. Maintain one shared source repository, with independent cloud implementations as later architectural targets:

- AWS: Amazon Bedrock AgentCore Runtime.
- Azure: Microsoft Foundry Agent Service hosted agents.
- GCP: Gemini Enterprise Agent Platform Agent Runtime.

Cloud selection changes runtime, identity, model, and infrastructure adapters. Shared domain contracts and evaluations remain consistent. Each cloud has its own Terraform state, credentials, releases, and operations. Cross-cloud agent calls and automatic failover are outside the baseline scope. Detailed service references and deployment assumptions are maintained in [Deployment topology](DEPLOYMENT_TOPOLOGY.md).

## Infrastructure cost controls

Include a bounded RAG capability in phase one: approved FAQs, claims procedures, and intake checklists, starting with auto. Store source documents in ordinary S3 and embeddings in an S3 Vectors index through Bedrock Knowledge Bases. Require versioned sources, citations, retrieval evaluations, and employee fallback when evidence is insufficient. Live customer policy facts and claim status remain authorized API lookups. Defer broad enterprise ingestion, complex policy interpretation, and advanced retrieval to phase two. See the [Phase 1 implementation guide](PHASE_1_IMPLEMENTATION_GUIDE.md#phase-one-rag) and [AWS hourly cost estimate](PHASE_1_AWS_COST_ESTIMATE.md).

Keep development, demo, and pilot environments small. Provision high-cost resources only when the workload or an approved security requirement needs them, and disable or remove optional resources when they are idle.

- **Managed firewalls:** Leave optional dedicated cloud firewall deployments disabled in development and demo environments unless testing requires them. Retain required network isolation and access controls. Any change to a required firewall, especially in production, needs security review and validated replacement controls before removal.
- **Other costly resources:** Review NAT gateways, dedicated clusters, GPU instances, provisioned model capacity, database replicas, and duplicate environments before provisioning. Prefer the smallest suitable configuration and scale with measured demand.
- **Idle environment cleanup:** Schedule shutdown of supported nonproduction compute and tear down disposable environments after demos or tests. Check which resources continue billing while idle; stopping an application alone is not a cost-control plan. Preserve required data and recovery assets before teardown.
- **Deployment defaults:** Use explicit infrastructure configuration flags for optional expensive components, with development/demo defaults disabled. Document dependencies and a tested re-enable procedure so cost changes do not break routing or access.
- **Spend ownership:** Tag resources with an owner, environment, and expiry date where applicable. Set environment budgets and alerts, review spend regularly, and remove unused resources. Track infrastructure cost alongside model cost per completed workflow.

Before each pilot expansion, review always-on infrastructure and justify each high-cost component against measured demand, security requirements, or recovery objectives.

## Value measurement and investment gates

Establish baselines before pilot launch and compare matched workloads. Separate results by vehicle/property line, complexity, channel, and catastrophe conditions. Track customer outcomes and errors alongside cost and conversion. Subtract model, infrastructure, engineering, oversight, and employee review costs from gross benefits. Report released capacity separately from realized expense savings and avoid double-counting faster handling across multiple benefit categories.

Expansion requires an agreed quality threshold, reviewed privacy/access results, functioning employee escalation, affordable unit economics, and demonstrated recovery. Numeric targets should be agreed with business owners using baseline data rather than invented from portfolio size.

## Delivery phases and open decisions

| Phase | Deliverable | Exit evidence |
|---|---|---|
| 1 | Customer service with bounded RAG, claims intake, and human-reviewed triage on AWS using LangGraph; local auto journey through deployed controlled pilot, then property expansion | Approved-source retrieval and citations, confirmed intake, early urgency escalation, durable employee review, access isolation, idempotency, restore, and agreed pilot quality/cost gates |
| 2 | Expand validated journeys and traffic, broaden the RAG corpus and document capabilities as justified; consider approved routine routing | Line-specific quality evidence, retrieval/document evaluations, operational capacity, and explicit action authority |
| 3 | Additional capabilities or independent Azure/GCP implementations when justified | Business case plus role-specific or cloud-specific contract, quality, security, and recovery evidence |

The [Phase 1 implementation guide](PHASE_1_IMPLEMENTATION_GUIDE.md) defines scope, LangGraph workflows, AWS placement, milestones, and acceptance criteria. Triage covers urgency, handling team, missing information, and employee escalation; fraud analysis is deferred. Azure and GCP remain architectural targets and are not prerequisites for the AWS pilot.

Before implementation, resolve region and model availability, networking requirements, existing policy/claims API contracts, customer identity integration, human work-queue integration, production data retention, model evaluation thresholds, and RTO/RPO. Validate Terraform/provider coverage and preview dependencies in the exact selected regions and accounts. These are implementation decisions, not requirements to abandon independent deployment.


