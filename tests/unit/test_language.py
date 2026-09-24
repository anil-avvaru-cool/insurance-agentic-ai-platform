import json
import unittest

import os
from unittest.mock import Mock, patch
from botocore.exceptions import ClientError, ReadTimeoutError
from botocore.stub import Stubber
import boto3

from adapters.models.language import Interpretation
from adapters.models.bedrock import BedrockAdapter
from apps.config import configured_language
from insurance_domain.catalogs import Catalogs
from insurance_domain.intake import DomainError


class LanguageTests(unittest.TestCase):
    def response(self, output):
        return {"stopReason": "tool_use", "output": {"message": {
            "role": "assistant", "content": [{"toolUse": {
                "name": "interpretation", "toolUseId": "test_call", "input": output}}]}},
            "usage": {"inputTokens": 12, "outputTokens": 8, "totalTokens": 20},
            "metrics": {"latencyMs": 10}}

    def adapter(self, body):
        runtime = Mock()
        runtime.converse.return_value = body
        return BedrockAdapter('test_model', 'us-east-1', 1, 2000, runtime)

    def test_structured_extraction_transport(self):
        output = dict(intent='intake', object_ref=None, source_ref=None, facts=[
            dict(name='description', value='Parked vehicle struck', quote='Parked vehicle struck')])
        adapter = self.adapter(self.response(output))
        result, metadata = adapter.interpret('Parked vehicle struck', [])
        self.assertEqual(result.facts[0].value, 'Parked vehicle struck')
        self.assertEqual(metadata['provider'], 'bedrock')
        self.assertEqual(metadata['usage']['totalTokens'], 20)
        request = adapter.runtime.converse.call_args.kwargs
        self.assertEqual(request['modelId'], 'test_model')
        self.assertEqual(request['toolConfig']['toolChoice'], {'tool': {'name': 'interpretation'}})
        schema = request['toolConfig']['tools'][0]['toolSpec']['inputSchema']['json']
        self.assertEqual(set(schema), {'type', 'properties', 'required'})
        self.assertNotIn('$ref', json.dumps(schema))
        # Validate the actual request and response against the installed AWS SDK.
        runtime = boto3.client('bedrock-runtime', region_name='us-east-1',
                               aws_access_key_id='testing', aws_secret_access_key='testing')
        self.addCleanup(runtime.close)
        with Stubber(runtime) as stub:
            stub.add_response('converse', self.response(output), request)
            BedrockAdapter('test_model', 'us-east-1', 1, 2000, runtime).interpret('Parked vehicle struck', [])
            stub.assert_no_pending_responses()

    def test_provider_failures_are_safe(self):
        valid = dict(intent='employee_help', facts=[], object_ref=None, source_ref=None)
        responses = [{}, {'stopReason': 'max_tokens'}, {'stopReason': 'guardrail_intervened'},
                     self.response({'intent': 'invalid'}), self.response(dict(valid, unexpected='value'))]
        wrong = self.response(valid)
        wrong['output']['message']['content'][0]['toolUse']['name'] = 'submit_claim'
        responses.append(wrong)
        extra = self.response(valid)
        extra['output']['message']['content'].append({'text': 'untrusted'})
        responses.append(extra)
        for body in responses:
            with self.subTest(body=body), self.assertRaisesRegex(DomainError, '^language_unavailable$'):
                self.adapter(body).interpret('hello', [])
        for error in (ClientError({'Error': {'Code': 'ThrottlingException', 'Message': 'private'}}, 'Converse'),
                      ReadTimeoutError(endpoint_url='https://test.invalid')):
            adapter = self.adapter({})
            adapter.runtime.converse.side_effect = error
            with self.assertRaisesRegex(DomainError, '^language_unavailable$'):
                adapter.interpret('hello', [])

    def test_cloud_configuration(self):
        with patch.dict(os.environ, {'LLM_PROVIDER': 'disabled'}, clear=True):
            self.assertEqual(type(configured_language()).__name__, 'DisabledLanguage')
        for provider in ('openai', 'anthropic', 'unknown'):
            with patch.dict(os.environ, {'LLM_PROVIDER': provider}, clear=True):
                with self.assertRaisesRegex(ValueError, 'direct providers are prohibited'):
                    configured_language()
        with patch.dict(os.environ, {'LLM_PROVIDER': 'bedrock'}, clear=True):
            with self.assertRaises(KeyError):
                configured_language()
        env = dict(LLM_PROVIDER='bedrock', BEDROCK_MODEL_ID='test_model', AWS_REGION='us-east-1',
                   LLM_TIMEOUT_SECONDS='5', LLM_MAX_OUTPUT_TOKENS='2000')
        with patch.dict(os.environ, env, clear=True), patch('adapters.models.bedrock.boto3.client') as client:
            adapter = configured_language()
            self.assertEqual(adapter.model, 'test_model')
            self.assertEqual(client.call_args.args, ('bedrock-runtime',))
            self.assertEqual(client.call_args.kwargs['region_name'], 'us-east-1')
            self.assertEqual(client.call_args.kwargs['config'].read_timeout, 5)

    def test_grounding_rejects_inventions_and_duplicates(self):
        fact = dict(name='description', value='invented', quote='car struck')
        for facts in ([fact], [dict(fact, value='car struck')] * 2):
            with self.assertRaises(DomainError):
                Interpretation(intent='intake', facts=facts, object_ref=None,
                               source_ref=None).grounded('car struck')

    def test_sources_withdrawal_access_and_expiration(self):
        catalogs = Catalogs('config/business_rules/local_catalogs_v1.json')
        self.assertEqual(catalogs.answer('report_loss')['source_version'], '1')
        source = catalogs.data['sources'][0]
        for key, value in [('approved', False), ('audience', 'employee'),
                           ('line', 'property'), ('effective_until', '2000-01-01')]:
            original = source[key]
            source[key] = value
            with self.subTest(key=key), self.assertRaises(DomainError):
                catalogs.answer('report_loss')
            source[key] = original
