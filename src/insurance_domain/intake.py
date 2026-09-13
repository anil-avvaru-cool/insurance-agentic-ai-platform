"""Immutable local intake contracts; no authorization or external writes."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json


class DomainError(ValueError):
    """Stable domain error code, safe to map at an API boundary."""


class ReportedStatus(StrEnum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Fact:
    value: str
    source_ref: str
    confirmed: bool
    conflicting: bool = False

    def __post_init__(self):
        if not isinstance(self.value, str) or not self.value.strip():
            raise DomainError("invalid_fact")
        if not isinstance(self.source_ref, str) or not self.source_ref.strip():
            raise DomainError("missing_source")
        if type(self.confirmed) is not bool or type(self.conflicting) is not bool:
            raise DomainError("invalid_fact_status")


AUTO_FIELDS = (
    "policy_ref", "incident_at", "description", "location_ref",
    "vehicle_ref", "contact_ref", "injury_reported", "drivable",
)


@dataclass(frozen=True)
class AutoDraft:
    intake_ref: str
    version: int = 1
    facts: tuple[tuple[str, Fact], ...] = ()

    def __post_init__(self):
        if not isinstance(self.intake_ref, str) or not self.intake_ref.strip():
            raise DomainError("invalid_intake_ref")
        if type(self.version) is not int or self.version < 1:
            raise DomainError("invalid_version")
        if not isinstance(self.facts, tuple):
            raise DomainError("invalid_facts")
        names = []
        for pair in self.facts:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise DomainError("invalid_fact_entry")
            name, fact = pair
            if name not in AUTO_FIELDS or not isinstance(fact, Fact):
                raise DomainError("invalid_field")
            names.append(name)
            if name in ("injury_reported", "drivable"):
                try:
                    ReportedStatus(fact.value)
                except ValueError as exc:
                    raise DomainError("invalid_reported_status") from exc
            if name == "incident_at":
                try:
                    datetime.fromisoformat(fact.value)
                except ValueError as exc:
                    raise DomainError("invalid_incident_at") from exc
        if len(names) != len(set(names)):
            raise DomainError("duplicate_field")

    def update(self, name: str, fact: Fact) -> "AutoDraft":
        facts = dict(self.facts)
        if facts.get(name) == fact:
            return self
        facts[name] = fact
        return replace(self, version=self.version + 1, facts=tuple(sorted(facts.items())))

    @property
    def missing_fields(self) -> tuple[str, ...]:
        facts = dict(self.facts)
        return tuple(name for name in AUTO_FIELDS if name not in facts
                     or not facts[name].confirmed or facts[name].conflicting)

    @property
    def digest(self) -> str:
        payload = [self.intake_ref, self.version, [
            [name, fact.value, fact.source_ref, fact.confirmed, fact.conflicting]
            for name, fact in sorted(self.facts)
        ]]
        return sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Confirmation:
    intake_ref: str
    draft_version: int
    payload_hash: str

    @classmethod
    def for_draft(cls, draft: AutoDraft) -> "Confirmation":
        if draft.missing_fields:
            raise DomainError("incomplete_intake")
        return cls(draft.intake_ref, draft.version, draft.digest)

    def validate(self, draft: AutoDraft) -> None:
        if self != Confirmation.for_draft(draft):
            raise DomainError("stale_confirmation")
