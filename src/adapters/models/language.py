"""Provider independent, evidence-bound interpretation contracts."""
from typing import Literal, Protocol
from pydantic import Field
from contracts.api import Contract
from insurance_domain.intake import AUTO_FIELDS, DomainError

PROMPT_VERSION = "auto_interpretation_v1"


class ExtractedFact(Contract):
    name: Literal[*AUTO_FIELDS]
    value: str = Field(min_length=1, max_length=2000)
    quote: str = Field(min_length=1, max_length=2000)


class Interpretation(Contract):
    intent: Literal["intake", "policy_status", "claim_status", "service", "employee_help"]
    facts: list[ExtractedFact]
    object_ref: str | None
    source_ref: str | None

    def grounded(self, text):
        names = set()
        for fact in self.facts:
            if fact.name in names or fact.quote not in text:
                raise DomainError("ungrounded_extraction")
            names.add(fact.name)
            if fact.name not in ("injury_reported", "drivable") and fact.value not in fact.quote:
                raise DomainError("ungrounded_extraction")
            if fact.name in ("injury_reported", "drivable") and fact.value not in ("yes", "no", "unknown"):
                raise DomainError("invalid_reported_status")
        if self.object_ref and self.object_ref not in text:
            raise DomainError("ungrounded_extraction")
        return self


class LanguageAdapter(Protocol):
    def interpret(self, text: str, sources: list[dict]) -> tuple[Interpretation, dict]: ...


class DisabledLanguage:
    def interpret(self, text, sources):
        raise DomainError("language_unavailable")
