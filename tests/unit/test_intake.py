import os
import unittest
from unittest.mock import patch

from insurance_domain.intake import AutoDraft, Confirmation, DomainError, Fact
from insurance_domain.urgency import screen


def complete_draft():
    values = {
        "policy_ref": "synthetic_policy", "incident_at": "2026-09-12T10:00:00-04:00",
        "description": "Parked vehicle struck", "location_ref": "synthetic_location",
        "vehicle_ref": "synthetic_vehicle", "contact_ref": "synthetic_contact",
        "injury_reported": "no", "drivable": "yes",
    }
    return AutoDraft("synthetic_intake", facts=tuple(
        (key, Fact(value, "customer_message_1", True)) for key, value in values.items()
    ))


class IntakeTests(unittest.TestCase):
    def test_complete_draft_confirmation(self):
        draft = complete_draft()
        Confirmation.for_draft(draft).validate(draft)

    def test_edit_invalidates_confirmation(self):
        draft = complete_draft()
        confirmation = Confirmation.for_draft(draft)
        changed = draft.update("drivable", Fact("no", "customer_message_2", True))
        with self.assertRaisesRegex(DomainError, "stale_confirmation"):
            confirmation.validate(changed)

    def test_confirmation_cannot_cross_intakes(self):
        draft = complete_draft()
        other = AutoDraft("other_intake", facts=draft.facts)
        with self.assertRaisesRegex(DomainError, "stale_confirmation"):
            Confirmation.for_draft(draft).validate(other)

    def test_incomplete_conflicting_and_unconfirmed_facts(self):
        for draft in (AutoDraft("draft"), complete_draft().update(
            "incident_at", Fact("2026-09-11", "message_2", True, True)),
            complete_draft().update("drivable", Fact("yes", "message_2", False))):
            with self.assertRaisesRegex(DomainError, "incomplete_intake"):
                Confirmation.for_draft(draft)

    def test_invalid_status_and_date_rejected(self):
        for name, value in (("drivable", "maybe"), ("incident_at", "yesterday")):
            with self.assertRaises(DomainError):
                complete_draft().update(name, Fact(value, "message", True))

    def test_unknown_is_explicit_and_can_be_reported(self):
        draft = complete_draft().update("injury_reported", Fact("unknown", "message", True))
        Confirmation.for_draft(draft).validate(draft)
        with patch.dict(os.environ, AUTO_RULES_PATH="config/business_rules/auto_synthetic_v1.json"):
            self.assertEqual(screen(draft).priority, "needs_clarification")

    def test_early_urgency_does_not_wait_for_complete_intake(self):
        for name, value in (("injury_reported", "yes"), ("drivable", "no")):
            draft = AutoDraft("draft").update(name, Fact(value, "message", False, True))
            with patch.dict(os.environ, AUTO_RULES_PATH="config/business_rules/auto_synthetic_v1.json"):
                result = screen(draft)
            self.assertEqual(result.priority, "urgent")
            self.assertEqual(result.evidence_refs, ("message",))
            self.assertTrue(result.review_required)

    def test_missing_configuration_fails_fast(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(KeyError):
                screen(complete_draft())

    def test_duplicate_fields_rejected(self):
        fact = Fact("yes", "message", True)
        with self.assertRaisesRegex(DomainError, "duplicate_field"):
            AutoDraft("draft", facts=(("drivable", fact), ("drivable", fact)))


if __name__ == "__main__":
    unittest.main()
