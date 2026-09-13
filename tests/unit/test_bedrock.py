import io
import json
import os
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from botocore.exceptions import ClientError
from adapters.models.bedrock import converse, embed, retrieve
from apps.agentcore.main import app
from scripts.bedrock_smoke import ingest


ENV = {
    "AWS_REGION": "us-east-1", "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
    "BEDROCK_EMBEDDING_MODEL_ID": "amazon.titan-embed-text-v2:0",
    "BEDROCK_EMBEDDING_DIMENSIONS": "1024", "MODEL_MAX_TOKENS": "512",
    "MODEL_TEMPERATURE": "0", "KNOWLEDGE_RESULT_COUNT": "3",
    "BEDROCK_KNOWLEDGE_BASE_ID": "TESTKB1234", "BEDROCK_DATA_SOURCE_ID": "TESTDS1234",
    "KNOWLEDGE_INGESTION_TIMEOUT_SECONDS": "60",
}


@patch.dict(os.environ, ENV)
class BedrockTests(unittest.TestCase):
    def test_converse_preserves_usage_and_ignores_nontext_blocks(self):
        runtime = Mock()
        runtime.converse.return_value = {"output": {"message": {"content": [
            {"text": "Synthetic response"}, {"toolUse": {"name": "ignored"}}]}},
            "usage": {"inputTokens": 5}, "stopReason": "end_turn"}
        result = converse("Synthetic question", runtime)
        self.assertEqual(result["text"], "Synthetic response")
        self.assertEqual(result["usage"]["inputTokens"], 5)
        self.assertNotIn("toolConfig", runtime.converse.call_args.kwargs)

    def test_embedding_mismatch_fails(self):
        runtime = Mock()
        runtime.invoke_model.return_value = {"body": io.BytesIO(json.dumps({
            "embedding": [1.0], "inputTextTokenCount": 1}).encode())}
        with self.assertRaisesRegex(ValueError, "dimension"):
            embed("synthetic", runtime)

    def test_retrieval_filters_and_preserves_citations(self):
        runtime = Mock()
        results = [{"content": {"text": "Synthetic"}, "location": {"s3Location": {"uri": "s3://test/approved/demo.txt"}}}]
        runtime.retrieve.return_value = {"retrievalResults": results}
        self.assertEqual(retrieve("test", runtime)["results"], results)
        filters = runtime.retrieve.call_args.kwargs["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"]["andAll"]
        self.assertIn({"equals": {"key": "approved", "value": True}}, filters)
        self.assertIn({"equals": {"key": "audience", "value": "customer"}}, filters)

    def test_ingestion_checks_document_failures(self):
        runtime = Mock()
        runtime.start_ingestion_job.return_value = {"ingestionJob": {"ingestionJobId": "job"}}
        runtime.get_ingestion_job.return_value = {"ingestionJob": {
            "ingestionJobId": "job", "status": "COMPLETE", "statistics": {"numberOfDocumentsFailed": 1}}}
        with self.assertRaisesRegex(RuntimeError, "document failures"):
            ingest(runtime)

    def test_ingestion_timeout_exposes_job_id(self):
        runtime = Mock()
        runtime.start_ingestion_job.return_value = {"ingestionJob": {"ingestionJobId": "job"}}
        runtime.get_ingestion_job.return_value = {"ingestionJob": {"ingestionJobId": "job", "status": "IN_PROGRESS"}}
        with patch("scripts.bedrock_smoke.time.monotonic", side_effect=[0, 61]):
            with self.assertRaisesRegex(TimeoutError, "job"):
                ingest(runtime)

    def test_runtime_contract_and_rejects_actions(self):
        with TestClient(app) as http:
            self.assertEqual(http.get("/ping").status_code, 200)
            self.assertEqual(http.post("/invocations", json={"operation": "submit_claim", "text": "test"}).status_code, 422)
            self.assertEqual(http.post("/invocations", json={"operation": "converse", "text": ""}).status_code, 422)
            with patch("apps.agentcore.main.converse", return_value={"text": "test"}):
                self.assertEqual(http.post("/invocations", json={"operation": "converse", "text": "test"}).json(), {"text": "test"})
            with patch("apps.agentcore.main.converse", side_effect=ClientError({"Error": {"Code": "AccessDenied", "Message": "private_detail"}}, "Converse")):
                response = http.post("/invocations", json={"operation": "converse", "text": "test"})
                self.assertEqual(response.status_code, 502)
                self.assertNotIn("private_detail", response.text)

    def test_missing_config_fails_at_startup(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(KeyError):
                with TestClient(app):
                    pass
