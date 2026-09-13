"""Synthetic urgency screening runs even when intake is incomplete."""

from dataclasses import dataclass
import json
import os
from pathlib import Path

from .intake import AutoDraft, DomainError


@dataclass(frozen=True)
class Urgency:
    priority: str
    reason_codes: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    missing_fields: tuple[str, ...]
    rule_version: str
    review_required: bool = True


def screen(draft: AutoDraft) -> Urgency:
    rules = json.loads(Path(os.environ["AUTO_RULES_PATH"]).read_text())
    if (rules["production_approved"] is not False
            or rules["urgent_triggers"] != {"injury_reported": "yes", "drivable": "no"}
            or not isinstance(rules["rule_version"], str)
            or not rules["rule_version"].strip()):
        raise DomainError("unsupported_rule_bundle")
    facts = dict(draft.facts)
    reasons, evidence, missing = [], [], []
    for name, trigger in rules["urgent_triggers"].items():
        fact = facts.get(name)
        # A reported urgent fact is actionable even before customer confirmation.
        if fact and fact.value == trigger:
            reasons.append(name)
            evidence.append(fact.source_ref)
        if fact is None or fact.value == "unknown" or fact.conflicting:
            missing.append(name)
    return Urgency(
        "urgent" if reasons else "needs_clarification" if missing else "routine",
        tuple(reasons), tuple(evidence), tuple(missing), rules["rule_version"],
    )
