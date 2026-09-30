"""Opt-in live Phase 1 API checks; see docs/aws/ONLINE_RAG_EVALUATION.md."""
import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import sys
from urllib.parse import urlsplit
import uuid

import httpx
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from evaluation.online import INSUFFICIENT, check_answer


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



def scenarios(fixtures, capture_evidence=False):
    for case in fixtures:
        payload = {"question": case["question"], "lob": case["lob"], "owner_id": case["owner_id"]}
        if capture_evidence:
            payload["capture_evidence"] = True
        yield case["case_id"], "signed", payload, 200, case


def read_capture(storage, body, payload, bucket, prefix):
    """Fetch only the configured destination and bind evidence to this API result."""
    descriptor = body.get("evaluation_capture", {})
    request_id = body["request_id"]
    key = prefix + hashlib.sha256(request_id.encode()).hexdigest() + ".json"
    if descriptor.get("bucket") != bucket or descriptor.get("key") != key:
        raise ValueError("capture destination mismatch")
    stream = storage.get_object(Bucket=bucket, Key=key)["Body"]
    try:
        encoded = stream.read(2_000_001)
    finally:
        stream.close()
    if len(encoded) > 2_000_000 or hashlib.sha256(encoded).hexdigest() != descriptor.get("sha256"):
        raise ValueError("capture size or hash mismatch")
    artifact = json.loads(encoded)
    expected_response = {key: body[key] for key in ("request_id", "answer", "citations")}
    expected_request = {key: payload[key] for key in ("question", "owner_id", "lob")}
    if artifact.get("schema_version") != 1 or artifact.get("response") != expected_response or artifact.get("request") != expected_request or artifact.get("request_id") != request_id:
        raise ValueError("capture does not match request and response")
    for result in artifact["retrieval_results"]:
        metadata = result.get("metadata", {})
        if metadata.get("owner_id") != payload["owner_id"] or metadata.get("lob") != payload["lob"]:
            raise ValueError("capture isolation mismatch")
    return artifact


def run(client, endpoint, cases, interval, signer, capture_storage=None, capture_bucket=None, capture_prefix=None):
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
            if payload.get("capture_evidence") and response.status_code == 200:
                try:
                    result["evaluation_evidence"] = read_capture(capture_storage, body, payload, capture_bucket, capture_prefix)
                    allowed = fixture["allowed_document_ids"]
                    if any(item.get("metadata", {}).get("document_id") not in allowed
                           for item in result["evaluation_evidence"]["retrieval_results"]):
                        errors.append("captured retrieval outside allowed documents")
                except Exception as error:
                    errors.append("capture verification failed: " + type(error).__name__)
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
    parser.add_argument("--capture-evidence", action="store_true", help="Save exact pipeline evidence; requires capture-enabled deployment and S3 read permission")
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE"), help="AWS credential profile")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"), help="API AWS region")
    args = parser.parse_args(argv)
    fixture_bytes = args.fixtures.read_bytes()
    fixtures = json.loads(fixture_bytes)
    selected = [case for case in fixtures if case["case_id"] == args.case_id]
    if len(selected) != 1:
        parser.error(f"--case-id must match exactly one fixture; found {len(selected)} matches for {args.case_id!r}")
    corpus_hash = None
    capture_bucket = capture_prefix = None
    if args.capture_evidence:
        from evaluation.fixtures import validate_baseline
        from evaluation.judge import digest
        validation = validate_baseline(ROOT / 'data/sample_insurance_policies', args.fixtures,
                                       ROOT / 'tests/fixtures/aws_poc/judge_baseline.json')
        corpus_hash = digest(validation['sha256'])
        capture_bucket = os.environ["QUERY_CAPTURE_BUCKET"]
        capture_prefix = os.environ["QUERY_CAPTURE_PREFIX"]
        if not capture_bucket or not capture_prefix or not capture_prefix.endswith("/"):
            parser.error("set QUERY_CAPTURE_BUCKET and a nonempty QUERY_CAPTURE_PREFIX ending in /")
    url = urlsplit(args.endpoint or "")
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        parser.error("provide an HTTPS endpoint without credentials, query string or fragment")
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    if not session.region_name:
        parser.error("set --region, AWS_DEFAULT_REGION, or the profile region")
    if session.get_credentials() is None:
        parser.error("configure AWS credentials for the approved operator")
    signer = RequestSigner(session)
    storage = session.client("s3") if args.capture_evidence else None
    with httpx.Client(timeout=40, follow_redirects=False) as client:
        results = run(client, args.endpoint, scenarios(selected, args.capture_evidence), interval=0.6, signer=signer,
                      capture_storage=storage, capture_bucket=capture_bucket, capture_prefix=capture_prefix)
    report = {
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "corpus_sha256": corpus_hash,
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
