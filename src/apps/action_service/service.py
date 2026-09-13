"""Durable submission intent committed before any independent core write."""
import json
from insurance_domain.intake import Confirmation, DomainError
from apps.storage import reference, encode
from workflows.auto import draft_from


def prepare(db, conversation, state, owner, confirmation, core):
    draft = draft_from(state)
    core.validate_draft(owner, draft)
    Confirmation(draft.intake_ref, confirmation["draft_version"],
                 confirmation["payload_hash"]).validate(draft)
    existing = db.execute("SELECT * FROM actions WHERE conversation=?", (conversation,)).fetchone()
    if existing:
        if existing["payload_hash"] != draft.digest:
            raise DomainError("submission_already_started")
        return existing["id"]
    action = reference("action")
    db.execute("INSERT INTO actions VALUES (?,?,?,?,?,?)",
               (action, conversation, draft.digest, "pending", None, encode(state)))
    return action


def execute(db, action_id, owner, state, core):
    action = db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
    if action is None:
        raise DomainError("stale_action")
    draft = draft_from(json.loads(action["payload"]))
    if action["payload_hash"] != draft.digest:
        raise DomainError("stale_action")
    if action["status"] == "confirmed":
        return json.loads(action["receipt"])
    try:
        # Always reconcile first, including after a worker crash between core
        # success and the local receipt commit.
        receipt = core.lookup(action_id)
        if receipt is None:
            receipt = core.submit(action_id, owner, draft)
    except (TimeoutError, ConnectionError):
        db.execute("UPDATE actions SET status='unknown' WHERE id=?", (action_id,))
        return None
    db.execute("UPDATE actions SET status='confirmed',receipt=? WHERE id=?",
               (encode(receipt), action_id))
    return receipt
