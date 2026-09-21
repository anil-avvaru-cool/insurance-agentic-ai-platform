# Phase 1: AWS Policy Coverage POC

## Objective

Deploy a small AWS proof of concept that answers policy coverage questions from four synthetic PDF documents, cites its sources, isolates content by authenticated policy owner and line of business (LOB), and reports when the documents do not support an answer.

## Scope

- Auto LOB: two customer-specific policy PDFs, one for each synthetic user.
- Property LOB: two customer-specific policy PDFs, one for each synthetic user.
- Basic owner isolation using verified authentication and mandatory owner-and-LOB retrieval filters.
- Richer ACLs, delegated access, and policy sharing are future extensions.
- Metadata extraction and validation.
- Amazon Bedrock Knowledge Base for document ingestion, indexing, and retrieval.
- Offline ingestion pipeline and online query pipeline.
- API Gateway and Lambda query API.
- Terraform bootstrap, infrastructure provisioning, and API/Lambda deployment.
- Observability for ingestion, queries, and answer quality.
- End-to-end testing with a predefined set of questions.

## Resource inventory

See [Phase 1 AWS resource inventory and deployment order](PHASE_1_AWS_RESOURCE_INVENTORY.md) for resource purposes, priorities, implementation status, dependencies, and acceptance gates.

## Implementation Plan

The numbered steps group related work; they are not a strictly sequential deployment order. Complete steps 1 and 2, then configure indexing from step 4 and provision the offline AWS resources from step 7 before running step 3 against AWS. After ingestion, complete step 4's retrieval validation before enabling online queries in steps 5 and 6. Add the relevant observability from step 8 alongside each pipeline.

### 1. Create policy documents

- Create four synthetic PDFs with coverage, limits, deductibles, and exclusions, using synthetic customer identities.

| Document | Owner | Product |
|---|---|---|
| Auto policy 1 | User 1 | Standard Auto |
| Auto policy 2 | User 2 | Standard Auto |
| Property policy 1 | User 1 | Standard Property |
| Property policy 2 | User 2 | Standard Property |

- Each Auto PDF covers bodily injury liability, property damage liability, collision, and comprehensive coverage. Auto property damage liability is distinct from the building and personal belongings coverage in the separate Property PDFs.
- Give each user one policy per LOB for this POC, with deliberately different policy values. For example, use a $500 collision deductible for User 1 and $1,000 for User 2 so accidental mixing is detectable.
- Keep documents small and easy to review.
- Prepare questions with expected answers and supporting passages for each document.
- Include questions that the documents cannot answer and paired questions that must produce different answers for the two users.

### 2. Define and extract metadata

- Define document ID, `owner_id`, `policy_id`, policy/product name, LOB, version, and effective date.
- Use distinct document and policy IDs for each policy, and a stable owner ID linking each synthetic user’s Auto and Property policies.
- Place these fields in a consistently labeled metadata block in each synthetic document.
- Extract metadata using deterministic rules for those labels; do not use LLM extraction.
- Validate required fields, expected owner-to-policy mappings, allowed LOB values, and date format, and flag missing or invalid values for correction before ingestion.
- Manually compare extracted metadata against each of the four PDFs before ingestion.
- Prepare metadata for ingestion and owner-and-LOB filtering.
- Keep metadata extraction logic separate from document text parsing; extraction may consume the parsed text.

### 3. Build the offline ingestion pipeline

Flow: PDFs → metadata preparation and validation → S3 → Bedrock Knowledge Base ingestion and indexing.

Prerequisites for an AWS ingestion run:

- Complete the four-document corpus and metadata review from steps 1 and 2.
- Complete the pre-ingestion configuration in step 4. Use step 7's Terraform workflow to provision the S3 document bucket, knowledge base, S3 data source, compatible vector index, and required IAM permissions.
- Configure the AWS region, bucket, dedicated POC prefix, knowledge base ID, data source ID, and timeout outside application code. Ensure the data source reads the intended prefix, the ingestion runner can upload and start/inspect jobs, and the knowledge base can read documents and write embeddings.
- Verify the required resources are deployed and accessible; Terraform definitions alone do not establish AWS readiness.

