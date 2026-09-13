"""Durable review interrupts. Business records authorize and reconcile resumes."""
from typing import TypedDict
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from insurance_domain.intake import DomainError


class ReviewState(TypedDict, total=False):
    review_ref: str
    draft_version: int
    workflow_version: str
    decision: dict


def review_node(state):
    return {"decision": interrupt({"review_ref": state["review_ref"], "draft_version": state["draft_version"]})}


class ReviewWorkflow:
    def __init__(self, path):
        self.path = path

    def run(self, review, decision=None):
        config = {"configurable": {"thread_id": f'{review["id"]}_{review["version"]}'}}
        with SqliteSaver.from_conn_string(self.path) as saver:
            builder = StateGraph(ReviewState)
            builder.add_node("employee_review", review_node)
            builder.add_edge(START, "employee_review")
            builder.add_edge("employee_review", END)
            graph = builder.compile(checkpointer=saver)
            snapshot = graph.get_state(config)
            # Only called after the application verifies a pending review.
            # A completed checkpoint here can belong to a rolled-back decision;
            # business records, not that orphan checkpoint, own authorization.
            if not snapshot.values or (snapshot.values.get("decision") and
                                       snapshot.values["decision"] != decision):
                graph.invoke({"review_ref": review["id"], "draft_version": review["version"],
                              "workflow_version": "review_v1", "decision": None}, config)
                snapshot = graph.get_state(config)
            if decision is not None:
                if snapshot.values.get("decision"):
                    if snapshot.values["decision"] != decision:
                        raise DomainError("idempotency_conflict")
                else:
                    graph.invoke(Command(resume=decision), config)
            return graph.get_state(config)
