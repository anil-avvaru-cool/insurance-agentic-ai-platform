# Phase 1 AWS POC pending work

This backlog consolidates the unfinished work described by
[PHASE_1_AWS_POC_PLAN.md](PHASE_1_AWS_POC_PLAN.md) and
[PHASE_1_AWS_RESOURCE_INVENTORY.md](PHASE_1_AWS_RESOURCE_INVENTORY.md).

**Status convention:** checked items indicate repository implementation, not AWS
acceptance. Terraform resources are defined, but deployment and live acceptance
remain unverified in the inventory. Keep live gates open until reviewable run
evidence establishes that they passed.

Priority describes the recommended implementation focus. Deployment must still
respect the gates below: bootstrap and offline infrastructure precede ingestion;
offline retrieval and isolation validation precede query API enablement.

## Priority summary

| Priority | Section | Outcome |
|---|---|---|
| P0 | Workloads: applications, Lambda, and services | Finish and verify the code that performs ingestion, retrieval, authorization, answer generation, telemetry, and acceptance testing. |
| P1 | Infrastructure: offline foundation | Establish usable Terraform state, S3, Bedrock Knowledge Base, S3 Vectors, IAM, and ingestion observability in the target AWS account. |
| P2 | Offline data and validation | Ingest the reviewed corpus and prove metadata, citations, replacement, owner isolation, and LOB isolation before exposing queries. |
| P3 | Infrastructure: online API and identity | Deploy the Lambda/REST API/IAM path, operator allowlist, synthetic customer selection, least-privilege IAM, and query observability. |
| P4 | End-to-end acceptance and operations | Prove the complete POC, retain reports, and document repeatable deployment, recovery, testing, and teardown. |

## P0 — Workloads: applications, Lambda, and services (prioritize first)

Local implementation should be completed early so it is ready when the gated
AWS infrastructure becomes available. These tasks do not authorize enabling
online traffic before P2 passes.

### Query Lambda and API behavior

- [x] Implement the query handler, ZIP packaging, and initial unit coverage.
  The inventory now records `src/apps/query_lambda/query.py`,
  `scripts/build_query_lambda.sh`, and `tests/unit/test_query_lambda.py` as
  implemented. Artifact verification and deployed acceptance remain open below.
- [ ] Complete review and local verification of the Lambda contract: accept only
  `question`, supported `lob`, and synthetic `owner_id`; verify IAM operator context,
  reject missing or unapproved identities, and always retrieve with both owner and
  LOB filters.
- [ ] Verify grounded-answer behavior: Bedrock supplies only the draft answer;
  Lambda must accept citations only from filtered retrieval results and return
  the controlled insufficient-information response when evidence is absent or
  unsupported.
- [ ] Verify the implemented response contract in deployed API tests: success
  returns `answer`, `citations`, and `request_id`; handler failures return
  `error` with `code` and `message`, plus `request_id`. Check validation,
  authorization, deadline, and upstream failures, and separately capture
  API Gateway rejections that occur before Lambda.
- [ ] Build and test `build/lambda/query.zip` for the configured Python 3.12
  runtime and `query.handler` entry point. Packaging includes `query.py` and
  relies on runtime-provided Boto3/Botocore. Retain evidence that the tested
  artifact is the artifact deployed by Terraform.
- [ ] Review remaining local test gaps and add coverage for malformed requests,
  both LOBs, cross-owner questions, model failures, deadlines, and Bedrock
  failures as needed. Existing handler tests cover IAM context rejection,
  approved role sessions, invalid customer selection, valid base64 requests,
  owner-and-LOB filters, unknown citations, and empty retrieval results.

### Offline ingestion and validation services

- [ ] Verify the repeatable ingestion CLI against deployed AWS, including full
  pre-upload validation, eight-object allowlisting, safe reruns, locking,
  partial-upload behavior, job failure, document failure, and timeout reporting.
- [ ] Implement or designate one repeatable index-validation command that checks
  all four documents, source references, combined owner-and-LOB filtering, and
  replacement of a revised document. The generic smoke helper is not the
  Phase 1 acceptance runner; its generic retrieval does not prove isolation.
  Use `scripts/ingest_poc.py` for managed POC ingestion: the smoke helper's
  `ingest` operation bypasses POC locking.