Existing foundations: `scripts/prepare_poc_metadata.py` validates the corpus and checks sidecars; `scripts/bedrock_smoke.py` starts and polls ingestion jobs, including document-failure checks; `infra/aws/terraform/development/bedrock.tf` defines the storage, knowledge base, data source, embedding model, and chunking configuration. Reuse these components and adjust their configuration for this POC.

Implement one repeatable CLI command for the four-document POC:

- Validate the entire corpus and check that all metadata sidecars are current before uploading anything. Fail without uploading if validation fails.
- Upload only the four approved PDFs and matching `*.pdf.metadata.json` sidecars to the dedicated POC prefix. Exclude README files, source JSON, review records, and question fixtures.
- Start ingestion only after all uploads succeed. Use an explicit command when documents or metadata are added, changed, or removed; event-driven automation is outside the initial POC scope.
- Support safe reruns, prevent overlapping runs from syncing incomplete uploads, and define how revised policies replace prior versions so obsolete content does not remain retrievable. Limit any cleanup to the managed POC inventory.
- Record the ingestion job ID, status, duration, document statistics, and failure reasons. Exit unsuccessfully on job failure, document failures, or timeout; retain the job ID so a timed-out job can be inspected before retrying.
- Test validation failures, partial upload failures, ingestion failures, timeouts, and reruns. Document the command and required configuration.

Step 3 is complete when the command uploads the validated corpus and finishes ingestion without document failures, with a reviewable run report. Successful ingestion does not establish retrieval correctness or owner isolation; those are step 4's acceptance checks.

### 4. Configure and validate document indexing

Indexing runs as part of the offline Bedrock Knowledge Base ingestion job.

Flow: S3 documents and metadata → text parsing → chunking → embeddings → retrieval index.

Before the first ingestion run:

- Configure text parsing and chunk size/overlap for the policy PDFs through Terraform.
- Select a Bedrock embedding model and configure a compatible vector index in the backing retrieval store. Review the existing Titan Text Embeddings V2, 1,024-dimension S3 Vectors index, and fixed-size 300-token/15% overlap configuration as the initial POC settings.
- Configure metadata and source preservation so indexed chunks carry document ID, `owner_id`, `policy_id`, LOB, version, and source references, with `owner_id` and LOB available for filtering.

After running the step 3 ingestion command:

- Verify each of the four documents is retrievable, source references are correct, and combined owner-and-LOB filters return only matching content before enabling online queries.
- Verify a revised document and its metadata become retrievable and superseded content is no longer returned.
- Re-run the step 3 command after document or metadata changes; rebuild and validate the index when embedding or chunking settings change.

### 5. Build the online query pipeline

Flow: verified owner identity + question + LOB → owner-and-LOB filtered retrieval → Bedrock answer generation → answer with citations.

- Require a supported LOB and a verified owner identity. Apply both `owner_id` and LOB as mandatory retrieval filters before content reaches answer generation.
- Reject requests with missing or unmapped owner identity; never fall back to unfiltered retrieval.
- Keep answers and citations within the authenticated owner’s selected LOB, including when the question asks about another user’s policy.
- Generate answers grounded in retrieved policy content.
- Return document citations with supported answers.
- Return an insufficient-information response when the documents do not support an answer.

### 6. Expose the query API

Flow: API Gateway with authentication → Lambda → online query pipeline.

- Accept a question and LOB.
- Derive `owner_id` from verified authentication context through a trusted mapping; do not trust caller-supplied owner IDs as authorization.
- Reject unauthenticated requests and identities without an authorized owner mapping. A local test harness may simulate identities; deployed API tests must use verified authentication.
- Return the answer, citations, and request ID.
- Validate input and return clear errors.
- Use appropriate API access controls and least-privilege AWS permissions.

