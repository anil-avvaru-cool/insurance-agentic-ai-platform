import importlib.util
import json
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location("query_lambda", Path(__file__).parents[2] / "src" / "apps" / "query_lambda" / "query.py")
query = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(query)


ENV = {
    "BEDROCK_KNOWLEDGE_BASE_ID": "kb-1",
    "BEDROCK_RAG_ANSWER_MODEL_ID": "amazon.nova-lite-v1:0",
    "QUERY_OPERATOR_ARN": "arn:aws:iam::123456789012:user/operator",
    "KNOWLEDGE_RESULT_COUNT": "5",
    "MODEL_MAX_TOKENS": "512",
    "MODEL_TEMPERATURE": "0",
    "QUERY_DEADLINE_SECONDS": "26",
}


class Context:
    aws_request_id = "lambda-id"

    def get_remaining_time_in_millis(self):
        return 28000


def event(body=None, arn="arn:aws:iam::123456789012:user/operator"):
    return {
        "requestContext": {"requestId": "api-id", "identity": {"userArn": arn}},
        "body": json.dumps(body if body is not None else {"question": "What is my deductible?", "lob": "auto", "owner_id": "customer_one"}),
    }


class QueryLambdaTests(TestCase):
    def invoke(self, request, agent=None, model=None):
        with patch.dict(os.environ, ENV, clear=True):
            return query.handler(request, Context(), agent_client=agent or Mock(), model_client=model or Mock())

    def test_rejects_other_identity_before_aws_calls(self):
        agent, model = Mock(), Mock()
        response = self.invoke(event(arn="arn:aws:iam::123456789012:user/other"), agent, model)
        self.assertEqual(response["statusCode"], 403)
        agent.retrieve.assert_not_called()
        model.converse.assert_not_called()

    def test_rejects_missing_identity_and_forged_header(self):
        request = event(arn=None)
        request["headers"] = {"userArn": ENV["QUERY_OPERATOR_ARN"]}
        response = self.invoke(request)
        self.assertEqual(response["statusCode"], 403)

    def test_role_sessions_match_only_approved_role(self):
        config = {"operator_arn": "arn:aws:iam::123456789012:role/team/operator"}
        query._authorize(event(arn="arn:aws:sts::123456789012:assumed-role/operator/session"), config)
        for arn in ("arn:aws:sts::999999999999:assumed-role/operator/session",
                    "arn:aws:sts::123456789012:assumed-role/other/session"):
            with self.assertRaises(query.RequestError):
                query._authorize(event(arn=arn), config)

    def test_invalid_owner_skips_bedrock(self):
        for owner in (None, "unknown", [], "customer_one "):
            agent, model = Mock(), Mock()
            response = self.invoke(event({"question": "Deductible?", "lob": "auto", "owner_id": owner}), agent, model)
            self.assertEqual(response["statusCode"], 400)
            agent.retrieve.assert_not_called()
            model.converse.assert_not_called()

    def test_customer_two_filter_and_base64_body(self):
        import base64
        agent, model = Mock(), Mock()
        agent.retrieve.return_value = {"retrievalResults": []}
        request = event({"question": "Deductible?", "lob": "property", "owner_id": "customer_two"})
        request["body"] = base64.b64encode(request["body"].encode()).decode()
        request["isBase64Encoded"] = True
        self.assertEqual(self.invoke(request, agent, model)["statusCode"], 200)
        filters = agent.retrieve.call_args.kwargs["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"]["andAll"]
        self.assertEqual(filters, [{"equals": {"key": "owner_id", "value": "customer_two"}}, {"equals": {"key": "lob", "value": "property"}}])

    def test_retrieval_always_filters_owner_and_lob(self):
        agent, model = Mock(), Mock()
        agent.retrieve.return_value = {"retrievalResults": [{
            "content": {"text": "The collision deductible is $500."},
            "metadata": {"document_id": "auto_user_1_v1", "owner_id": "customer_one", "lob": "auto"},
            "location": {"s3Location": {"uri": "s3://private/approved/aws_poc/auto_user_1_v1.pdf"}},
        }]}
        model.converse.return_value = {
            "output": {"message": {"content": [{"text": json.dumps({
                "answer": "$500 per covered loss.", "evidence_ids": ["E1"], "insufficient_information": False,
            })}]}}, "usage": {"inputTokens": 12, "outputTokens": 8},
        }
        response = self.invoke(event(), agent, model)
        self.assertEqual(response["statusCode"], 200)
        vector = agent.retrieve.call_args.kwargs["retrievalConfiguration"]["vectorSearchConfiguration"]
        self.assertEqual(vector["filter"]["andAll"], [
            {"equals": {"key": "owner_id", "value": "customer_one"}},
            {"equals": {"key": "lob", "value": "auto"}},
        ])
        body = json.loads(response["body"])
        self.assertEqual(body["answer"], "$500 per covered loss.")
        self.assertEqual(body["citations"][0]["document_id"], "auto_user_1_v1")
        self.assertNotIn("owner_id", body["citations"][0])
        self.assertEqual(body["request_id"], "api-id")

    def test_unknown_model_citation_becomes_insufficient(self):
        agent, model = Mock(), Mock()
        agent.retrieve.return_value = {"retrievalResults": [{"content": {"text": "Some evidence."}, "metadata": {}}]}
        model.converse.return_value = {"output": {"message": {"content": [{"text": json.dumps({
            "answer": "Invented", "evidence_ids": ["E99"], "insufficient_information": False,
        })}]}}}
        body = json.loads(self.invoke(event(), agent, model)["body"])
        self.assertEqual(body["answer"], query.INSUFFICIENT_ANSWER)
        self.assertEqual(body["citations"], [])

    def test_no_results_skips_model(self):
        agent, model = Mock(), Mock()
        agent.retrieve.return_value = {"retrievalResults": []}
        body = json.loads(self.invoke(event(), agent, model)["body"])
        self.assertEqual(body["answer"], query.INSUFFICIENT_ANSWER)
        model.converse.assert_not_called()

    def test_invalid_input_is_clear_and_skips_retrieval(self):
        agent = Mock()
        response = self.invoke(event({"question": "", "lob": "life"}), agent)
        self.assertEqual(response["statusCode"], 400)
        self.assertEqual(json.loads(response["body"])["error"]["code"], "invalid_question")
        agent.retrieve.assert_not_called()
