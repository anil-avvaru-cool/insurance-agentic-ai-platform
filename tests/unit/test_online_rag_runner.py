import json
from unittest import TestCase
from unittest.mock import Mock
from botocore.credentials import Credentials
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

import httpx

from scripts.test_online_rag import INSUFFICIENT, ROOT, RequestSigner, check_answer, run, scenarios


class OnlineRagRunnerTests(TestCase):
    def setUp(self):
        session = Mock(region_name="us-east-1")
        session.get_credentials.return_value = Credentials("test-key", "test-secret", "session-token")
        self.signer = RequestSigner(session)
        self.case = json.loads((ROOT / "tests/fixtures/aws_poc/questions.json").read_text())[0]
        self.body = {"request_id": "request-1", "answer": "$500 per covered loss.", "citations": [
            {"document_id": "auto_user_1_v1", "lob": "auto", "source": "policy.pdf", "evidence_id": "E1"}
        ]}

    def test_good_answer_and_cross_owner_citation(self):
        self.assertEqual(check_answer(self.case, self.body), [])
        self.body["citations"][0]["document_id"] = "auto_user_2_v1"
        self.assertIn("citation outside allowed documents", check_answer(self.case, self.body))

    def test_wrong_amount_and_malformed_response(self):
        self.body["answer"] = "$1,000 per covered loss."
        self.assertIn("expected monetary amount missing", check_answer(self.case, self.body))
        for body in (None, [], {"citations": [None]}):
            self.assertTrue(check_answer(self.case, body))

    def test_insufficient_must_have_no_citations(self):
        self.case["expected_status"] = "insufficient_information"
        self.body.update(answer=INSUFFICIENT, citations=[])
        self.assertEqual(check_answer(self.case, self.body), [])
        self.body["answer"] = "An unsupported guess"
        self.assertTrue(check_answer(self.case, self.body))

    def test_signed_payload_and_negative_auth_cases(self):
        requests = []
        def respond(request):
            requests.append(request)
            if len(requests) > 1:
                return httpx.Response(403, json={"message": "Forbidden"})
            return httpx.Response(200, json=self.body)
        cases = list(scenarios([self.case]))[:3]
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            results = run(client, "https://example.test/poc/query", cases, 0, self.signer)
        self.assertTrue(all(result["passed"] for result in results))
        self.assertEqual(json.loads(requests[0].content)["owner_id"], self.case["owner_id"])
        signed = requests[0]
        self.assertIn("/us-east-1/execute-api/aws4_request", signed.headers["authorization"])
        self.assertEqual(signed.headers["x-amz-security-token"], "session-token")
        verifier = AWSRequest(method="POST", url=str(signed.url), data=signed.content,
                              headers={k: signed.headers[k] for k in ("content-type", "x-amz-date", "x-amz-security-token")})
        verifier.context["timestamp"] = signed.headers["x-amz-date"]
        auth = SigV4Auth(Credentials("test-key", "test-secret", "session-token"), "execute-api", "us-east-1")
        signature = auth.signature(auth.string_to_sign(verifier, auth.canonical_request(verifier)), verifier)
        self.assertTrue(signed.headers["authorization"].endswith("Signature=" + signature))
        self.assertNotIn("authorization", requests[1].headers)
        self.assertTrue(requests[2].headers["authorization"].endswith("Signature=" + "0" * 64))

    def test_http_failure_and_transport_failure_are_recorded(self):
        cases = [("case", "signed", {}, 200, self.case)]
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503, text="bad"))) as client:
            self.assertFalse(run(client, "https://example.test/query", cases, 0, self.signer)[0]["passed"])

        def timeout(request):
            raise httpx.ReadTimeout("timeout", request=request)

        with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
            result = run(client, "https://example.test/query", cases, 0, self.signer)[0]
        self.assertEqual(result["errors"], ["ReadTimeout"])
