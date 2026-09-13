"""Synthetic core with an independent receipt store and stable idempotency keys."""
import json
from contextlib import closing
import sqlite3
from pathlib import Path
from apps.storage import reference, encode
from insurance_domain.intake import DomainError


class SyntheticCore:
    def __init__(self, fixture_path, receipt_path):
        self.fixtures = json.loads(Path(fixture_path).read_text())
        self.receipt_path = receipt_path
        with closing(sqlite3.connect(receipt_path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS receipts (action TEXT PRIMARY KEY, "
                       "owner TEXT NOT NULL, payload_hash TEXT NOT NULL, receipt TEXT NOT NULL)")

    def authorize(self, owner, kind, ref):
        item = self.fixtures[kind].get(ref)
        if item is None or item["owner"] != owner:
            raise DomainError("not_found")
        return item

    def validate_draft(self, owner, draft):
        facts = dict(draft.facts)
        for field, kind in (("policy_ref", "policies"), ("vehicle_ref", "vehicles"),
                            ("location_ref", "locations"), ("contact_ref", "contacts")):
            if field in facts:
                self.authorize(owner, kind, facts[field].value)
        if "vehicle_ref" in facts and "policy_ref" in facts:
            vehicle = self.authorize(owner, "vehicles", facts["vehicle_ref"].value)
            if vehicle["policy_ref"] != facts["policy_ref"].value:
                raise DomainError("invalid_vehicle_policy")

    def lookup(self, action_id):
        with closing(sqlite3.connect(self.receipt_path)) as db, db:
            row = db.execute("SELECT receipt FROM receipts WHERE action=?", (action_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def submit(self, action_id, owner, draft):
        self.validate_draft(owner, draft)
        with closing(sqlite3.connect(self.receipt_path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT owner,payload_hash,receipt FROM receipts WHERE action=?",
                             (action_id,)).fetchone()
            if row:
                if row[:2] != (owner, draft.digest):
                    raise DomainError("idempotency_conflict")
                return json.loads(row[2])
            receipt = {"intake_receipt": reference("receipt"), "claim_ref": reference("claim"),
                       "status": "received", "synthetic": True, "draft_version": draft.version}
            db.execute("INSERT INTO receipts VALUES (?,?,?,?)",
                       (action_id, owner, draft.digest, encode(receipt)))
            return receipt

    def claim_status(self, owner, claim_ref):
        with closing(sqlite3.connect(self.receipt_path)) as db, db:
            for (raw,) in db.execute("SELECT receipt FROM receipts WHERE owner=?", (owner,)):
                receipt = json.loads(raw)
                if receipt["claim_ref"] == claim_ref:
                    return receipt
        raise DomainError("not_found")
