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
    "QUERY_MAX_PASSAGE_CHARS": "6000",
    "QUERY_MAX_CONTEXT_CHARS": "24000",
    "QUERY_CAPTURE_ENABLED": "false",
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
        agent.retrieve.return_value = {"retrievalResults": [{"content": {"text": "Some evidence."},
            "metadata": {"owner_id": "customer_one", "lob": "auto", "document_id": "auto_user_1_v2"}}]}
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


class EvidenceCaptureTests(TestCase):
    def setUp(self):
        self.agent, self.model, self.storage = Mock(), Mock(), Mock()
        self.env = {**ENV, 'QUERY_CAPTURE_ENABLED': 'true', 'QUERY_CAPTURE_BUCKET': 'evaluation_bucket',
                    'QUERY_CAPTURE_PREFIX': 'captures/', 'QUERY_DEPLOYMENT_ID': 'zip_hash'}
        self.results = [{'content': {'text': '  Collision deductible is $750.  '},
                         'metadata': {'owner_id': 'customer_one', 'lob': 'auto', 'document_id': 'auto_user_1_v2'},
                         'location': {'s3Location': {'uri': 's3://knowledge/POC_AUTO_001.pdf'}}}]
        self.agent.retrieve.return_value = {'retrievalResults': self.results}
        self.model.converse.return_value = {'output': {'message': {'content': [{'text': json.dumps({
            'answer': '$750 per covered loss.', 'evidence_ids': ['E1'], 'insufficient_information': False})}]}},
            'usage': {'inputTokens': 90, 'outputTokens': 20}}
        self.body = {'question': 'What is my deductible?', 'owner_id': 'customer_one', 'lob': 'auto', 'capture_evidence': True}

    def invoke(self):
        with patch.dict(os.environ, self.env, clear=True):
            return query.handler(event(self.body), Context(), agent_client=self.agent,
                                 model_client=self.model, capture_client=self.storage)

    def test_exact_context_answer_and_request_bound_capture_without_log_content(self):
        from contextlib import redirect_stdout
        from io import StringIO
        import hashlib
        logs = StringIO()
        with redirect_stdout(logs):
            response = self.invoke()
        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        saved = self.storage.put_object.call_args.kwargs
        artifact = json.loads(saved['Body'])
        prompt = self.model.converse.call_args.kwargs['messages'][0]['content'][0]['text']
        self.assertEqual(prompt.split('EVIDENCE:\n', 1)[1], artifact['generation_evidence'])
        self.assertEqual(artifact['retrieval_results'], self.results)
        self.assertEqual(artifact['response'], {k: body[k] for k in ('request_id', 'answer', 'citations')})
        self.assertEqual(body['evaluation_capture']['sha256'], hashlib.sha256(saved['Body']).hexdigest())
        self.assertEqual(saved['IfNoneMatch'], '*')
        self.assertNotIn('$750', logs.getvalue())
        self.assertNotIn(self.body['question'], logs.getvalue())
        self.assertEqual(artifact['usage'], {'input_tokens': 90, 'output_tokens': 20})

    def test_normal_request_does_not_write_capture(self):
        del self.body['capture_evidence']
        self.assertEqual(self.invoke()['statusCode'], 200)
        self.storage.put_object.assert_not_called()

    def test_disabled_invalid_or_unauthorized_capture_skips_retrieval(self):
        for flag in ('true', 1, None):
            self.body['capture_evidence'] = flag
            self.assertEqual(self.invoke()['statusCode'], 400)
        self.body['capture_evidence'] = True
        self.env['QUERY_CAPTURE_ENABLED'] = 'false'
        self.assertEqual(self.invoke()['statusCode'], 400)
        self.agent.retrieve.assert_not_called()
        self.storage.put_object.assert_not_called()
        with patch.dict(os.environ, self.env, clear=True):
            response = query.handler(event(self.body, arn=None), Context(), agent_client=self.agent,
                                     model_client=self.model, capture_client=self.storage)
        self.assertEqual(response['statusCode'], 403)
        self.agent.retrieve.assert_not_called()

    def test_owner_lob_or_missing_metadata_fails_before_generation_and_capture(self):
        for metadata in ({}, {'owner_id': 'customer_two', 'lob': 'auto', 'document_id': 'other'},
                         {'owner_id': 'customer_one', 'lob': 'property', 'document_id': 'other'}):
            self.results[0]['metadata'] = metadata
            self.assertEqual(self.invoke()['statusCode'], 503)
        self.model.converse.assert_not_called()
        self.storage.put_object.assert_not_called()

    def test_oversize_passage_context_and_result_count_fail_before_generation(self):
        for variable in ('QUERY_MAX_PASSAGE_CHARS', 'QUERY_MAX_CONTEXT_CHARS'):
            self.env[variable] = '1'
            self.assertEqual(self.invoke()['statusCode'], 503)
            self.env[variable] = ENV[variable]
        self.agent.retrieve.return_value = {'retrievalResults': self.results * 6}
        self.assertEqual(self.invoke()['statusCode'], 503)
        self.model.converse.assert_not_called()
        self.storage.put_object.assert_not_called()

    def test_capture_failure_returns_error_without_retry(self):
        self.storage.put_object.side_effect = RuntimeError('private details')
        response = self.invoke()
        self.assertEqual(response['statusCode'], 503)
        self.assertEqual(json.loads(response['body'])['error']['code'], 'capture_failed')
        self.assertNotIn('private details', response['body'])
        self.storage.put_object.assert_called_once()
        self.model.converse.assert_called_once()

    def test_empty_retrieval_preserved_without_model_invocation(self):
        self.agent.retrieve.return_value = {'retrievalResults': []}
        self.assertEqual(self.invoke()['statusCode'], 200)
        artifact = json.loads(self.storage.put_object.call_args.kwargs['Body'])
        self.assertEqual(artifact['retrieval_results'], [])
        self.assertEqual(artifact['generation_evidence'], '')
        self.assertEqual(artifact['response']['answer'], query.INSUFFICIENT_ANSWER)
        self.model.converse.assert_not_called()

    def test_truncated_answer_never_becomes_capture(self):
        self.model.converse.return_value['stopReason'] = 'max_tokens'
        self.assertEqual(self.invoke()['statusCode'], 503)
        self.storage.put_object.assert_not_called()
