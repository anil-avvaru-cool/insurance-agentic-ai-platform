# Insurance agentic AI platform

Phase 1 now includes a runnable **local synthetic auto journey**: authenticated
HTTP contracts, sourced intake facts, customer confirmation, durable queued work,
mock claims receipts, urgency handoffs, and employee review. AWS and real claims
systems are not connected. The broader Phase 1 rollout remains pending; see the
[implementation status](docs/PHASE_1_STATUS.md).

Phase 1B has started with selectable PostgreSQL planning/review checkpoints and
a recovery evaluation runner. See the [spike runbook](docs/PHASE_1B_SPIKE.md)
for migration and verification commands. The [Terraform foundation](infra/terraform/README.md)
adds separate bootstrap/development roots for state, RDS, SQS and service identities;
AWS deployment remains pending. Existing `.env` files now require
`CHECKPOINT_BACKEND=sqlite` to keep the local setup.

Use Python 3.14 and UV. Copy `example.env` to `.env` for a new setup; if `.env`
already exists, add its missing settings from the template without replacing
existing secrets. All settings are required. The template tokens are public
synthetic fixtures and must only be used locally.

```sh
uv sync --locked
PYTHONPATH=src uv run --env-file .env uvicorn apps.api.main:create_app --factory --host 127.0.0.1
```

Open `http://127.0.0.1:8000` for customer intake and employee review, or `/docs`
for the HTTP contracts. Enter a configured customer token, start a conversation,
and save facts. In another terminal, drain accepted tasks:

```sh
PYTHONPATH=src uv run --env-file .env python -m apps.worker.main
```

The worker runs once and exits after draining the outbox and attempting one
reconciliation per uncertain action. Run it again after each queued message or
confirmation, then refresh the browser. The interface deliberately displays
queued work until the worker runs. Persist the conversation reference to resume
later. Switch to the configured employee token to review the queue.

Example facts for `customer_one`:

| Field | Synthetic value |
|---|---|
| Policy | `synthetic_policy` |
| Incident date/time | `2026-09-12T10:00:00-04:00` |
| Description | `Parked vehicle struck` |
| Location | `synthetic_location` |
| Vehicle | `synthetic_vehicle` |
| Contact | `synthetic_contact` |
| Injury reported | `no` (or `yes` / `unknown`) |
| Drivable | `yes` (or `no` / `unknown`) |

Save and refresh the draft, review its facts, confirm the displayed version,
run the worker, and refresh to see the mock receipt. Every triage recommendation
requires employee review. Accept/amend records a reviewed recommendation;
assignment is never reported as confirmed. Rejection performs no claims write.
Request-information returns the submission task to awaiting-customer.

Run the deterministic and HTTP/recovery suites:

```sh
PYTHONPATH=src uv run --locked python -m unittest discover -s tests/unit -v
PYTHONPATH=src uv run --locked python -m unittest discover -s tests/integration -v
```

The tests use temporary databases and synthetic identities. They do not need
`.env`, model credentials, AWS, or a running server. Dependencies are pinned in
`pyproject.toml` and resolved in `uv.lock`.

## Local implementation boundaries

- SQLite application state persists tasks, an outbox, drafts, action intents,
  review proposals, and audited decisions. A separate SQLite mock core persists
  idempotent receipts. Database paths come from configuration.
- LangGraph performs pure urgency/intake/triage transitions. Application records
  authorize pauses and resume context. A separate SQLite LangGraph checkpointer
  persists planning and `interrupt()`/`Command` employee reviews across restarts.
  Application records reconcile checkpoints left by rolled-back transactions.
- Static bearer fixtures enforce customer ownership. Employees have access to
  the single synthetic queue. Production identity, reviewer scope delegation,
  and workload/action-service isolation remain pending.
- Inputs support structured facts and optional natural-language interpretation
  through the OpenAI Responses adapter. Extracted facts stay unconfirmed until
  customer review; errors and unsupported requests produce employee handoffs.
  `LLM_PROVIDER=disabled` keeps the demo offline. Live model quality evaluation
  requires a configured key and remains pending.
- Versioned local customer sources and team catalogs come from `CATALOGS_PATH`.
  Source approval, audience, line, and effective dates filter service answers.
  These synthetic sources are not a production-approved RAG corpus; Bedrock
  retrieval and protected evidence uploads remain later milestones.
- `/v1/help` accepts only injury/drivability status before authentication. Its
  random request ID deduplicates retries; its capability token attaches the
  handoff to one authenticated owner. Keep both values private.
- Material fact changes invalidate pending review versions. Explicit urgency is
  retained across edits. Facts reported after submission remain local review
  context; the receipt identifies the original submitted draft version.
- Action intent and the original confirmed snapshot commit before a core write.
  After timeout or restart the worker checks the stable action ID before retrying.
  Unknown outcomes stay pending and cannot be approved into a second submission.
- Local workers serialize through a SQLite transaction. SQS dispatch, distributed
  leases, bounded retry/DLQ policy, telemetry, and PostgreSQL migration are pending.

Source layout: `src/contracts`, `src/insurance_domain`, `src/workflows`,
`src/apps/{api,web,worker,action_service}`, and `src/adapters/insurance`.
Synthetic fixtures and urgency rules live in `policies`; they require claims
owner approval before production use.

## Additional 1A verification

Install Chromium and its OS dependencies, then run the browser journey:

```sh
uv run --locked playwright install --with-deps chromium
PYTHONPATH=src uv run --locked python -m unittest discover -s tests/browser -v
```

The browser test starts a temporary localhost API and processes work through the
real worker methods. It requires permission to bind sockets and launch Chromium.
On Ubuntu 26.04 the pinned Playwright release needs
`PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64` for its fallback browser.

To evaluate the configured model against nine synthetic language cases, set
`OPENAI_API_KEY` and the model settings from `example.env`, then run:

```sh
PYTHONPATH=src uv run --env-file .env --locked python tests/evaluation/run_language.py
```

This command makes paid provider calls, reports model/prompt/catalog versions,
usage and latency, and exits nonzero if any case fails. Offline tests use mocked
provider responses and verify contracts and workflow controls; they do not measure
live language quality. The evaluation does not establish production readiness.
The transport follows the official [Structured Outputs contract](https://developers.openai.com/api/docs/guides/structured-outputs).
