"""Pure LangGraph planning; durable business writes belong to the worker.

Each material update is re-evaluated from persisted application state. No model
or external side effect executes inside replayable graph nodes.
"""
from dataclasses import asdict
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
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


def triage_node(state):
    urgency = state["urgency"]
    return {"stage": "awaiting_review", "triage": {
        **urgency,
        "recommended_team": "auto_priority" if urgency["priority"] == "urgent" else "auto_standard",
        "review_required": True,
    }}


def build_graph():
    graph = StateGraph(State)
    graph.add_node("urgency_screening", urgency_node)
    graph.add_node("intake_validation", intake_node)
    graph.add_node("triage_recommendation", triage_node)
    graph.add_edge(START, "urgency_screening")
    graph.add_conditional_edges("urgency_screening", lambda s: "triage_recommendation"
                               if s.get("receipt") else "intake_validation")
    graph.add_edge("intake_validation", END)
    graph.add_edge("triage_recommendation", END)
    return graph.compile()
