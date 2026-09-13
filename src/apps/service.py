"""Application authorization, durable acceptance, and local worker execution."""
from dataclasses import asdict
import json
from apps.storage import reference, encode
from apps.action_service.service import prepare, execute
from insurance_domain.intake import DomainError, Fact
from workflows.auto import AutoWorkflow, draft_from
from workflows.review import ReviewWorkflow
from adapters.models.language import DisabledLanguage
from insurance_domain.catalogs import Catalogs
import os
import hashlib
import secrets


class Application:
    def __init__(self, store, core, language=None, catalogs=None, checkpoint_path=None):
        self.store, self.core = store, core
        self.catalogs = catalogs if catalogs is not None else Catalogs(os.environ["CATALOGS_PATH"])
        self.language = language if language is not None else DisabledLanguage()
        self.review_graph = ReviewWorkflow(checkpoint_path if checkpoint_path is not None else store.path + ".checkpoints")
        self.graph = AutoWorkflow(self.catalogs, self.review_graph.path)

    def owned(self, db, conversation, owner):
        row = db.execute("SELECT * FROM conversations WHERE id=? AND owner=?",
                         (conversation, owner)).fetchone()
        if row is None:
            raise DomainError("not_found")
        return json.loads(row["state"])

    def create(self, owner, help_token=None):
        if help_token:
            with self.store.transaction() as db:
                row = db.execute("SELECT * FROM help_sessions WHERE token_hash=?",
                                 (hashlib.sha256(help_token.encode()).hexdigest(),)).fetchone()
                if row is None:
                    raise DomainError("not_found")
                conversation = db.execute("SELECT * FROM conversations WHERE id=?", (row["conversation"],)).fetchone()
                if conversation["owner"] not in ("preauth", owner):
                    raise DomainError("not_found")
                db.execute("UPDATE conversations SET owner=? WHERE id=?", (owner, conversation["id"]))
                return {"conversation_ref": conversation["id"], **self.customer_state(json.loads(conversation["state"]))}
        conversation = reference("conversation")
        state = {"schema_version": "1", "workflow_version": "auto_local_v2",
                 "conversation_ref": conversation, "intake_ref": reference("intake"),
                 "version": 1, "facts": {}, "receipt": None, "stage": "awaiting_customer"}
        state = self.graph.invoke(state)
        with self.store.transaction() as db:
            db.execute("INSERT INTO conversations VALUES (?,?,?)", (conversation, owner, encode(state)))
        return {"conversation_ref": conversation, **self.customer_state(state)}

    def help(self, request):
        # request_id is a client-generated capability; only status enums are retained.
        digest = hashlib.sha256(encode(request).encode()).hexdigest()
        with self.store.transaction() as db:
            existing = db.execute("SELECT * FROM help_sessions WHERE request_id=?", (request["request_id"],)).fetchone()
            if existing:
                if existing["payload_hash"] != digest:
                    raise DomainError("idempotency_conflict")
                return json.loads(existing["result"])
            conversation, intake = reference("conversation"), reference("intake")
            state = {"schema_version": "1", "workflow_version": "auto_local_v2",
                     "conversation_ref": conversation, "intake_ref": intake, "version": 1,
                     "facts": {name: asdict(Fact(request[name], "preauth_status", False))
                               for name in ("injury_reported", "drivable")}, "receipt": None}
            state = self.graph.invoke(state)
            db.execute("INSERT INTO conversations VALUES (?,?,?)", (conversation, "preauth", encode(state)))
            self.upsert_review(db, conversation, state, "urgency" if state["handoff_required"] else "service",
                               {**state["urgency"], "reason": "preauth_help"})
            token = secrets.token_hex(32)
            result = {"help_token": token, "priority": state["urgency"]["priority"],
                      "review_pending": True, "message": self.catalogs.data["help_message"]}
            db.execute("INSERT INTO help_sessions VALUES (?,?,?,?,?)",
                       (request["request_id"], digest, hashlib.sha256(token.encode()).hexdigest(), conversation, encode(result)))
            return result

    @staticmethod
    def customer_state(state):
        return {"draft_version": state["version"], "payload_hash": draft_from(state).digest,
                "facts": state["facts"], "missing_fields": state["missing_fields"],
                "stage": state["stage"], "urgency": state["urgency"],
                "receipt": state.get("receipt"), "review_outcome": state.get("review_outcome"),
                "post_submission_changes": bool(state.get("receipt") and
                    state["receipt"]["draft_version"] != state["version"])}

    def enqueue(self, owner, conversation, key, payload):
        with self.store.transaction() as db:
            state = self.owned(db, conversation, owner)
            existing = db.execute("SELECT * FROM tasks WHERE conversation=? AND request_key=?",
                                  (conversation, key)).fetchone()
            if existing:
                if existing["payload"] != encode(payload):
                    raise DomainError("idempotency_conflict")
                return {"task_ref": existing["id"]}
            if db.execute("SELECT 1 FROM tasks WHERE conversation=? AND status IN ('queued','running')",
                          (conversation,)).fetchone():
                raise DomainError("conversation_busy")
            if payload["kind"] == "message":
                msg = payload["message"]
                if msg["expected_version"] != state["version"]:
                    raise DomainError("stale_version")
                if msg["facts"]:
                    candidate = draft_from(state)
                    for name, fact in msg["facts"].items():
                        candidate = candidate.update(name, Fact(source_ref=msg["message_id"], **fact))
                    self.core.validate_draft(owner, candidate)
                if msg["intent"] == "policy_status":
                    self.core.authorize(owner, "policies", msg["object_ref"])
                elif msg["intent"] == "claim_status":
                    self.core.claim_status(owner, msg["object_ref"])
            else:
                prepare(db, conversation, state, owner, payload["confirmation"], self.core)
            task = reference("task")
            db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?)",
                       (task, conversation, key, encode(payload), "queued", None))
            db.execute("INSERT INTO outbox(task) VALUES (?)", (task,))
            return {"task_ref": task}

    def get_task(self, owner, task):
        with self.store.transaction() as db:
            row = db.execute("SELECT t.* FROM tasks t JOIN conversations c ON c.id=t.conversation "
                             "WHERE t.id=? AND c.owner=?", (task, owner)).fetchone()
            if row is None:
                raise DomainError("not_found")
            return {"task_ref": row["id"], "status": row["status"],
                    "result": json.loads(row["result"]) if row["result"] else None}

    def upsert_review(self, db, conversation, state, kind, proposal):
        row = db.execute("SELECT * FROM reviews WHERE conversation=? AND kind=?",
                         (conversation, kind)).fetchone()
        if row is None:
            db.execute("INSERT INTO reviews VALUES (?,?,?,?,?,?)",
                       (reference("review"), conversation, kind, state["version"], "pending", encode(proposal)))
        elif row["version"] != state["version"]:
            db.execute("UPDATE reviews SET version=?,status='pending',proposal=? WHERE id=?",
                       (state["version"], encode(proposal), row["id"]))

        review = db.execute("SELECT * FROM reviews WHERE conversation=? AND kind=?", (conversation, kind)).fetchone()
        if review["status"] == "pending" and kind != "submission":
            self.review_graph.run(review)

    def work_once(self):
        # Local transaction lock provides serialization and automatic rollback
        # on worker death. AWS needs SQS leases/fencing and a separate dispatcher.
        with self.store.transaction() as db:
            task = db.execute("SELECT t.* FROM tasks t JOIN outbox o ON t.id=o.task "
                              "WHERE o.delivered=0 ORDER BY t.rowid LIMIT 1").fetchone()
            if task is None:
                return False
            row = db.execute("SELECT * FROM conversations WHERE id=?", (task["conversation"],)).fetchone()
            state, payload = json.loads(row["state"]), json.loads(task["payload"])
            db.execute("UPDATE tasks SET status='running' WHERE id=?", (task["id"],))
            try:
                result, status = self.process(db, row["owner"], state, payload)
            except DomainError as exc:
                result, status = {"error": str(exc)}, "failed"
            db.execute("UPDATE conversations SET state=? WHERE id=?", (encode(state), row["id"]))
            db.execute("UPDATE tasks SET status=?,result=? WHERE id=?", (status, encode(result), task["id"]))
            db.execute("UPDATE outbox SET delivered=1 WHERE task=?", (task["id"],))
        return True

    def process(self, db, owner, state, payload):
        conversation = state["conversation_ref"]
        answer = None
        changed = False
        if payload["kind"] == "message":
            msg = payload["message"]
            if msg["expected_version"] != state["version"]:
                raise DomainError("stale_version")
            if msg["intent"] == "auto":
                triggers = [name for name, phrases in self.catalogs.data["urgent_phrases"].items()
                            if any(phrase in msg["text"].casefold() for phrase in phrases)]
                if triggers:
                    state['version'] += 1
                    changed = True
                    state.pop('review_outcome', None)
                    db.execute("UPDATE reviews SET status='stale' WHERE conversation=? AND kind!='service'", (conversation,))
                    db.execute("UPDATE reviews SET version=? WHERE conversation=? AND kind='service' AND status='pending'",
                               (state['version'], conversation))
                    state["urgency"]["priority"] = "urgent"
                    state["urgency"]["reason_codes"] = sorted(set(state["urgency"]["reason_codes"]) | set(triggers))
                    state["urgency"]["evidence_refs"] = sorted(set(state["urgency"]["evidence_refs"]) | {msg["message_id"]})
                    state["handoff_required"] = True
                    self.upsert_review(db, conversation, state, "urgency", state["urgency"])
                msg = dict(msg)
                try:
                    interpreted, metadata = self.language.interpret(msg["text"], self.catalogs.sources())
                    interpreted.grounded(msg["text"])
                    msg.update(intent=interpreted.intent, object_ref=interpreted.object_ref,
                               question=interpreted.source_ref,
                               facts={f.name: {"value": f.value, "confirmed": False,
                                   "conflicting": bool(state["facts"].get(f.name) and
                                       state["facts"][f.name]["value"] != f.value)} for f in interpreted.facts})
                    candidate = draft_from(state)
                    for name, fact in msg["facts"].items():
                        candidate = candidate.update(name, Fact(source_ref=msg["message_id"], **fact))
                    self.core.validate_draft(owner, candidate)
                    if msg["intent"] == "policy_status":
                        self.core.authorize(owner, "policies", msg["object_ref"])
                    elif msg["intent"] == "claim_status":
                        self.core.claim_status(owner, msg["object_ref"])
                    state["model_run"] = metadata
                except DomainError:
                    msg.update(intent="employee_help", facts={})
            if msg["intent"] == "intake" or msg["facts"]:
                draft = draft_from(state)
                for name, fact in msg["facts"].items():
                    draft = draft.update(name, Fact(source_ref=msg["message_id"], **fact))
                self.core.validate_draft(owner, draft)
                changed = changed or draft.facts != draft_from(state).facts
                state["facts"] = {key: asdict(fact) for key, fact in draft.facts}
                if changed:
                    state["version"] += 1
                    state.pop("review_outcome", None)
                    db.execute("UPDATE reviews SET version=? WHERE conversation=? AND kind='service' AND status='pending'",
                               (state["version"], conversation))
                    db.execute("UPDATE reviews SET status='stale' WHERE conversation=? AND kind!='service'", (conversation,))
            if msg["intent"] == "policy_status":
                policy = self.core.authorize(owner, "policies", msg["object_ref"])
                answer = {"status": policy["status"], "source_ref": msg["object_ref"],
                          "source_version": policy["source_version"], "synthetic": True,
                          "message": "Policy status is not a coverage determination."}
            elif msg["intent"] == "claim_status":
                answer = self.core.claim_status(owner, msg["object_ref"])
            elif msg["intent"] == "service":
                try:
                    answer = self.catalogs.answer(msg["question"])
                except DomainError:
                    msg["intent"] = "employee_help"
            if msg["intent"] == "employee_help":
                previous = db.execute("SELECT status FROM reviews WHERE conversation=? AND kind='service'",
                                      (conversation,)).fetchone()
                if previous and previous["status"] != "pending":
                    state["version"] += 1
                self.upsert_review(db, conversation, state, "service", {"reason": "employee_help"})
                answer = {"message": "Employee help requested. No coverage decision has been made.",
                          "review_pending": True}
        else:
            action = db.execute("SELECT id FROM actions WHERE conversation=?", (conversation,)).fetchone()
            receipt = execute(db, action["id"], owner, state, self.core)
            if receipt is None:
                state["stage"] = "pending_submission"
                self.upsert_review(db, conversation, state, "submission", {"reason": "unknown_submission"})
                return {**self.customer_state(state), "message": "Submission outcome unknown; reconciliation required."}, "awaiting_review"
            state["receipt"] = receipt

        if changed or (answer is None and (payload["kind"] == "confirmation" or not state.get("receipt"))):
            state.update(self.graph.invoke(state))
        if state["handoff_required"]:
            self.upsert_review(db, conversation, state, "urgency", state["urgency"])
        if state.get("receipt"):
            self.upsert_review(db, conversation, state, "triage", state["triage"])
        pending_action = db.execute("SELECT status FROM actions WHERE conversation=?", (conversation,)).fetchone()
        if pending_action and pending_action["status"] == "unknown":
            state["stage"] = "pending_submission"
            self.upsert_review(db, conversation, state, "submission", {"reason": "unknown_submission"})
        result = self.customer_state(state)
        if answer is not None:
            result["answer"] = answer
            status = "awaiting_review" if answer.get("review_pending") else "completed"
            if answer.get("review_pending"):
                result["pending_review_ref"] = db.execute(
                    "SELECT id FROM reviews WHERE conversation=? AND kind='service'", (conversation,)
                ).fetchone()["id"]
        else:
            status = ("completed" if state["stage"] == "review_completed" else
                      "awaiting_review" if state["stage"] in ("awaiting_review", "pending_submission") else
                      "awaiting_customer")
        return result, status

    def reconcile(self):
        """Bounded local recovery: one attempt per unknown action per invocation."""
        with self.store.transaction() as db:
            rows = db.execute("SELECT a.*,c.owner,c.state FROM actions a JOIN conversations c "
                              "ON c.id=a.conversation WHERE a.status='unknown'").fetchall()
            for row in rows:
                state = json.loads(row["state"])
                receipt = execute(db, row["id"], row["owner"], state, self.core)
                if receipt:
                    state["receipt"] = receipt
                    db.execute("UPDATE reviews SET status='reconciled' WHERE conversation=? AND kind='submission'",
                               (row["conversation"],))
                    state.update(self.graph.invoke(state))
                    self.upsert_review(db, row["conversation"], state, "triage", state["triage"])
                    db.execute("UPDATE conversations SET state=? WHERE id=?", (encode(state), row["conversation"]))
                    db.execute("UPDATE tasks SET result=? WHERE conversation=? AND request_key LIKE 'confirmation_%'",
                               (encode(self.customer_state(state)), row["conversation"]))

    def reviews(self):
        with self.store.transaction() as db:
            items = []
            for row in db.execute("SELECT r.*,c.state FROM reviews r JOIN conversations c "
                                  "ON c.id=r.conversation WHERE r.status='pending' ORDER BY r.rowid"):
                item = dict(row)
                item["context"] = self.customer_state(json.loads(item.pop("state")))
                item["proposal"] = json.loads(item["proposal"])
                items.append(item)
            return items

    def decide(self, reviewer, review_id, decision):
        with self.store.transaction() as db:
            existing = db.execute("SELECT * FROM decisions WHERE id=?", (decision["decision_id"],)).fetchone()
            if existing:
                if (existing["review"], existing["reviewer"], existing["payload"]) != (review_id, reviewer, encode(decision)):
                    raise DomainError("idempotency_conflict")
                return json.loads(existing["result"])
            review = db.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
            if review is None:
                raise DomainError("not_found")
            row = db.execute("SELECT state FROM conversations WHERE id=?", (review["conversation"],)).fetchone()
            state = json.loads(row["state"])
            if db.execute("SELECT 1 FROM tasks WHERE conversation=? AND status IN ('queued','running')",
                          (review["conversation"],)).fetchone():
                raise DomainError("conversation_busy")
            if review["status"] != "pending" or review["version"] != decision["expected_version"] or state["version"] != review["version"]:
                raise DomainError("stale_review")
            if review["kind"] == "submission":
                raise DomainError("reconciliation_required")
            proposal = json.loads(review["proposal"])
            if decision["decision"] == "amend":
                if review["kind"] != "triage":
                    raise DomainError("invalid_amendment")
                if decision["recommended_team"] not in self.catalogs.teams:
                    raise DomainError("invalid_team")
                if state["urgency"]["priority"] == "urgent" and decision["recommended_team"] != self.catalogs.team("urgent"):
                    raise DomainError("urgency_floor")
                proposal["recommended_team"] = decision["recommended_team"]
            result = {"review_ref": review_id, "decision": decision["decision"],
                      "assignment_confirmed": False}
            if decision["decision"] in ("accept", "amend"):
                result["reviewed_recommendation"] = proposal
            self.review_graph.run(review, {"reviewer": reviewer, **decision})
            db.execute("UPDATE reviews SET status=? WHERE id=?", (decision["decision"], review_id))
            db.execute("INSERT INTO decisions VALUES (?,?,?,?,?)",
                       (decision["decision_id"], review_id, reviewer, encode(decision), encode(result)))
            if review["kind"] == "service":
                for task in db.execute("SELECT id,result FROM tasks WHERE conversation=? AND status='awaiting_review'",
                                       (review["conversation"],)).fetchall():
                    task_result = json.loads(task["result"])
                    if task_result.get("pending_review_ref") == review_id:
                        task_result["review_outcome"] = result
                        task_result["answer"]["review_pending"] = False
                        next_status = "awaiting_customer" if decision["decision"] == "request_information" else "completed"
                        db.execute("UPDATE tasks SET status=?,result=? WHERE id=?",
                                   (next_status, encode(task_result), task["id"]))
            if review["kind"] == "triage":
                state["review_outcome"] = result
                state["stage"] = "awaiting_customer" if decision["decision"] == "request_information" else "review_completed"
                db.execute("UPDATE conversations SET state=? WHERE id=?", (encode(state), review["conversation"]))
                db.execute("UPDATE tasks SET status=?,result=? WHERE conversation=? AND status='awaiting_review' "
                           "AND request_key LIKE 'confirmation_%'",
                           ("awaiting_customer" if decision["decision"] == "request_information" else "completed",
                            encode(self.customer_state(state)), review["conversation"]))
            return result
