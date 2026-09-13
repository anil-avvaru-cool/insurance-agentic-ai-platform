# Insurance agentic AI platform

Phase 1 now includes a runnable **local synthetic auto journey**: authenticated
HTTP contracts, sourced intake facts, customer confirmation, durable queued work,
mock claims receipts, urgency handoffs, and employee review. AWS and real claims
systems are not connected. The broader Phase 1 rollout remains pending; see the
[implementation status](docs/PHASE_1_STATUS.md).

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
  persist pauses and resume context; a persistent LangGraph checkpointer and
  `interrupt()`/`Command` review flow remain pending.
- Static bearer fixtures enforce customer ownership. Employees have access to
  the single synthetic queue. Production identity, reviewer scope delegation,
  and workload/action-service isolation remain pending.
- Inputs are structured facts with explicit intents. Natural-language extraction,
  model generation, RAG, evidence uploads, and pre-authentication help remain
  pending. The one process FAQ is synthetic and is not an approved RAG corpus.
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
