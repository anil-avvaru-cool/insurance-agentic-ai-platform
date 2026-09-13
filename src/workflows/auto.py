"""Pure LangGraph planning; durable business writes belong to the worker.

Each material update is re-evaluated from persisted application state. No model
or external side effect executes inside replayable graph nodes.
"""
from dataclasses import asdict
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from workflows.checkpoints import Checkpoints
from insurance_domain.intake import AutoDraft, Fact
from insurance_domain.urgency import screen


class State(TypedDict, total=False):
    schema_version: str
    workflow_version: str
    conversation_ref: str
    intake_ref: str
    version: int
    facts: dict
    missing_fields: list[str]
    urgency: dict
    triage: dict
    handoff_required: bool
    stage: str
    receipt: dict | None


def draft_from(state):
    return AutoDraft(state["intake_ref"], state["version"], tuple(
        (name, Fact(**fact)) for name, fact in sorted(state["facts"].items())))


def urgency_node(state):
    urgency = asdict(screen(draft_from(state)))
    previous = state.get("urgency")
    # Keep an explicit urgent trigger until employee handling; later edits must
    # never silently clear the persisted alert or lower the recommendation.
    if previous and previous["priority"] == "urgent":
        urgency["priority"] = "urgent"
        for key in ("reason_codes", "evidence_refs"):
            urgency[key] = sorted(set(urgency[key]) | set(previous[key]))
    return {"urgency": urgency, "handoff_required": urgency["priority"] == "urgent"}


def intake_node(state):
    missing = list(draft_from(state).missing_fields)
    return {"missing_fields": missing,
            "stage": "awaiting_customer" if missing else "awaiting_confirmation"}


def triage_node(state, catalogs):
    urgency = state["urgency"]
    return {"stage": "awaiting_review", "triage": {
        **urgency,
        "recommended_team": catalogs.team(urgency["priority"]),
        "review_required": True, "catalog_version": catalogs.data["version"],
    }}


def build_graph(catalogs, checkpointer=None):
    graph = StateGraph(State)
    graph.add_node("urgency_screening", urgency_node)
    graph.add_node("intake_validation", intake_node)
    graph.add_node("triage_recommendation", lambda state: triage_node(state, catalogs))
    graph.add_edge(START, "urgency_screening")
    graph.add_conditional_edges("urgency_screening", lambda s: "triage_recommendation"
                               if s.get("receipt") else "intake_validation")
    graph.add_edge("intake_validation", END)
    graph.add_edge("triage_recommendation", END)
    return graph.compile(checkpointer=checkpointer)


class AutoWorkflow:
    def __init__(self, catalogs, path, checkpoints=None):
        self.catalogs, self.path = catalogs, path
        self.checkpoints = checkpoints if checkpoints is not None else Checkpoints("sqlite", path)

    def invoke(self, state):
        # Application state is authoritative when recovering separate commits.
        with self.checkpoints.connect() as saver:
            graph = build_graph(self.catalogs, saver)
            # Clear channels absent from the authoritative snapshot. A prior
            # checkpoint may have committed before its application transaction.
            authoritative = {key: None for key in State.__annotations__}
            authoritative.update(state)
            return graph.invoke(authoritative, {"configurable": {"thread_id": state["conversation_ref"] + "_planning"}})
