"""Opt-in live Phase 1 API checks; see docs/ONLINE_RAG_TESTING.md."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
import uuid

import httpx
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


ROOT = Path(__file__).resolve().parents[1]
INSUFFICIENT = "The selected policy document does not provide this information."


class RequestSigner:
    def __init__(self, session):
        self.session = session
        self.secrets = set()

    def headers(self, endpoint, payload):
        credentials = self.session.get_credentials()
        if credentials is None:
            raise RuntimeError("No AWS credentials found; configure your AWS profile.")
        frozen = credentials.get_frozen_credentials()
        self.secrets.update(value for value in (frozen.access_key, frozen.secret_key, frozen.token) if value)
        request = AWSRequest(method="POST", url=endpoint, data=payload, headers={"Content-Type": "application/json"})
        SigV4Auth(frozen, "execute-api", self.session.region_name).add_auth(request)
        self.secrets.add(request.headers["Authorization"])
        return dict(request.headers)


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


def scenarios(fixtures):
    for case in fixtures:
        payload = {"question": case["question"], "lob": case["lob"], "owner_id": case["owner_id"]}
        yield case["case_id"], "signed", payload, 200, case


def run(client, endpoint, cases, interval, signer):
    results = []
    for index, (name, auth_mode, payload, expected_status, fixture) in enumerate(cases):
        if index:
            time.sleep(interval)
        started = time.monotonic()
        result = {"case_id": name, "expected_http_status": expected_status}
        errors = []
        try:
            encoded = json.dumps(payload, separators=(",", ":")).encode()
            headers = {"Content-Type": "application/json"}
            if auth_mode != "unsigned":
                headers = signer.headers(endpoint, encoded)
                if auth_mode == "invalid":
                    headers["Authorization"] = headers["Authorization"].split("Signature=")[0] + "Signature=" + "0" * 64
            response = client.post(endpoint, content=encoded, headers=headers)
            result["http_status"] = response.status_code
            if response.status_code != expected_status:
                errors.append(f"expected HTTP {expected_status}, got {response.status_code}")
            try:
                body = response.json()
            except ValueError:
                body = None
                errors.append("response is not JSON")
            result["response"] = body
            if fixture:
                result["expected_answer"] = fixture["expected_answer"]
                result["supporting_passages"] = fixture["supporting_passages"]
                errors.extend(check_answer(fixture, body))
            elif expected_status == 400:
                if not isinstance(body, dict) or not body.get("request_id") or not isinstance(body.get("error"), dict):
                    errors.append("missing structured Lambda error or request_id")
        except httpx.HTTPError as error:
            # Exception strings may contain request details; keep only the type.
            errors.append(type(error).__name__)
        result.update(errors=errors, passed=not errors, duration_ms=round((time.monotonic() - started) * 1000))
        results.append(result)
        print(f"{'FAIL' if errors else 'PASS'} {name}", flush=True)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=os.environ.get("RAG_QUERY_ENDPOINT"), help="Full HTTPS /query URL")
    parser.add_argument("--fixtures", type=Path, default=ROOT / "tests/fixtures/aws_poc/questions.json")
    parser.add_argument("--case-id", required=True, help="Run exactly one question with this case_id")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE"), help="AWS credential profile")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"), help="API AWS region")
    args = parser.parse_args(argv)
    fixtures = json.loads(args.fixtures.read_text())
    selected = [case for case in fixtures if case["case_id"] == args.case_id]
    if len(selected) != 1:
        parser.error(f"--case-id must match exactly one fixture; found {len(selected)} matches for {args.case_id!r}")
    url = urlsplit(args.endpoint or "")
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        parser.error("provide an HTTPS endpoint without credentials, query string or fragment")
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    if not session.region_name:
        parser.error("set --region, AWS_DEFAULT_REGION, or the profile region")
    if session.get_credentials() is None:
        parser.error("configure AWS credentials for the approved operator")
    signer = RequestSigner(session)
    with httpx.Client(timeout=40, follow_redirects=False) as client:
        results = run(client, args.endpoint, scenarios(selected), interval=0.6, signer=signer)
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "automated_checks_passed": all(item["passed"] for item in results),
        "semantic_review_required": True,
        "different_principal_check": "not run; requires separate AWS credentials",
        "limitations": ["Human review of answer meaning and citation support required", "No authentication-negative, input-validation, replacement, injected backend failure or CloudWatch verification"],
        "results": results,
    }
    path = args.report or ROOT / "online_rag_reports" / f"{uuid.uuid4().hex}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Redact credentials even if a misconfigured remote service echoes them.
    serialized = json.dumps(report, indent=2)
    for token in sorted(signer.secrets, key=len, reverse=True):
        if token:
            serialized = serialized.replace(token, "[REDACTED]")
    path.write_text(serialized + "\n")
    print(f"Report: {path}. Semantic review is still required.")
    return 0 if report["automated_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