- [ ] Emit the documented structured ingestion and index-validation events to
  CloudWatch. The current ingestion CLI writes a local report only. Match the
  documented metric-filter contract and avoid duplicate direct metric publishing;
  the log group and metric filters alone do not create telemetry.
- [x] Ensure every failed or timed-out ingestion exits nonzero and leaves a
  reviewable report containing the job/run identifiers needed for recovery.
  Implemented in `scripts/ingest_poc.py` and `src/ingestion/offline.py`; local
  tests cover job/document failures, timeouts, lost start responses, polling
  errors, and retained recovery identifiers. Live AWS verification remains open
  above.

### Evaluation workload

- [x] Finalize expected answers and supporting passages for all four policies,
  including paired owner-specific questions and unsupported questions.
  `tests/fixtures/aws_poc/questions.json` contains 36 cases: 24 supported questions
  with supporting passages, eight unsupported questions, and four cross-owner
  attempts. Paired cases cover both owners and both LOBs.
- [x] Implement a SigV4-authenticated online fixture runner with retained reports.
  [test_online_rag.py](../scripts/test_online_rag.py) requires `--case-id` and
  runs exactly one selected fixture per invocation, checking response shape,
  request IDs, citations, expected amounts, and insufficient-information behavior.
  See [ONLINE_RAG_TESTING.md](ONLINE_RAG_TESTING.md).
- [ ] Execute the complete fixture matrix through separate runner invocations
  across both synthetic customers and both LOBs, including cross-owner question
  attempts and unsupported questions; retain responses and request IDs.
- [ ] Supply separate deployed checks for missing/invalid signatures and invalid
  customer/question/LOB inputs; the runner does not execute these. Test an
  unapproved principal using separate credentials; the runner records that
  check as not run. Controlled backend failures and CloudWatch verification
  also remain outside the runner.
- [ ] Evaluate answer accuracy and citation correctness separately from the
  operational `has_citations` metric.

## P1 — Infrastructure: offline foundation

All infrastructure tasks below concern deployment and verification of existing
Terraform definitions, rather than missing resource implementations. The inventory
counts six separate bootstrap resources, 22 default development resources,
24 additional resources when queries are enabled, and one resource per optional
operator-role attachment. These are configuration counts, not an account plan.

### Terraform bootstrap and configuration

- [ ] Verify or deploy the S3 Terraform backend with versioning, encryption,
  public-access blocking, ownership controls, TLS enforcement, and lockfile use.
- [ ] Configure the target account, region, backend, dedicated POC prefix,
  deployment identity, and environment-specific variables outside application
  code; generate and review a fresh account-specific Terraform plan.

### S3, Bedrock Knowledge Base, and vector storage

- [ ] Deploy and verify the private knowledge-document bucket and its security
  controls.
- [ ] Deploy and verify the S3 Vectors bucket/index, using 1,024 dimensions and
  filterable `owner_id` and `lob` metadata.
- [ ] Deploy and verify the Bedrock Knowledge Base and S3 data source restricted
  to `approved/aws_poc/`, with Titan Text Embeddings V2 and the reviewed
  300-token/15-percent-overlap chunking configuration.
- [ ] Verify embedding-model and answer-model access in the chosen account and
  region, including service quotas and expected latency.

### IAM and offline observability

- [ ] Verify the Knowledge Base service role can read only the intended source,
  invoke the embedding model, and write to the intended vector index.
- [ ] Attach the ingestion-runner and validation-runner policies to approved
  operator roles, or confirm equivalent externally managed permissions. Policy
  creation by itself grants no operator access.
- [ ] Verify ingestion and validation log delivery, retention, metric filters,
  and dashboard widgets with actual emitted events.

## P2 — Offline data and validation gate

- [ ] Confirm that the four synthetic PDFs, metadata sidecars, question fixtures,
  and manual metadata review are current and mutually consistent.
- [ ] Run the ingestion command against the deployed environment and retain the
  successful run report; require all four documents to complete without document
  failures.
- [ ] Prove that each document is retrievable with the correct source and metadata.
- [ ] Prove that every combined owner-and-LOB filter returns only the intended
  policy content.
