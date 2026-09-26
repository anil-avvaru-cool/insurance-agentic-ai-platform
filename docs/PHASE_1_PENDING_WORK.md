# Phase 1 AWS POC pending work

This backlog consolidates the unfinished work described by
[PHASE_1_AWS_POC_PLAN.md](PHASE_1_AWS_POC_PLAN.md) and
[PHASE_1_AWS_RESOURCE_INVENTORY.md](PHASE_1_AWS_RESOURCE_INVENTORY.md).

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

- [ ] Reconcile the resource inventory with the current query implementation.
  The inventory says the handler artifact is pending, while `src/apps/query_lambda/query.py`,
  `scripts/build_query_lambda.sh`, and unit tests now exist in the working tree.
- [ ] Complete review and local verification of the Lambda contract: accept only
  `question`, supported `lob`, and synthetic `owner_id`; verify IAM operator context,
  reject missing or unapproved identities, and always retrieve with both owner and
  LOB filters.
- [ ] Verify grounded-answer behavior: Bedrock supplies only the draft answer;
  Lambda must accept citations only from filtered retrieval results and return
  the controlled insufficient-information response when evidence is absent or
  unsupported.
- [ ] Freeze and document the response/error JSON schemas for `answer`,
  `citations`, `request_id`, validation failures, authorization failures,
  timeouts, and upstream failures.
- [ ] Build the reproducible Python 3.12 ZIP and verify that its handler path and
  dependencies match the Terraform configuration.
- [ ] Add or complete application tests for malformed/base64 requests, IAM context
  handling, invalid customer selection, both LOBs, cross-owner questions,
  model/citation failures, deadlines, and Bedrock failures.

### Offline ingestion and validation services

- [ ] Verify the repeatable ingestion CLI against deployed AWS, including full
  pre-upload validation, eight-object allowlisting, safe reruns, locking,
  partial-upload behavior, job failure, document failure, and timeout reporting.
- [ ] Implement or designate one repeatable index-validation command that checks
  all four documents, source references, combined owner-and-LOB filtering, and
  replacement of a revised document. The generic smoke helper is not the
  production authorization path.
- [ ] Emit the documented structured ingestion and index-validation events to
  CloudWatch. The log group and metric filters alone do not create telemetry.
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
- [ ] Automate the deployed authenticated test matrix for both users and both
  LOBs, including attempted cross-owner access and caller-supplied owner IDs.
- [ ] Evaluate answer accuracy and citation correctness separately from the
  operational `has_citations` metric.

## P1 — Infrastructure: offline foundation

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

- [ ] Verify Lambda and API log delivery and retention, including requests that
  authentication rejects before Lambda invocation.
- [ ] Confirm structured query events drive metrics for retrieval count,
  citations, insufficient-information responses, authorization failures, token
  usage, errors, latency, and throttling.
- [ ] Confirm logs exclude policy text, questions, credentials, tokens, and other
  unnecessary sensitive content; avoid high-cardinality metric dimensions.

## P4 — End-to-end acceptance and operational handoff

- [ ] Run deployed authenticated tests for every expected question across both
  users and both LOBs; compare answers and citations with the fixtures.
- [ ] Verify unauthenticated, invalid-signature, unapproved-principal, invalid-input,
  cross-owner, cross-LOB, unsupported-question, and caller-owner-spoof cases.
- [ ] Introduce controlled ingestion and query failures and confirm visible logs,
  metrics, nonzero ingestion exit status, and reviewable reports.
- [ ] Review the CloudWatch dashboard during ingestion and query tests and retain
  evidence of activity, failures, latency, and throttling behavior.
- [ ] Document exact deployment, configuration, ingestion, validation, API test,
  retained-lock recovery, rollback, and teardown procedures.
- [ ] Update both source planning documents so implementation status matches the
  accepted system, especially the Lambda artifact and telemetry status.

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
