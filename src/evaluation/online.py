"""Shared deterministic checks for online API and judge evidence."""
import re

INSUFFICIENT = "The selected policy document does not provide this information."


def check_answer(case, body):
    """Check observable contract, isolation and amounts, not semantic correctness."""
    errors = []
    if not isinstance(body, dict):
        return ["response must be a JSON object"]
    if not isinstance(body.get("request_id"), str) or not body["request_id"].strip():
        errors.append("missing request_id")
    answer, citations = body.get("answer"), body.get("citations")
    if not isinstance(answer, str) or not answer.strip():
        errors.append("missing answer")
    if not isinstance(citations, list):
        return errors + ["citations must be a list"]
    for citation in citations:
        if not isinstance(citation, dict):
            errors.append("invalid citation")
            continue
        if citation.get("document_id") not in case["allowed_document_ids"]:
            errors.append("citation outside allowed documents")
        if citation.get("lob") != case["lob"]:
            errors.append("citation LOB mismatch")
        if not citation.get("source") or not citation.get("evidence_id"):
            errors.append("citation missing source or evidence_id")
    if case["expected_status"] == "insufficient_information":
        if answer != INSUFFICIENT or citations:
            errors.append("expected controlled insufficient-information response without citations")
    else:
        if not citations or answer == INSUFFICIENT:
            errors.append("supported question needs an answer with citations")
        # This catches swapped owner amounts, but cannot assess negation or grounding.
        amounts = lambda text: set(re.findall(r"\$\s*(\d+(?:\.\d+)?)", text.replace(",", "")))
        if isinstance(answer, str) and not amounts(case["expected_answer"]).issubset(amounts(answer)):
            errors.append("expected monetary amount missing")
    return errors