- [ ] Replace one document and its metadata, re-ingest, and prove that the new
  version is retrievable and superseded content is not returned.
- [ ] Record the validation evidence, then set `index_validation_passed = true`
  only after every offline check succeeds.

**P2 exit gate:** do not deploy or enable the online query path until ingestion,
retrieval, citation/source, replacement, owner-isolation, and LOB-isolation
checks all pass.

## P3 — Infrastructure: online API, IAM, identity, and monitoring

### Identity and authorization

- [ ] Configure the exact `query_operator_arn` and verify it matches the operator's
  AWS credentials. No Cognito users or JWT tokens are needed.
- [ ] Verify missing/invalid signatures and other principals are rejected before
  Lambda execution. Testing another principal requires separate credentials.
- [ ] Verify both synthetic customer IDs and reject missing/invalid selections.
  Customer login isolation is outside this operator-only POC's scope.

### Lambda, API Gateway, and IAM

- [ ] Configure the reviewed Lambda ZIP, handler, knowledge-base ID, answer-model
  ID, operator ARN, result/token limits, and deadline settings.
- [ ] Deploy the Lambda execution role and least-privilege policy for filtered
  retrieval, answer-model invocation, and scoped logging.
- [ ] Deploy API Gateway REST API, explicit operator-only policy, IAM-authenticated method,
  Lambda integration/permission, stage, access logging, and throttling.
- [ ] Verify the 28-second Lambda and 29-second API integration budgets against
  live model latency and controlled timeout behavior.

### Online observability

- [ ] Reconcile any existing regional API Gateway logging-role setting before
  applying the defined API log delivery role, policy, and account configuration.
- [ ] Verify Lambda and API log delivery and retention, including requests that
  authentication rejects before Lambda invocation.
- [ ] Confirm structured query events drive metrics for retrieval count,
  citations, insufficient-information responses, authorization failures, token
  usage, errors, latency, and throttling.
- [ ] Confirm logs exclude policy text, questions, credentials, tokens, and other
  unnecessary sensitive content; avoid high-cardinality metric dimensions.

## P4 — End-to-end acceptance and operational handoff

- [ ] Run deployed authenticated tests for every expected question across both
  synthetic customers and both LOBs using one `--case-id` invocation per fixture;
  review semantic answer support and citation correctness against the fixtures.
  A passing automated report alone does not establish answer quality.
- [ ] Verify unauthenticated, invalid-signature, unapproved-principal, invalid-input,
  cross-owner question, cross-LOB, and unsupported-question cases. Confirm that
  question text cannot override the selected owner/LOB filters. Selecting either
  valid `owner_id` is authorized for the approved operator; reject missing or
  invalid selections rather than treating a valid customer switch as spoofing.
- [ ] Introduce controlled ingestion and query failures and confirm visible logs,
  metrics, nonzero ingestion exit status, and reviewable reports.
- [ ] Review the CloudWatch dashboard during ingestion and query tests and retain
  evidence of activity, failures, latency, and throttling behavior.
- [ ] Verify and complete the existing [Terraform runbook](../infra/aws/terraform/README.md),
  [offline ingestion runbook](OFFLINE_INGESTION.md), and
  [online test runbook](ONLINE_RAG_TESTING.md) against accepted runs. Fill gaps
  in index validation, retained-lock recovery, rollback, and teardown procedures;
  identify shared or retained resources and link the acceptance reports.
- [ ] Update both source planning documents so implementation status matches the
  accepted system. Record deployed artifact evidence and live telemetry results;
  do not equate implemented code or a successful apply with acceptance.

## Deferred or conditional work

- Customer authentication and Cognito are deferred; Phase 1 uses the operator's
  existing AWS credentials with synthetic customer selection.
- Optional operator-role attachments are unnecessary when equivalent scoped
  permissions are managed externally.
- Automated alarms and alert delivery are outside Phase 1 unless the POC runs
  unattended or supports ongoing users.
- A dedicated model endpoint, metadata database, checkpoint store, event-driven
  ingestion, richer ACLs, delegated access, and policy sharing are outside the
  agreed Phase 1 scope.
