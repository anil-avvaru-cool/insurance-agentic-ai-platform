# Bedrock RAG LLM-as-judge implementation plan

Status: fixture alignment and opt-in exact evidence capture implemented and tested locally; deployment/live capture verification and the budget-gated judge workflow remain pending. No AWS evaluation has been run by this work.

Prerequisites now available: all 36 current-version fixtures, an explicit six-case
manifest, `scripts/validate_judge_baseline.py`, bounded and owner-checked Lambda
capture, dedicated Terraform storage/permissions, and the online runner's
`--capture-evidence` option. See the [capture workflow](ONLINE_RAG_EVALUATION.md#exact-evidence-capture-for-judge-evaluation).
The dedicated six-case runner, shared signing helpers, cost ledger, JSONL export,
evaluation service role, job lifecycle, and review report below remain planned.

Implements steps 9 and 10 of [the Phase 1 plan](PHASE_1_AWS_POC_PLAN.md). Deliver one manually submitted Bedrock evaluation of six actual deployed API responses, using correctness and faithfulness, a required budget gate, and recorded human review.

1. **Align the six scenarios with the current corpus.**

   Reuse `tests/fixtures/aws_poc/questions.json` and the explicit six-case baseline manifest in `tests/fixtures/aws_poc/judge_baseline.json`. The following review findings have been resolved:

   - Corrected the v2 collision reference from $500 to $750 after comparing the PDF and source.
   - Migrated User 1's Auto fixtures to v2 and removed the obsolete duplicate collision case. Replacement tests now advance from the current version.
   - Aligned other-owner reference wording with the controlled insufficient-information response; no-disclosure remains an independent requirement.
   - Refreshed the corpus review record and verified all four PDFs locally. Successful AWS ingestion and retrieval validation for the chosen version remain prerequisites for live capture.

   | Baseline scenario | Selected owner / LOB | Reference behavior |
   |---|---|---|
   | Collision deductible, User 1 | `customer_one` / `auto` | $750 per covered loss from `auto_user_1_v2` |
   | Same collision question, User 2 | `customer_two` / `auto` | $1,000 per covered loss from `auto_user_2_v1` |
   | Building coverage, User 1 | `customer_one` / `property` | Covered causes and $300,000 limit from `property_user_1_v1` |
   | Flood exclusion, User 2 | `customer_two` / `property` | Flood excluded for building and belongings from `property_user_2_v1` |
   | Annual Auto premium, User 1 | `customer_one` / `auto` | Controlled insufficient-information response |
   | Request User 2's deductible, selected User 1 | `customer_one` / `auto` | Controlled insufficient-information response; no other-owner evidence |

   Validate unique IDs, exactly six cases, paired identical deductible questions, owner/LOB/document mappings, expected responses, and exact supporting passages against the reviewed corpus. Pin corpus and fixture hashes to each run. Unsupported cases have no invented supporting passage.

2. **Capture evidence from the actual deployed query path.**

   Extend `src/apps/query_lambda/query.py` with an explicitly enabled, operator-only capture mode. Keep the existing IAM authorization and mandatory retrieval filters. The current API returns only answer, citations, and request ID; existing online reports cannot supply the exact model context.

   - Use a server-configured evaluation S3 destination and a validated capture flag on signed requests. Generate artifact keys on the server from request IDs; callers cannot choose S3 destinations.
   - Write a separate artifact containing selected owner/LOB, question, retrieval filters, all returned passage text and metadata, the exact bounded evidence sent to generation, evidence-ID mappings, final API answer/citations, generation configuration, model/KB identifiers, token usage, request ID, and deployment version.
   - Enforce passage-count, per-passage, total-context, and answer limits before generation/capture. Record any context selection or truncation. Preserve exactly what the answer model saw; do not shorten context after generation or re-retrieve it later for the judge.
   - Check owner/LOB and document metadata before passing evidence to generation; reject missing or mismatched ownership metadata. Validate citation IDs against that same evidence.
   - Keep full evidence out of CloudWatch logs. Capture failure must be visible and must prevent that response from becoming an eligible evaluation sample.
   - Preserve the existing single-case online runner. Add a dedicated evaluation runner that makes exactly six signed capture requests after budget preflight, without automatic inference retries. Reuse signing and response checks from `scripts/test_online_rag.py` through shared helpers.

   Acceptance: tests prove the captured final answer equals the API answer, captured generation context equals model input, ordinary requests do not write artifacts, and isolation failures cannot reach generation or judge submission.

3. **Provision evaluation storage and permissions through Terraform.**

   Add `infra/aws/terraform/development/evaluation.tf`, relevant outputs, example configuration, and Terraform tests.

   - Provision private encrypted artifact storage with public access blocked, TLS-only access, explicit retention, and separate `captures/`, `inputs/`, `outputs/`, and `runs/` prefixes. Keep it outside the KB ingestion source.
   - Grant the query Lambda write access only to captures when capture is enabled.
   - Create a Bedrock evaluation service role with scoped trust conditions, input read/output write access, and invocation permissions for one configured supported evaluator. Add KMS permissions only if using a customer-managed key.
   - Give the operator the necessary artifact access, evaluation create/get/list/stop permissions, and `iam:PassRole` limited to the evaluation role and Bedrock service. Scope resources where supported; explain required wildcard permissions.
   - Require region, evaluator identifier, artifact locations, budget, bounds, and pricing inputs through configuration; document them in `example.env`. Keep credentials out of Terraform and reports.

   Select and pin one model after verifying regional/account availability. Amazon Nova Pro is a candidate on the [supported evaluator list](https://docs.aws.amazon.com/bedrock/latest/userguide/evaluation-kb.html); do not infer evaluator support from the online answer model. If a cross-region inference profile is necessary, explicitly account for its model permissions and routing.

4. **Build and validate the bring-your-own-response dataset.**

   Add a small `src/evaluation/` package and `scripts/evaluate_rag.py`. Separate fixture validation, capture validation, dataset export, budget calculation, job operations, and reporting into testable functions.

   Export six JSONL records with one conversation turn each: `prompt`, `referenceResponses`, and `output` containing the captured answer, source/model identifiers, and `retrievedPassages.retrievalResults`. Match the dataset source identifier to the job configuration. Keep scenario/request IDs and row hashes in a sidecar manifest and verify result associations rather than assuming output order.

   Ground-truth passages remain in the review manifest. AWS built-in metrics do not use `referenceContexts`; faithfulness uses actual retrieved context. Do not substitute expected passages for captured retrieval evidence. Follow the [AWS dataset schema](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-evaluation-prompt-retrieve-generate.html).

   Reject incomplete captures, stale hashes, duplicate/missing cases, owner/LOB/citation failures, and schema violations before upload/submission. Preserve empty retrieval honestly; validate the service's handling before a paid run rather than fabricating context. Missing or inapplicable scores must remain visible, especially for abstention cases.

5. **Implement the cost gate before paid capture and before submission.**

   Require a positive total USD budget and a dated pricing record with model, region, rates, source URL, and token assumptions. Missing or invalid prices/bounds block paid work.

   Estimate generation and retrieval costs for any new captures, plus evaluator input/output tokens for both metrics across all six rows. Include built-in judge prompt overhead, repeated context per metric, conservative output allowances, a documented safety margin, and supporting AWS request/storage costs. Use the [current AWS pricing](https://aws.amazon.com/bedrock/pricing/); judge prompts are billable tokens.

   Store a persistent run ledger with estimates, reservations, capture costs, job IDs, and known usage. Reserve the estimate atomically before paid work so concurrent runs cannot reuse the same budget. Explicitly requested reruns consume the remaining budget; failed or ambiguous operations retain reservations until reconciled. Missing actual usage must not become zero cost.

   Acceptance: unset budget, insufficient remaining budget, stale/changed pricing inputs, oversized data, or an unresolved previous submission block new work. The estimate is a submission gate, not an AWS billing cap; evaluator output allowances are estimate assumptions unless the service exposes enforceable limits.

6. **Submit once, then inspect the same job.**

   Use the Bedrock control-plane client with `applicationType=RagEvaluation`, `taskType=General`, precomputed retrieve-and-generate source configuration, and only `Builtin.Correctness` and `Builtin.Faithfulness`, following [AWS's job configuration](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-evaluation-create-randg.html).

   Persist an immutable request manifest and idempotency token before submission; immediately retain the returned job ARN/ID. Disable automatic create retries. On an ambiguous response, reconcile the existing submission before allowing another job. Bounded polling may resume against the same ID; timeouts or failed jobs must never trigger automatic resubmission. Support explicit stop and collect operations without scheduling.

   Proposed CLI, to be implemented (commands below do not exist yet):

   ```sh
   uv run --locked --env-file .env python scripts/evaluate_rag.py prepare --run-id baseline_001
   uv run --locked --env-file .env python scripts/evaluate_rag.py capture --run-id baseline_001
   uv run --locked --env-file .env python scripts/evaluate_rag.py submit --run-id baseline_001
   uv run --locked --env-file .env python scripts/evaluate_rag.py status --run-id baseline_001
   uv run --locked --env-file .env python scripts/evaluate_rag.py collect --run-id baseline_001
   ```

   `prepare` validates fixtures/configuration and estimates costs without paid inference. `capture` enforces the initial budget reservation; `submit` validates the actual six-row export and remaining reservation. Inspection and collection never generate replacement answers.

7. **Produce a reviewable report and require human sign-off.**

   Retain raw AWS outputs, JSON summary, and a six-row Markdown review template under a gitignored `evaluation_reports/<run_id>/` and the configured artifact prefix. Include references, captured evidence and responses, citations, IDs/hashes, model/metric configuration, status/failures, per-case scores and available explanations, available usage, estimated cost, and deterministic check results.

   Require a reviewer, timestamp, pass/fail, and reasons for every case. Review answer accuracy, limits/exclusions, citation support, abstention, and owner/LOB isolation against the actual policy. Investigate and document judge disagreements. Citation correctness is not established by faithfulness alone. Do not add citation metrics beyond the two metrics in Phase 1 scope.

   Completion requires one completed six-case job, all six manual reviews passing, and independent isolation/citation checks passing. Missing results or unresolved disagreements remain incomplete; an aggregate judge score cannot override a deterministic failure. Keep broader Phase 1 authentication and end-to-end checks separate.

8. **Validate and document the operational workflow.**

   - Unit tests: fixture/version drift, exact evidence capture, isolation failure, dataset serialization, abstention handling, budget boundaries/concurrency, redaction, submission ambiguity, polling timeout, failed jobs, and missing/duplicate/out-of-order result records.
   - Mocked integration test: six captures through dataset export, one submission, collection, and pending manual review; assert there is no second answer-generation path or automatic paid retry.
   - Terraform validation/tests: private storage, capture disabled by default, role trust, S3/model scopes, and restricted pass-role.
   - Document configuration, preflight, commands, manual review, budget reconciliation, stopping/inspecting jobs, retention, and teardown. Link the runbook from the Phase 1 plan, resource inventory, online evaluation guide, and Terraform README. Keep implementation and live verification statuses distinct.
   - After offline checks and deployed retrieval validation pass, perform the single budget-gated live baseline and retain all run evidence. Any fixes requiring a new paid run need an explicit rerun within the remaining budget.

Implementation order: fixture alignment → evidence capture and Terraform → dataset and budget gate → job lifecycle and reports → offline verification → deployed baseline and manual review. Choose the numeric budget and evaluator/pricing configuration before paid execution; neither is required to begin implementation.
