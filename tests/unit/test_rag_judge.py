from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from scripts.evaluate_rag import main

from apps.query_lambda.query import _evidence
from evaluation.judge import BudgetLedger, CUSTOM_METRIC, METRICS, estimate, export_dataset, digest, job_request

ROOT = Path(__file__).resolve().parents[2]


class JudgeTests(TestCase):
    def config(self):
        return {'pricing_date': date.today().isoformat(), 'region': 'test_region', 'evaluator_model_id': 'test_judge', 'custom_evaluator_model_id': 'test_custom_judge',
                'pricing_source': 'operator_reviewed_test_rates', 'budget_usd': 10, 'safety_multiplier': 2,
                'supporting_cost_bound_usd': '.1', **{f'{kind}_{direction}_{suffix}': value
                for kind in ('capture', 'judge', 'custom_judge') for direction in ('input', 'output')
                for suffix, value in (('token_bound', 1000), ('usd_per_million', 1))}}

    def test_estimate_counts_three_metrics_and_rejects_bad_inputs(self):
        self.assertEqual(estimate(self.config())['estimated_usd'], '0.296000')
        result = estimate(self.config())
        self.assertEqual(result['judge_metric_assessments'], 18)
        self.assertEqual(result['custom_metric_assessments'], 6)
        self.assertEqual(estimate({**self.config(), 'custom_judge_input_usd_per_million': 2})['estimated_usd'], '0.308000')
        for changes in ({'budget_usd': 0}, {'budget_usd': '.01'}, {'pricing_date': '2000-01-01'},
                        {'safety_multiplier': '.5'}, {'judge_input_token_bound': 1.5},
                        {'capture_input_usd_per_million': 'NaN'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                estimate({**self.config(), **changes})

    def test_concurrent_reservations_cannot_overspend_or_change_budget(self):
        with TemporaryDirectory() as directory:
            ledger = BudgetLedger(Path(directory) / 'ledger.sqlite3')
            def reserve(index):
                try:
                    ledger.reserve(str(index), 6, 10)
                    return True
                except ValueError:
                    return False
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(sum(pool.map(reserve, range(2))), 1)
            with self.assertRaises(ValueError):
                ledger.reserve('next', 1, 20)
            with self.assertRaises(ValueError):
                ledger.reserve('next', 6, 10)

    def samples(self):
        fixtures = json.loads((ROOT / 'tests/fixtures/aws_poc/questions.json').read_text())
        ids = json.loads((ROOT / 'tests/fixtures/aws_poc/judge_baseline.json').read_text())['case_ids']
        cases = [next(case for case in fixtures if case['case_id'] == key) for key in ids]
        identity = {'fixture_sha256': 'fixtures', 'corpus_sha256': 'corpus', 'deployment_id': 'deployment',
                    'model_id': 'model', 'knowledge_base_id': 'kb', 'rag_source_id': 'insurance_api', 'max_age_seconds': 3600}
        results = []
        for index, case in enumerate(cases):
            config = {'model_id': 'model', 'knowledge_base_id': 'kb', 'result_count': 10,
                      'max_passage_chars': 6000, 'max_context_chars': 24000}
            retrieved = [{'content': {'text': passage['text']}, 'metadata': {
                'document_id': passage['document_id'], 'owner_id': case['owner_id'], 'lob': case['lob']},
                'location': {'s3Location': {'uri': 's3://test/policy.pdf'}}} for passage in case['supporting_passages']]
            evidence, references = _evidence(retrieved, config, case['owner_id'], case['lob'])
            response = {'request_id': str(index), 'answer': case['expected_answer'], 'citations': list(references.values())}
            artifact = {'schema_version': 1, 'request_id': str(index), 'created_at': datetime.now(timezone.utc).isoformat(),
                        'request': {key: case[key] for key in ('question', 'owner_id', 'lob')},
                        'response': response, 'configuration': config, 'deployment_id': 'deployment',
                        'retrieval_filter': {'andAll': [{'equals': {'key': key, 'value': case[key]}} for key in ('owner_id', 'lob')]},
                        'retrieval_results': retrieved, 'generation_evidence': evidence, 'evidence_references': references,
                        'context_truncated': False, 'model_invoked': bool(references), 'usage': {'input_tokens': 10, 'output_tokens': 10}}
            results.append({'case_id': case['case_id'], 'passed': True, 'errors': [], 'http_status': 200,
                            'response': {**response, 'evaluation_capture': {'sha256': digest(artifact)}}, 'evaluation_evidence': artifact})
        return cases, {'fixture_sha256': 'fixtures', 'corpus_sha256': 'corpus', 'results': results}, identity

    def test_export_preserves_real_evidence_empty_retrieval_and_hash_identity(self):
        cases, report, identity = self.samples()
        report['results'].reverse()
        rows, manifest = export_dataset(cases, report, identity)
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[-1]['conversationTurns'][0]['output']['retrievedPassages']['retrievalResults'], [])
        self.assertTrue(manifest['empty_retrieval_service_verification_required'])
        self.assertEqual([item['case_id'] for item in manifest['cases']], [case['case_id'] for case in cases])
        self.assertTrue(all(item['row_sha256'] and item['reviewer'] is None for item in manifest['cases']))

    def test_export_rejects_tampering_staleness_missing_usage_and_failed_capture(self):
        cases, report, identity = self.samples()
        changes = [lambda r: r.update(fixture_sha256='old'),
                   lambda r: r['results'][0].update(passed=False),
                   lambda r: r['results'][0]['evaluation_evidence'].update(generation_evidence='fabricated'),
                   lambda r: r['results'][0]['evaluation_evidence'].update(created_at='2000-01-01T00:00:00+00:00'),
                   lambda r: r['results'][0]['evaluation_evidence']['usage'].update(input_tokens=None),
                   lambda r: r['results'][0]['evaluation_evidence']['retrieval_results'][0]['metadata'].update(owner_id='other'),
                   lambda r: r['results'][0]['evaluation_evidence'].update(context_truncated=True),
                   lambda r: r['results'].append(r['results'][0])]
        for change in changes:
            modified = deepcopy(report)
            change(modified)
            for item in modified['results']:
                item['response']['evaluation_capture']['sha256'] = digest(item['evaluation_evidence'])
            with self.subTest(change=change), self.assertRaises(ValueError):
                export_dataset(cases, modified, identity)

    def test_request_is_sdk_valid_and_uses_only_precomputed_source(self):
        config = {**self.config(), 'evaluation_role_arn': 'arn:aws:iam::123456789012:role/evaluation',
                  'dataset_s3_uri': 's3://evaluation/datasets/baseline.jsonl',
                  'output_s3_uri': 's3://evaluation/results/'}
        request = job_request(config, 'a' * 32, {'knowledge_base_id': 'kb', 'rag_source_id': 'insurance_api'})
        source = request['inferenceConfig']['ragConfigs'][0]
        self.assertEqual(source['precomputedRagSourceConfig']['retrieveAndGenerateSourceConfig']['ragSourceIdentifier'], 'insurance_api')
        self.assertEqual(request['evaluationConfig']['automated']['datasetMetricConfigs'][0]['metricNames'],
                         METRICS)
        automated = request['evaluationConfig']['automated']
        custom = automated['customMetricConfig']
        definition = custom['customMetrics'][0]['customMetricDefinition']
        self.assertEqual(definition['name'], CUSTOM_METRIC)
        self.assertEqual([item['value']['floatValue'] for item in definition['ratingScale']], [0, 1])
        for variable in ('prompt', 'ground_truth', 'context', 'prediction'):
            self.assertIn('{{' + variable + '}}', definition['instructions'])
        self.assertEqual(custom['evaluatorModelConfig']['bedrockEvaluatorModels'][0]['modelIdentifier'], 'test_custom_judge')
        self.assertEqual(automated['evaluatorModelConfig']['bedrockEvaluatorModels'][0]['modelIdentifier'], 'test_judge')
        self.assertNotEqual(request['clientRequestToken'], job_request({**config, 'custom_evaluator_model_id': 'another_judge'}, 'a' * 32, {'rag_source_id': 'insurance_api'})['clientRequestToken'])
        self.assertRegex(request['jobName'], r'^[a-z0-9]{1,63}$')
        self.assertEqual(request, job_request(config, 'a' * 32, {'knowledge_base_id': 'kb', 'rag_source_id': 'insurance_api'}))
        with self.assertRaises(ValueError):
            job_request({**config, 'dataset_s3_uri': 'https://example.test'}, 'a' * 32, {'knowledge_base_id': 'kb', 'rag_source_id': 'insurance_api'})

    def test_cli_prepare_reserve_export_without_aws(self):
        cases, report, identity = self.samples()
        config = {**self.config(), **identity, 'evaluation_role_arn': 'arn:aws:iam::123456789012:role/evaluation',
                  'dataset_s3_uri': 's3://evaluation/datasets/baseline.jsonl', 'output_s3_uri': 's3://evaluation/results/'}
        environment = {'JUDGE_' + key.upper(): str(value) for key, value in config.items()}
        with TemporaryDirectory() as directory, patch.dict('os.environ', environment), patch('boto3.Session') as aws:
            root = Path(directory)
            prepared_path = root / 'prepared.json'
            self.assertEqual(main(['prepare', '--output', str(prepared_path)]), 0)
            prepared = json.loads(prepared_path.read_text())
            self.assertFalse(prepared['aws_verified'])
            self.assertEqual(main(['reserve', '--prepared', str(prepared_path), '--ledger', str(root / 'ledger.sqlite3')]), 0)
            report['fixture_sha256'] = prepared['identity']['fixture_sha256']
            report['corpus_sha256'] = prepared['identity']['corpus_sha256']
            captures = root / 'captures.json'
            captures.write_text(json.dumps(report))
            self.assertEqual(main(['export', '--prepared', str(prepared_path), '--captures', str(captures), '--output', str(root / 'export')]), 0)
            self.assertEqual(len((root / 'export/dataset.jsonl').read_text().splitlines()), 6)
            with self.assertRaises(FileExistsError):
                main(['prepare', '--output', str(prepared_path)])
            aws.assert_not_called()