### 7. Deploy with Terraform

Begin Terraform work alongside pipeline development. Offline infrastructure is a prerequisite for the first AWS ingestion run; API/Lambda deployment is not.

1. Bootstrap Terraform state storage.
2. Provision the offline infrastructure: S3 document storage, knowledge base, S3 data source, vector index, required permissions, and ingestion observability, using step 4's indexing configuration. Reuse the existing development Terraform resources where appropriate.
3. Run the step 3 command to upload documents and metadata and complete ingestion; perform step 4's retrieval and owner-and-LOB filter validation.
4. Provision API authentication, trusted owner identity mapping, online permissions, and query observability; package and deploy the Lambda application and API from steps 5 and 6. Enable online queries only after indexing validation passes.
5. Run smoke tests against the authenticated deployed API, followed by step 9's end-to-end checks.

Keep environment-specific configuration outside application code.

### 8. Add observability

#### Offline ingestion and indexing

- Record ingestion status, documents processed or failed, duration, and failure reasons.
- Make failed ingestion runs visible in logs and metrics.
- Record index validation results, including missing documents, incorrect source references, and owner or LOB filter failures.

#### Online queries

- Use structured logs with a request ID to correlate API and pipeline activity.
- Track request volume, authentication/authorization failures, API/Lambda errors, response latency, and Lambda throttling.
- Record retrieval result counts, citation presence, and insufficient-information responses.
- Track model token usage where available.

#### Dashboard and logs

- Create a CloudWatch dashboard for request volume, errors, latency, throttling, and ingestion failures.
- Review logs and the dashboard during operator-run ingestion and API tests. Automated alarms and alert delivery are outside Phase 1 scope; revisit them if the POC runs unattended or supports ongoing users.
- Set log retention explicitly.
- Avoid logging full policy documents or user questions by default.
- Provision observability resources through Terraform.

#### Answer quality

- Evaluate answer accuracy and citation correctness against the predefined questions.
- Treat citation presence as an operational signal; verify correctness separately in evaluation.

### 9. Test end to end

- Verify all four documents are indexed and retrievable with the expected metadata.
- Update a document and its metadata, re-run ingestion, and verify retrieval reflects the new version.
- Check supported questions across all four documents.
- Verify answers and citations against the expected policy passages.
- For each user, verify Auto queries retrieve only their Auto content and Property queries retrieve only their Property content.
- Ask the same deductible or limit question as both users and verify each answer and citation matches that user’s policy.
- Attempt to request another user’s policy through question text and caller-supplied owner IDs; verify no other owner’s content appears in retrieval results, answers, or citations.
- Verify missing or invalid authentication and unmapped identities are rejected before retrieval.
- Check unsupported questions return insufficient information.
- Check invalid API inputs produce clear errors.
- Introduce a controlled failure to verify logs and metrics; verify ingestion failures also produce an unsuccessful CLI exit and a reviewable run report.

## Completion Criteria

- All four PDFs and their validated metadata are successfully ingested, indexed, and verified through retrieval checks.
- One deployed API answers the predefined test set with accurate document citations.
- Mandatory owner-and-LOB filtering prevents retrieval from another owner or LOB.
- The deployed API derives owner identity from verified authentication and rejects missing, invalid, or unmapped identities.
- Isolation tests confirm that answers and citations contain only the authenticated owner’s selected LOB content.
- Unsupported questions produce an insufficient-information response.
- Terraform supports bootstrap, infrastructure provisioning, and API/Lambda deployment.
- CloudWatch dashboards show ingestion and query activity.
- A controlled failure demonstrates that logs and metrics expose failures, and failed ingestion exits unsuccessfully with a reviewable run report.
- Deployment and test instructions are documented so the POC can be repeated.
