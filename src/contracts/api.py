"""Strict local HTTP contracts. Identity is never accepted in request payloads."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from insurance_domain.intake import AUTO_FIELDS


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FactInput(Contract):
    value: str = Field(min_length=1, max_length=2000)
    confirmed: bool
    conflicting: bool = False


class Message(Contract):
    message_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_]+$")
    intent: Literal["intake", "policy_status", "claim_status", "service", "employee_help"]
    expected_version: int = Field(ge=1)
    facts: dict[str, FactInput] = Field(default_factory=dict)
    object_ref: str | None = Field(default=None, max_length=100)
    question: Literal["report_loss", "coverage", "other"] | None = None

    @model_validator(mode="after")
    def validate_facts(self):
        if set(self.facts) - set(AUTO_FIELDS):
            raise ValueError("invalid_field")
        if self.facts and self.intent != "intake":
            raise ValueError("facts_require_intake")
        return self


class IntakeConfirmation(Contract):
    draft_version: int = Field(ge=1)
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReviewDecision(Contract):
    decision_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_]+$")
    expected_version: int = Field(ge=1)
    decision: Literal["accept", "amend", "reject", "request_information"]
    recommended_team: Literal["auto_standard", "auto_priority"] | None = None
    note: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_amendment(self):
        if (self.decision == "amend") != (self.recommended_team is not None):
            raise ValueError("team_requires_amendment")
        return self
