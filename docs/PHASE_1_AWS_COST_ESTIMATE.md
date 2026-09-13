# Phase 1 AWS cost estimate

> Model decision update (2026-09-13): [ADR 0001](adr/0001_model_selection_and_provider_abstraction.md) selects GPT-5.4 mini through OpenAI for the initial POC. The worksheet below retains the earlier Nova Lite v1 assumptions for reference. Its totals and budgets are not the current combined AWS/OpenAI estimate; recalculate generation and total spend before provisioning.

**Updated:** September 12, 2026.  
**Status:** Approximate planning estimate; nothing has been provisioned.  
**Region/currency:** US East (N. Virginia), `us-east-1`, USD.  
**Basis:** On-demand rates and explicit budget allowances; 730 hours/month.

Plan for approximately **$0.39/hour ($288/month)** for one small development environment, or **$0.68/hour ($499/month)** for one more resilient pilot environment, at the illustrative workload below. Set initial budgets of **$0.60/hour equivalent ($438/month)** and **$1.00/hour equivalent ($730/month)** respectively. Budgets are monitoring thresholds, not automatic spending caps.

These estimates follow the [Phase 1 implementation guide](PHASE_1_IMPLEMENTATION_GUIDE.md), including bounded RAG. They are not estimates for the full 40-million-policy portfolio. Monthly figures use unrounded hourly totals; the hourly display is rounded. AWS prices, model availability, and final sizing must be checked again before deployment.

## Assumptions

- One environment running continuously. Development, staging, and production are billed separately; do not interpret either column as the cost of all three.
- 100 user turns/hour, with two generation calls per turn. Each call averages 3,000 input tokens, including history and retrieved context, and 500 output tokens. This is 600,000 input and 100,000 output tokens/hour.
- Nova Lite v1 is a cost example, not an approved model choice. Quality evaluations determine the deployed model. No provisioned model throughput or dedicated GPU endpoints.
- One RAG query per turn, 100 tokens/query; 10,000 chunks averaging 500 embedding tokens each. Use Titan Text Embeddings V2 with 1,024 dimensions. Assume approximately 6 KiB stored per vector including metadata and key, and 5 KiB counted for query processing. Re-embed 1% of the corpus monthly.
- Four continuously running Fargate tasks: API, invocation worker, outbox dispatcher, and action service. Development uses one of each; the pilot estimate uses two of each across two availability zones. Each task has 0.25 vCPU and 0.5 GB RAM, Linux/x86. These are starting sizes to load-test.
- API Gateway HTTP API → VPC Link → internal ALB → private ECS services. One NAT gateway for development; two for the pilot. Reserve four interface endpoint services per active AZ, with the exact endpoint list and routing decided during the deployment spike. Ordinary S3 traffic uses a gateway endpoint where applicable.
- Existing enterprise identity provider; include an integration allowance below. New identity subscriptions, Cognito MAU charges, and SMS are additional if chosen. Approximately 100 GB combined source/evidence S3 storage, modest logs and traffic, and short text documents using standard parsing.
- No Free Tier credits, Savings Plans, or negotiated discounts applied to quoted rates. Allowances cover small operational items without claiming exact metering.

## Always-on resources and standing allowances

“Allowance” means an engineering budget assumption, not a verified AWS SKU quote. Monthly storage and operational budgets are divided by 730 to show an hourly equivalent.

