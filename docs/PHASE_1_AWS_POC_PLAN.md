# Phase 1: AWS Policy Coverage POC

## Objective

Deploy a small AWS proof of concept that answers policy coverage questions from four synthetic PDF documents, cites its sources, filters by line of business (LOB), and reports when the documents do not support an answer.

## Scope

- Auto LOB: two lightweight policy coverage PDFs.
- Property LOB: two lightweight policy coverage PDFs.
- Metadata extraction and validation.
- Amazon Bedrock Knowledge Base for document ingestion, indexing, and retrieval.
- Offline ingestion pipeline and online query pipeline.
- API Gateway and Lambda query API.
- Terraform bootstrap, infrastructure provisioning, and API/Lambda deployment.
- Observability for ingestion, queries, and answer quality.
- End-to-end testing with a predefined set of questions.

## Implementation Plan

### 1. Create policy documents

- Create four synthetic PDFs with coverage, limits, deductibles, and exclusions.
- Keep documents small and easy to review.
- Prepare questions with expected answers and supporting passages for each document.
- Include questions that the documents cannot answer.

### 2. Define and extract metadata

- Define document ID, policy/product name, LOB, version, and effective date.
- Extract and manually validate metadata for the four documents.
- Prepare metadata for ingestion and LOB filtering.
- Keep metadata extraction separate from document text parsing.

### 3. Build the offline ingestion pipeline

Flow: PDFs → metadata preparation and validation → S3 → Bedrock Knowledge Base ingestion and indexing.

- Store PDFs and associated metadata in S3.
- Configure the knowledge base and its backing retrieval store.
- Run ingestion when documents are added or changed.
- Track ingestion completion and surface failures.

### 4. Configure and validate document indexing

Indexing runs as part of the offline Bedrock Knowledge Base ingestion job.

Flow: S3 documents and metadata → text parsing → chunking → embeddings → retrieval index.

- Configure text parsing and chunk size/overlap for the policy PDFs.
- Select a Bedrock embedding model and configure a compatible vector index in the backing retrieval store.
- Preserve document ID, LOB, version, and source references on indexed chunks for filtering and citations.
- Run ingestion to populate the index and wait for successful completion.
- Verify each of the four documents is retrievable, source references are correct, and LOB filters return only matching content before enabling online queries.
- Re-run ingestion after document or metadata changes; rebuild and validate the index when embedding or chunking settings change.

### 5. Build the online query pipeline

Flow: question + LOB → filtered retrieval → Bedrock answer generation → answer with citations.

- Require a supported LOB and apply it as a retrieval filter.
- Generate answers grounded in retrieved policy content.
- Return document citations with supported answers.
- Return an insufficient-information response when the documents do not support an answer.

### 6. Expose the query API

Flow: API Gateway → Lambda → online query pipeline.

- Accept a question and LOB.
- Return the answer, citations, and request ID.
- Validate input and return clear errors.
- Use appropriate API access controls and least-privilege AWS permissions.

### 7. Deploy with Terraform

Begin Terraform work alongside pipeline development so the required AWS resources are available.

1. Bootstrap Terraform state storage.
2. Provision infrastructure, permissions, knowledge base and vector index resources, and observability.
3. Package and deploy the Lambda application and API.
4. Upload the documents and metadata, then run ingestion and indexing.
5. Verify indexed content and LOB filtering, then run smoke tests against the deployed API.

Keep environment-specific configuration outside application code.

### 8. Add observability

#### Offline ingestion and indexing

- Record ingestion status, documents processed or failed, duration, and failure reasons.
- Make failed ingestion runs visible in logs and metrics.
- Record index validation results, including missing documents, incorrect source references, and LOB filter failures.

#### Online queries

- Use structured logs with a request ID to correlate API and pipeline activity.
- Track request volume, API/Lambda errors, response latency, and Lambda throttling.
- Record retrieval result counts, citation presence, and insufficient-information responses.
- Track model token usage where available.

#### Dashboards and alarms

- Create a CloudWatch dashboard for request volume, errors, latency, throttling, and ingestion failures.
- Configure CloudWatch alarms for API/Lambda errors, throttling, and ingestion failures, with an alert destination.
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
- Verify Auto queries retrieve only Auto content and Property queries retrieve only Property content.
- Check unsupported questions return insufficient information.
- Check invalid API inputs produce clear errors.
- Introduce a controlled failure to verify logs, metrics, and alarm delivery.

## Completion Criteria

- All four PDFs and their validated metadata are successfully ingested, indexed, and verified through retrieval checks.
- One deployed API answers the predefined test set with accurate document citations.
- LOB filtering prevents retrieval from the other LOB.
- Unsupported questions produce an insufficient-information response.
- Terraform supports bootstrap, infrastructure provisioning, and API/Lambda deployment.
- CloudWatch dashboards show ingestion and query activity.
- A controlled failure demonstrates that logs and alarms work.
- Deployment and test instructions are documented so the POC can be repeated.
