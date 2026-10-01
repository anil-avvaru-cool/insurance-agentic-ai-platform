from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

import boto3
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from scripts.evaluate_rag import main
from evaluation.judge import CUSTOM_METRIC, METRICS, export_dataset, job_request
from evaluation.judge_workflow import collect, execute, load_export, submit, summarize, upload
from tests.unit import test_rag_judge


class WorkflowTests(TestCase):
    def baseline(self):
        helper = test_rag_judge.JudgeTests()
        cases, captures, identity = helper.samples()
        rows, manifest = export_dataset(cases, captures, identity)
        manifest['run_id'] = 'a' * 32
        config = {**helper.config(), 'evaluation_role_arn': 'arn:aws:iam::123456789012:role/evaluation',
                  'dataset_s3_uri': 's3://evaluation/datasets/baseline.jsonl', 'output_s3_uri': 's3://evaluation/results/'}
        prepared = {'run_id': manifest['run_id'], 'identity': identity, 'config': config,
                    'job_request': job_request(config, manifest['run_id'], identity)}
        encoded = ''.join(json.dumps(row) + '\n' for row in rows).encode()
        return prepared, encoded, rows, manifest

    def records(self, rows):
        return [{'inputRecord': row, 'automatedEvaluationResult': {'scores': [
            {'metricName': metric, 'result': 1, 'explanation': 'Supported by supplied passages'} for metric in METRICS]}}
            for row in reversed(rows)]

    def test_summary_matches_inputs_not_order_and_separates_groups(self):
        _, _, rows, manifest = self.baseline()
        report = summarize(rows, manifest, self.records(rows))
        self.assertTrue(report['scores_complete'])
        self.assertEqual(report['custom_metric_summary']['abstention']['expected_cases'], 2)
        self.assertEqual(report['custom_metric_summary']['answerable']['expected_cases'], 4)
        self.assertEqual(report['cases'][0]['explanations'][CUSTOM_METRIC], 'Supported by supplied passages')
        records = self.records(rows)
        records[0]['automatedEvaluationResult']['scores'][-1]['result'] = 0
        report = summarize(rows, manifest, records)
        self.assertEqual(report['custom_metric_summary']['abstention']['fail_count'], 1)
        self.assertTrue(report['scores_complete'])  # Complete does not mean all scores pass.
        self.assertIsNone(report['cases'][0]['review_notes'])

    def test_missing_invalid_unknown_and_duplicate_results_do_not_pass(self):
        _, _, rows, manifest = self.baseline()
        records = self.records(rows)
        records[0]['automatedEvaluationResult']['scores'][1]['result'] = None
        records[1]['automatedEvaluationResult']['scores'][-1]['result'] = .5
        records[2]['automatedEvaluationResult']['scores'][0]['result'] = float('nan')
        records.append({'inputRecord': {'conversationTurns': []}})
        report = summarize(rows, manifest, records)
        self.assertFalse(report['scores_complete'])
        self.assertEqual(len(report['missing_scores']), 3)
        self.assertEqual(len(report['unmatched_results']), 1)
        self.assertFalse(report['custom_metric_summary']['abstention']['complete'])
        self.assertFalse(summarize(rows, manifest, [])['scores_complete'])
        with self.assertRaises(ValueError):
            summarize(rows, manifest, self.records(rows) + self.records(rows)[:1])

    def test_submit_saves_before_call_and_retries_identical_sdk_valid_request(self):
        prepared, encoded, _, manifest = self.baseline()
        storage = Mock()
        storage.get_object.side_effect = lambda **kw: {'Body': BytesIO(encoded)}
        bedrock = boto3.Session(region_name='us-east-1', aws_access_key_id='testing', aws_secret_access_key='testing').client('bedrock')
        with TemporaryDirectory() as directory, Stubber(bedrock) as stub:
            state = Path(directory) / 'submission.json'
            stub.add_client_error('create_evaluation_job', service_error_code='InternalServerException', expected_params=prepared['job_request'])
            stub.add_response('create_evaluation_job', {'jobArn': 'arn:aws:bedrock:us-east-1:123456789012:evaluation-job/test'}, prepared['job_request'])
            with self.assertRaises(ClientError):
                submit(bedrock, storage, prepared, encoded, manifest, state)
            self.assertIsNone(json.loads(state.read_text())['job_arn'])
            saved = json.loads(state.read_text())['request']
            result = submit(bedrock, storage, prepared, encoded, manifest, state)
            self.assertEqual(result['request'], saved)
            self.assertTrue(result['job_arn'])
            self.assertEqual(submit(bedrock, storage, prepared, encoded, manifest, state), result)
            stub.assert_no_pending_responses()
            with self.assertRaises(ValueError):
                submit(bedrock, storage, prepared, encoded + b'\n', manifest, state)

    def test_submit_rejects_changed_remote_input_before_paid_call(self):
        prepared, encoded, _, manifest = self.baseline()
        storage, bedrock = Mock(), Mock()
        storage.get_object.return_value = {'Body': BytesIO(b'changed')}
        with TemporaryDirectory() as directory, self.assertRaises(ValueError):
            submit(bedrock, storage, prepared, encoded, manifest, Path(directory) / 'state.json')
        bedrock.create_evaluation_job.assert_not_called()

    def test_conditional_upload_accepts_identical_retry_and_rejects_overwrite(self):
        prepared, encoded, _, _ = self.baseline()
        storage = Mock()
        upload(storage, prepared, encoded)
        self.assertEqual(storage.put_object.call_args.kwargs['IfNoneMatch'], '*')
        self.assertEqual(storage.put_object.call_args.kwargs['ServerSideEncryption'], 'AES256')
        storage.put_object.side_effect = ClientError({'Error': {'Code': 'PreconditionFailed'}}, 'PutObject')
        storage.get_object.return_value = {'Body': BytesIO(encoded)}
        upload(storage, prepared, encoded)
        storage.get_object.return_value = {'Body': BytesIO(b'other run')}
        with self.assertRaises(ValueError):
            upload(storage, prepared, encoded)

    def test_collect_scopes_to_job_and_handles_pagination(self):
        prepared, _, rows, manifest = self.baseline()
        state = {'job_arn': 'arn:aws:bedrock:us-east-1:123456789012:evaluation-job/job_id', 'request': prepared['job_request']}
        prefix = 'results/' + prepared['job_request']['jobName'] + '/job_id/'
        storage = Mock()
        keys = [prefix + 'datasets/result.jsonl', prefix + 'custom_metrics/definition.json']
        storage.get_paginator.return_value.paginate.return_value = [{'Contents': [{'Key': keys[0]}]}, {'Contents': [{'Key': keys[1]}]}]
        storage.get_object.side_effect = lambda **kw: {'Body': BytesIO(('\n'.join(json.dumps(record) for record in self.records(rows)) if kw['Key'].endswith('.jsonl') else '{}').encode())}
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'results'
            collect(storage, state, output)
            storage.get_paginator.return_value.paginate.assert_called_once_with(Bucket='evaluation', Prefix=prefix)
            self.assertTrue((output / 'artifacts/custom_metrics/definition.json').exists())
            self.assertEqual(len(json.loads((output / 'downloads.json').read_text())['artifacts']), 2)

    def test_offline_summary_cli_and_export_tamper_detection(self):
        prepared, encoded, rows, manifest = self.baseline()
        with TemporaryDirectory() as directory, patch('boto3.Session') as aws:
            root = Path(directory)
            (root / 'export').mkdir()
            (root / 'export/dataset.jsonl').write_bytes(encoded)
            (root / 'export/manifest.json').write_text(json.dumps(manifest))
            (root / 'results').mkdir()
            (root / 'results/results.jsonl').write_text('\n'.join(json.dumps(record) for record in self.records(rows)))
            self.assertEqual(main(['summarize', '--export', str(root / 'export'), '--results', str(root / 'results'), '--output', str(root / 'report.json')]), 0)
            aws.assert_not_called()
            load_export(root / 'export', prepared)
            manifest['cases'][0]['row_sha256'] = 'changed'
            (root / 'export/manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                load_export(root / 'export', prepared)

    def test_status_and_failed_collect_never_create_jobs(self):
        from argparse import Namespace
        prepared, _, _, _ = self.baseline()
        with TemporaryDirectory() as directory, patch('boto3.Session') as session:
            root = Path(directory)
            state = root / 'state.json'
            state.write_text(json.dumps({'job_arn': 'arn:aws:bedrock:us-east-1:123456789012:evaluation-job/test', 'request': prepared['job_request'], 'region': 'us-east-1'}))
            bedrock = session.return_value.client.return_value
            bedrock.get_evaluation_job.return_value = {'status': 'Failed', 'failureMessages': ['empty row rejected']}
            self.assertEqual(execute(Namespace(command='status', state=state, output=root / 'status.json'), root), 0)
            self.assertEqual(json.loads((root / 'status.json').read_text())['failureMessages'], ['empty row rejected'])
            with self.assertRaisesRegex(ValueError, 'empty row rejected'):
                execute(Namespace(command='collect', state=state, output=root / 'results'), root)
            bedrock.create_evaluation_job.assert_not_called()

    def test_capture_runs_only_six_selected_cases_and_preserves_partial_failures(self):
        from evaluation.judge_workflow import capture
        prepared, _, _, _ = self.baseline()
        cases, captures, _ = test_rag_judge.JudgeTests().samples()
        prepared['validation'] = {'case_ids': [case['case_id'] for case in cases]}
        root = Path(__file__).resolve().parents[2]
        environment = {'RAG_QUERY_ENDPOINT': 'https://example.test/poc/query',
                       'QUERY_CAPTURE_BUCKET': 'capture_bucket', 'QUERY_CAPTURE_PREFIX': 'captures/'}
        with TemporaryDirectory() as directory, patch.dict('os.environ', environment), patch('boto3.Session'), patch('httpx.Client'), patch('scripts.test_online_rag.RequestSigner') as signer, patch('scripts.test_online_rag.run') as runner:
            signer.return_value.secrets = {'do_not_record_secret'}
            runner.side_effect = [[item] for item in captures['results']]
            output = Path(directory) / 'captures.json'
            self.assertEqual(capture(prepared, root, output), 0)
            self.assertEqual(runner.call_count, 6)
            self.assertEqual(len(json.loads(output.read_text())['results']), 6)
            for call, case in zip(runner.call_args_list, cases):
                scenario = list(call.args[2])
                self.assertEqual(scenario[0][0], case['case_id'])
                self.assertTrue(scenario[0][2]['capture_evidence'])
            with self.assertRaises(FileExistsError):
                capture(prepared, root, output)
            self.assertEqual(runner.call_count, 6)
            runner.reset_mock()
            bad = deepcopy(captures['results'][1])
            bad.update(passed=False, errors=['do_not_record_secret'])
            runner.side_effect = [[captures['results'][0]], [bad]]
            output = Path(directory) / 'failed.json'
            self.assertEqual(capture(prepared, root, output), 1)
            self.assertEqual(runner.call_count, 2)
            self.assertEqual(len(json.loads(output.read_text())['results']), 2)
            self.assertNotIn('do_not_record_secret', output.read_text())

    def test_completed_collect_cli_preserves_artifacts_and_produces_report(self):
        from argparse import Namespace
        import hashlib
        prepared, encoded, rows, manifest = self.baseline()
        with TemporaryDirectory() as directory, patch('boto3.Session') as session:
            root = Path(directory)
            state = {'job_arn': 'arn:aws:bedrock:us-east-1:123456789012:evaluation-job/job_id',
                     'region': 'us-east-1', 'request': prepared['job_request'], 'manifest': manifest,
                     'dataset_sha256': hashlib.sha256(encoded).hexdigest()}
            state_path = root / 'state.json'
            state_path.write_text(json.dumps(state))
            bedrock, storage = Mock(), Mock()
            session.return_value.client.side_effect = lambda service: bedrock if service == 'bedrock' else storage
            bedrock.get_evaluation_job.return_value = {'status': 'Completed', 'jobName': prepared['job_request']['jobName'], 'outputDataConfig': prepared['job_request']['outputDataConfig']}
            prefix = 'results/' + prepared['job_request']['jobName'] + '/job_id/'
            storage.get_paginator.return_value.paginate.return_value = [{'Contents': [{'Key': prefix + 'datasets/results.jsonl'}]}]
            storage.get_object.side_effect = lambda **kw: {'Body': BytesIO(encoded if kw['Key'] == 'datasets/baseline.jsonl' else '\n'.join(json.dumps(record) for record in self.records(rows)).encode())}
            self.assertEqual(execute(Namespace(command='collect', state=state_path, output=root / 'results'), root), 0)
            report = json.loads((root / 'results/report.json').read_text())
            self.assertTrue(report['scores_complete'])
            self.assertEqual(report['job_arn'], state['job_arn'])
            bedrock.create_evaluation_job.assert_not_called()