| Resource | Sizing / calculation | Development USD/hour | Pilot USD/hour |
|---|---|---:|---:|
| ECS Fargate | 4 / 8 tasks × (0.25 × $0.0404784/vCPU-hour + 0.5 × $0.004446/GB-hour) | 0.0494 | 0.0987 |
| RDS PostgreSQL including storage | Allowance: Single-AZ `db.t4g.small`, 20 GiB gp3 / Multi-AZ `db.t4g.medium`, 100 GiB gp3; confirm exact quote and CPU-credit exposure | 0.0500 | 0.1800 |
| Internal Application Load Balancer | $0.0225/hour + allowance for 1 LCU at $0.008/hour | 0.0305 | 0.0305 |
| NAT gateway and public IPv4 | 1 / 2 × ($0.045 gateway-hour + $0.005 public IPv4-hour); traffic below | 0.0500 | 0.1000 |
| Interface VPC endpoints | 4 services × 1 / 2 AZs × $0.01/endpoint-AZ-hour; traffic below | 0.0400 | 0.0800 |
| CloudWatch and audit operations | Allowance for modest log ingestion/retention, metrics, alarms, and audit storage; about $22 / $37 monthly | 0.0300 | 0.0500 |
| Secrets Manager and KMS | Allowance: 5 secrets, 2 customer-managed keys, and modest requests | 0.0100 | 0.0100 |
| Ordinary S3 storage and S3 Vectors storage | Rounded allowance for 100 GB ordinary storage and the small vector index; requests below | 0.0040 | 0.0040 |
| ECR, web assets, DNS, and delivery | Small artifact/static-web allowance; no separate always-on frontend server | 0.0100 | 0.0100 |
| Identity integration | Allowance for existing-IdP integration operations; external licensing excluded | 0.0100 | 0.0100 |
| **Standing subtotal** | Includes operational allowances even during quiet hours | **0.2839** | **0.5732** |

