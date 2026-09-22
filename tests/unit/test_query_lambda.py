import importlib.util
import json
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location("query_lambda", Path(__file__).parents[2] / "lambda" / "query.py")
query = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(query)


ENV = {
    "BEDROCK_KNOWLEDGE_BASE_ID": "kb-1",
    "BEDROCK_RAG_MODEL_ID": "amazon.nova-lite-v1:0",
    "JWT_ISSUER": "https://issuer.example",
    "OWNER_BY_SUBJECT_JSON": '{"subject-1":"customer_one","subject-2":"customer_two"}',
    "KNOWLEDGE_RESULT_COUNT": "5",
    "MODEL_MAX_TOKENS": "512",
    "MODEL_TEMPERATURE": "0",
    "QUERY_DEADLINE_SECONDS": "26",
}


class Context:
    aws_request_id = "lambda-id"

    def get_remaining_time_in_millis(self):
        return 28000


def event(body=None, subject="subject-1", issuer="https://issuer.example"):
    return {
        "requestContext": {"requestId": "api-id", "authorizer": {"jwt": {"claims": {"iss": issuer, "sub": subject}}}},
        "body": json.dumps(body or {"question": "What is my deductible?", "lob": "auto"}),
    }


class QueryLambdaTests(TestCase):
    def invoke(self, request, agent=None, model=None):
        with patch.dict(os.environ, ENV, clear=True):
            return query.handler(request, Context(), agent_client=agent or Mock(), model_client=model or Mock())

    def test_rejects_unmapped_identity_before_aws_calls(self):
        agent, model = Mock(), Mock()
        response = self.invoke(event(subject="unknown"), agent, model)
        self.assertEqual(response["statusCode"], 403)
        agent.retrieve.assert_not_called()
        model.converse.assert_not_called()

    def test_rejects_wrong_issuer(self):
        response = self.invoke(event(issuer="https://attacker.example"))
        self.assertEqual(response["statusCode"], 401)

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
