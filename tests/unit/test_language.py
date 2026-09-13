import json
import unittest

import httpx

from adapters.models.language import Interpretation
from adapters.models.openai import OpenAIAdapter
from insurance_domain.catalogs import Catalogs
from insurance_domain.intake import DomainError


class LanguageTests(unittest.TestCase):
    def adapter(self, body, status=200):
        def respond(request):
            payload = json.loads(request.content)
            self.assertFalse(payload['store'])
            self.assertTrue(payload['text']['format']['strict'])
            self.assertNotIn('tools', payload)
            return httpx.Response(status, json=body)
        client = httpx.Client(transport=httpx.MockTransport(respond))
        self.addCleanup(client.close)
        return OpenAIAdapter('test-model', 'test-key', 1, 2000, client)

    def test_structured_extraction_transport(self):
        output = dict(intent='intake', object_ref=None, source_ref=None, facts=[
            dict(name='description', value='Parked vehicle struck', quote='Parked vehicle struck')])
        adapter = self.adapter(dict(status='completed', output=[dict(type='message', content=[
            dict(type='output_text', text=json.dumps(output))])]))
        result, metadata = adapter.interpret('Parked vehicle struck', [])
        self.assertEqual(result.facts[0].value, 'Parked vehicle struck')
        self.assertEqual(metadata['provider'], 'openai')

    def test_provider_failures_are_safe(self):
        for body, status in [({}, 429), ({'status': 'incomplete'}, 200),
                             ({'status': 'completed', 'output': []}, 200),
                             ({'status': 'completed', 'output': [{'type': 'message', 'content': [
                                 {'type': 'refusal', 'refusal': 'private text'}]}]}, 200)]:
            with self.subTest(body=body), self.assertRaisesRegex(DomainError, '^language_unavailable$'):
                self.adapter(body, status).interpret('hello', [])

    def test_grounding_rejects_inventions_and_duplicates(self):
        fact = dict(name='description', value='invented', quote='car struck')
        for facts in ([fact], [dict(fact, value='car struck')] * 2):
            with self.assertRaises(DomainError):
                Interpretation(intent='intake', facts=facts, object_ref=None,
                               source_ref=None).grounded('car struck')

    def test_sources_withdrawal_access_and_expiration(self):
        catalogs = Catalogs('policies/local_catalogs_v1.json')
        self.assertEqual(catalogs.answer('report_loss')['source_version'], '1')
        source = catalogs.data['sources'][0]
        for key, value in [('approved', False), ('audience', 'employee'),
                           ('line', 'property'), ('effective_until', '2000-01-01')]:
            original = source[key]
            source[key] = value
            with self.subTest(key=key), self.assertRaises(DomainError):
                catalogs.answer('report_loss')
            source[key] = original