Rate references: [Fargate](https://aws.amazon.com/fargate/pricing/), [RDS PostgreSQL](https://aws.amazon.com/rds/postgresql/pricing/), [load balancing](https://aws.amazon.com/elasticloadbalancing/pricing/), [VPC/NAT/IPv4](https://aws.amazon.com/vpc/pricing/), [PrivateLink](https://aws.amazon.com/privatelink/pricing/), [CloudWatch](https://aws.amazon.com/cloudwatch/pricing/), [Secrets Manager](https://aws.amazon.com/secrets-manager/pricing/), and [KMS](https://aws.amazon.com/kms/pricing/). RDS and operational allowances require a final AWS Pricing Calculator quote; they are deliberately distinguished from sourced unit rates.

One development task per service is not highly available. The pilot column adds replicas and database/network redundancy, but the small task sizes and database still require load and recovery tests. Add approximately $0.01/hour for each additional interface endpoint service in each AZ. The endpoint count is a budget placeholder, not a complete network design.

## Usage at 100 user turns/hour

The following workload is the same for both columns; adding infrastructure replicas does not double model traffic.

| Resource | Calculation / allowance | USD/hour |
|---|---|---:|
| Bedrock generation: Nova Lite v1 | 0.6M input × $0.06/M + 0.1M output × $0.24/M | 0.0600 |
| AgentCore Runtime | 100 turns × (4 active vCPU-seconds × $0.0895/3,600 + 60 GB-seconds × $0.00945/3,600), rounded | 0.0260 |
| Query embeddings, vector queries, and small refreshes | Rounded allowance; details below | 0.0010 |
| API Gateway HTTP API, SQS, and S3 requests | Allowance for roughly 1,000 HTTP requests/hour plus queue operations, polling, and object requests | 0.0030 |
| Network processing and transfer | Allowance for modest NAT/endpoint traffic, cross-AZ traffic, and internet delivery | 0.0100 |
| Evidence malware scanning and ingestion jobs | Small-volume allowance; reprice against upload GB, object count, and scan implementation | 0.0100 |
| **Usage subtotal** | | **0.1100** |
| **Development total** | 0.2839 + 0.1100 | **0.3939** |
| **Pilot total** | 0.5732 + 0.1100 | **0.6832** |

AWS publishes the Nova Lite example rates of $0.06/M input and $0.24/M output in its [model cost guidance](https://aws.amazon.com/blogs/machine-learning/customizing-text-content-moderation-with-amazon-nova/). Verify the exact model/version and inference route against [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/) before deployment. Other metering references: [AgentCore](https://aws.amazon.com/bedrock/agentcore/pricing/), [API Gateway](https://aws.amazon.com/api-gateway/pricing/), [SQS](https://aws.amazon.com/sqs/pricing/), and [GuardDuty scanning](https://aws.amazon.com/guardduty/pricing/).

AgentCore CPU is billed for active consumption, while memory is billed over the session lifetime, including idle periods. The estimate assumes an aggregate 60 seconds at 1 GB billed memory per turn, including initialization and termination. Persist human waits and configure session termination; leaving sessions alive or consuming more memory raises this line. AgentCore Memory, Gateway, Browser, and Code Interpreter are outside this topology.

## Where the embeddings live and what RAG costs

Keep approved originals in a **regular private S3 bucket**. Bedrock Knowledge Bases performs ingestion and stores embeddings in a **separate S3 Vectors bucket/index**. RDS continues to hold application state and checkpoints. Customer evidence stays in its own protected bucket and is not ingested into the shared knowledge corpus. This integration is supported by [AWS S3 Vectors documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-getting-started.html).

Use Knowledge Bases `Retrieve`, then the existing model generation call. This estimate covers standard text ingestion, embedding, and vector retrieval; it does not select the separately priced Bedrock Managed Knowledge Base offering or include advanced parsing, reranking, or agentic retrieval.

| RAG component | Approximate calculation | Cost |
|---|---|---:|
| Vector storage | 10,000 × 6 KiB ≈ 0.057 GiB × $0.06/GB-month | $0.0034/month |
| Vector queries | 73,000/month × $2.50/M, plus 5 KiB × 10,000 vectors/query at $0.004/TB processed | About $0.20/month |
| Query embeddings | 73,000 × 100 tokens × $0.02/M | $0.146/month |
| Initial document embeddings | 10,000 × 500 tokens × $0.02/M | $0.10 once |
| Initial vector PUT | Approximately 0.057 GB × $0.20/GB, with batched writes | About $0.012 once |

Assume top-five retrieval with returned metadata below the per-query free data-return threshold. PUT minimum billable sizes and metadata overhead can raise ingestion cost. Recurring embedding/retrieval/vector-storage cost is approximately **$0.35/month** for this corpus and traffic, excluding ordinary source storage, ingestion compute, and answer generation. The tables reserve more than this small calculated amount. Source: [S3 Vectors pricing](https://aws.amazon.com/s3/pricing/) and AWS's [Titan V2 embedding cost example](https://aws.amazon.com/blogs/machine-learning/optimizing-costs-of-generative-ai-applications-on-aws/).

The small vector bill does not mean RAG answers are free: retrieved passages increase model input tokens, already included in the generation assumption. Benchmark retrieval quality and latency before expanding the corpus.

## Cost changes to watch

- **Model selection:** Recalculate `input millions/hour × input rate + output millions/hour × output rate`. At hypothetical rates of $3/M input and $15/M output, the same traffic costs $3.30/hour for generation instead of $0.06/hour: add $3.24/hour to either total. These are sensitivity assumptions, not a quote for a selected model.
- **Traffic and conversation length:** Model, runtime, and retrieval usage rise with turns, retries, and context size. Infrastructure grows in steps when tests show the need for larger tasks or databases. Do not linearly extrapolate this small deployment to portfolio scale.
- **Dedicated AWS Network Firewall:** Excluded from this baseline unless required by the approved network design. Standard endpoints are approximately $0.395/hour per AZ, or $0.79/hour for two AZs before processing. Eligible same-path NAT charges can be waived, so recompute the net total instead of blindly adding both. Preserve required isolation and security controls. [AWS Network Firewall pricing](https://aws.amazon.com/network-firewall/pricing/)
- **Environment duplication:** One development plus one staging sized like development plus one pilot at the stated workload is approximately $1.47/hour, or $1,074/month. Use actual traffic for each environment; idle environments still incur standing costs.
- **Shutdown:** Stopping tasks reduces compute costs, but databases/storage, load balancers, NAT gateways, endpoints, keys, and logs can continue billing. Tear down disposable infrastructure through reviewed Terraform changes while preserving required data.

Excluded or requiring separate sizing: taxes, AWS Support, engineering and employee staffing, external policy/claims/IdP licenses, VPN/Direct Connect/Transit Gateway, WAF and organization-mandated security tooling, large attachment volume, OCR/advanced document parsing, Bedrock Guardrails, automated model evaluations, CI/build and load-test bursts, cross-region recovery, extra backup retention, and substantial egress. The small operational allowances are not substitutes for pricing these when selected. [Cognito pricing](https://aws.amazon.com/cognito/pricing/) applies if Cognito is chosen instead of the existing-IdP assumption.

Before provisioning, replace allowances with an exported AWS Pricing Calculator estimate for the final network, database, identity, model, and recovery choices. After the deployment spike, compare actual daily spend, tokens per turn, runtime memory lifetime, and completed-journey cost against this worksheet.
