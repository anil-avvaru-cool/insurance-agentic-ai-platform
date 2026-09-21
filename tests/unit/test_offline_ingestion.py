import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from ingestion.corpus import ROOT
from ingestion.offline import Settings, run, snapshot

SETTINGS = Settings('us-east-1', 'test_knowledge'.replace('_', ''), 'approved/aws_poc/',
                    'TESTKB1234', 'TESTDS1234', 1)


def aws_clients():
    s3, agent, vectors = Mock(), Mock(), Mock()
    s3.get_bucket_location.return_value = {'LocationConstraint': None}
    s3.put_object.return_value = {'ETag': 'lock_etag'}
    s3.get_paginator.return_value.paginate.return_value = [{'Contents': []}]
    agent.get_knowledge_base.return_value = {'knowledgeBase': {
        'status': 'ACTIVE', 'storageConfiguration': {'type': 'S3_VECTORS',
            's3VectorsConfiguration': {'indexArn': 'index_arn'}},
        'knowledgeBaseConfiguration': {'vectorKnowledgeBaseConfiguration': {
            'embeddingModelArn': 'arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0',
            'embeddingModelConfiguration': {'bedrockEmbeddingModelConfiguration': {
                'dimensions': 1024, 'embeddingDataType': 'FLOAT32'}}}}}}
    vectors.get_index.return_value = {'index': {'dimension': 1024, 'dataType': 'float32',
        'distanceMetric': 'cosine', 'metadataConfiguration': {'nonFilterableMetadataKeys': [
            'AMAZON_BEDROCK_TEXT', 'AMAZON_BEDROCK_METADATA']}}}
    agent.get_data_source.return_value = {'dataSource': {'status': 'AVAILABLE',
        'dataSourceConfiguration': {'type': 'S3', 's3Configuration': {
            'bucketArn': 'arn:aws:s3:::testknowledge', 'inclusionPrefixes': ['approved/aws_poc/']}},
        'vectorIngestionConfiguration': {'chunkingConfiguration': {'chunkingStrategy': 'FIXED_SIZE',
            'fixedSizeChunkingConfiguration': {'maxTokens': 300, 'overlapPercentage': 15}}}}}
    agent.list_ingestion_jobs.return_value = {'ingestionJobSummaries': []}
    agent.start_ingestion_job.return_value = {'ingestionJob': {'ingestionJobId': 'JOB1234567', 'status': 'STARTING'}}
    agent.get_ingestion_job.return_value = {'ingestionJob': {'ingestionJobId': 'JOB1234567',
        'status': 'COMPLETE', 'statistics': {'numberOfDocumentsFailed': 0, 'numberOfDocumentsScanned': 4}}}
    return s3, agent, vectors


class OfflineIngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'corpus'
        shutil.copytree(ROOT, self.root)
        self.report_path = Path(self.temp.name) / 'report.json'
        self.s3, self.agent, self.vectors = aws_clients()

    def run_pipeline(self, **kwargs):
        return run(SETTINGS, self.root, self.report_path, self.s3, self.agent, self.vectors, **kwargs)

    def report(self):
        return json.loads(self.report_path.read_text())

    def test_success_uploads_only_eight_approved_objects_and_reports_job(self):
        def start(**kwargs):
            self.assertEqual(self.s3.put_object.call_count, 9)
            return {'ingestionJob': {'ingestionJobId': 'JOB1234567', 'status': 'STARTING'}}
        self.agent.start_ingestion_job.side_effect = start
        report = self.run_pipeline()
        uploads = [call.kwargs for call in self.s3.put_object.call_args_list]
        self.assertEqual(len(uploads), 9)  # eight sources plus coordination lock
        self.assertEqual(uploads[0]['IfNoneMatch'], '*')
        self.assertTrue(all(item['Key'].startswith(SETTINGS.prefix) for item in uploads[1:]))
        self.assertEqual(set(report['uploaded']), {SETTINGS.prefix + name for name in snapshot(self.root)})
        self.assertEqual(report['job']['statistics']['numberOfDocumentsScanned'], 4)
        self.assertEqual(self.report()['status'], 'COMPLETE')
        self.s3.delete_object.assert_called_once_with(Bucket=SETTINGS.bucket, Key=SETTINGS.lock_key, IfMatch='lock_etag')
        self.assertEqual(self.agent.start_ingestion_job.call_args.kwargs['clientToken'], report['run_id'])

    def test_validation_failure_performs_no_aws_writes(self):
        for failure in ('stale', 'missing', 'invalid_pdf'):
            with self.subTest(failure=failure):
                path = self.root / 'auto_user_1_v1.pdf.metadata.json'
                if failure == 'stale':
                    path.write_text('{}')
                elif failure == 'missing':
                    path.unlink()
                else:
                    (self.root / 'auto_user_1_v1.pdf').write_bytes(b'not a PDF')
                with self.assertRaises(Exception):
                    self.run_pipeline()
                self.s3.put_object.assert_not_called()
                self.agent.start_ingestion_job.assert_not_called()
                self.assertEqual(self.report()['status'], 'FAILED')

    def test_partial_upload_does_not_start_ingestion_and_retry_repairs(self):
        self.s3.put_object.side_effect = [{'ETag': 'lock_etag'}, {}, RuntimeError('upload failed')]
        with self.assertRaisesRegex(RuntimeError, 'upload failed'):
            self.run_pipeline()
        self.agent.start_ingestion_job.assert_not_called()
        self.assertEqual(len(self.report()['uploaded']), 1)
        self.assertFalse(self.report()['lock_retained'])
        self.s3.put_object.side_effect = None
        self.s3.put_object.return_value = {'ETag': 'lock_etag'}
        self.assertEqual(self.run_pipeline()['status'], 'COMPLETE')

    def test_overlapping_run_cannot_upload_or_release_someone_elses_lock(self):
        self.s3.put_object.side_effect = ClientError({'Error': {'Code': 'PreconditionFailed'}}, 'PutObject')
        with self.assertRaises(ClientError):
            self.run_pipeline()
        self.assertEqual(self.s3.put_object.call_count, 1)
        self.agent.start_ingestion_job.assert_not_called()
        self.s3.delete_object.assert_not_called()

    def test_existing_job_on_second_readiness_check_blocks_uploads(self):
        self.agent.list_ingestion_jobs.side_effect = [
            {'ingestionJobSummaries': []},
            {'ingestionJobSummaries': [{'ingestionJobId': 'OTHER', 'status': 'IN_PROGRESS'}]}]
        with self.assertRaisesRegex(RuntimeError, 'OTHER'):
            self.run_pipeline()
        self.assertEqual(self.s3.put_object.call_count, 1)
        self.agent.start_ingestion_job.assert_not_called()

    def test_job_failures_release_lock_and_capture_failure_reasons(self):
        for status, failed in [('FAILED', 0), ('STOPPED', 0), ('COMPLETE', 1)]:
            with self.subTest(status=status, failed=failed):
                self.agent.get_ingestion_job.return_value = {'ingestionJob': {
                    'ingestionJobId': 'JOB1234567', 'status': status,
                    'statistics': {'numberOfDocumentsFailed': failed}, 'failureReasons': ['synthetic failure']}}
                with self.assertRaises(RuntimeError):
                    self.run_pipeline()
                self.assertEqual(self.report()['job']['failureReasons'], ['synthetic failure'])
                self.assertFalse(self.report()['lock_retained'])
                self.assertEqual(self.report()['status'], 'FAILED')

    def test_timeout_preserves_job_id_and_lock(self):
        now = [0]
        self.agent.get_ingestion_job.return_value['ingestionJob']['status'] = 'IN_PROGRESS'
        with self.assertRaises(TimeoutError):
            self.run_pipeline(clock=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
        self.assertEqual(self.report()['job']['ingestionJobId'], 'JOB1234567')
        self.assertTrue(self.report()['lock_retained'])
        self.assertEqual(self.report()['status'], 'TIMEOUT')
        self.s3.delete_object.assert_not_called()

    def test_lost_start_response_preserves_durable_idempotency_token(self):
        self.agent.start_ingestion_job.side_effect = ConnectionError('response lost')
        with self.assertRaises(ConnectionError):
            self.run_pipeline()
        lock = json.loads(self.s3.put_object.call_args_list[0].kwargs['Body'])
        self.assertEqual(lock['client_token'], self.report()['run_id'])
        self.assertTrue(self.report()['lock_retained'])
        self.s3.delete_object.assert_not_called()

    def test_poll_error_preserves_known_job_and_lock(self):
        self.agent.get_ingestion_job.side_effect = ConnectionError('connection lost')
        with self.assertRaises(ConnectionError):
            self.run_pipeline()
        self.assertEqual(self.report()['job']['ingestionJobId'], 'JOB1234567')
        self.assertTrue(self.report()['lock_retained'])

    def test_missing_statistics_cannot_be_reported_as_success(self):
        self.agent.get_ingestion_job.return_value['ingestionJob'].pop('statistics')
        with self.assertRaisesRegex(RuntimeError, 'no document failure statistics'):
            self.run_pipeline()
        self.assertEqual(self.report()['status'], 'FAILED')

    def test_lock_release_failure_is_reported_and_fails_run(self):
        self.s3.delete_object.side_effect = ConnectionError('release failed')
        with self.assertRaisesRegex(ConnectionError, 'release failed'):
            self.run_pipeline()
        self.assertEqual(self.report()['status'], 'FAILED')
        self.assertTrue(self.report()['lock_retained'])

    def test_repeated_runs_keep_exact_inventory(self):
        first = self.run_pipeline()
        self.s3.get_paginator.return_value.paginate.return_value = [
            {'Contents': [{'Key': key} for key in first['uploaded']]}]
        second = self.run_pipeline()
        self.assertEqual(first['uploaded'], second['uploaded'])
        self.assertEqual(first['sha256'], second['sha256'])
        self.assertNotEqual(first['run_id'], second['run_id'])

    def test_new_document_version_keeps_stable_policy_keys(self):
        first = snapshot(self.root)
        metadata = copy.deepcopy(json.loads((self.root / 'documents.json').read_text()))
        # Regenerate actual PDFs and sidecars for a source revision.
        from scripts import generate_poc_policies
        item = metadata[0]
        old = self.root / (item['metadata']['document_id'] + '.pdf')
        old.unlink()
        old.with_name(old.name + '.metadata.json').unlink()
        item['metadata']['version'] = '2'
        item['metadata']['document_id'] = 'auto_user_1_v2'
        (self.root / 'documents.json').write_text(json.dumps(metadata))
        with patch.object(generate_poc_policies, 'ROOT', self.root):
            generate_poc_policies.main()
        from ingestion.corpus import prepare
        prepare(self.root)
        second = snapshot(self.root)
        self.assertEqual(set(first), set(second))
        self.assertNotEqual(first['POC_AUTO_001.pdf'], second['POC_AUTO_001.pdf'])
        self.assertEqual(json.loads(second['POC_AUTO_001.pdf.metadata.json'])['metadataAttributes']['version'], '2')

    def test_unknown_remote_inventory_is_never_deleted_or_synced(self):
        self.s3.get_paginator.return_value.paginate.return_value = [
            {'Contents': [{'Key': SETTINGS.prefix + 'unmanaged.pdf'}]}]
        with self.assertRaisesRegex(ValueError, 'Unmanaged'):
            self.run_pipeline()
        self.assertEqual(self.s3.put_object.call_count, 1)
        self.agent.start_ingestion_job.assert_not_called()
        self.assertEqual(self.s3.delete_object.call_args.kwargs['Key'], SETTINGS.lock_key)

    def test_configuration_mismatch_blocks_all_writes(self):
        self.agent.get_data_source.return_value['dataSource']['dataSourceConfiguration']['s3Configuration']['inclusionPrefixes'] = ['approved/']
        with self.assertRaisesRegex(ValueError, 'exactly'):
            self.run_pipeline()
        self.s3.put_object.assert_not_called()

    def test_nonfilterable_owner_is_rejected(self):
        self.vectors.get_index.return_value['index']['metadataConfiguration']['nonFilterableMetadataKeys'].append('owner_id')
        with self.assertRaisesRegex(ValueError, 'incompatible'):
            self.run_pipeline()
        self.s3.put_object.assert_not_called()

    def test_active_jobs_on_later_page_block_run(self):
        self.agent.list_ingestion_jobs.side_effect = [
            {'ingestionJobSummaries': [], 'nextToken': 'next'},
            {'ingestionJobSummaries': [{'ingestionJobId': 'OTHER', 'status': 'STARTING'}]}]
        with self.assertRaisesRegex(RuntimeError, 'OTHER'):
            self.run_pipeline()
        self.s3.put_object.assert_not_called()

    def test_invalid_settings(self):
        for field, value in [('prefix', 'approved/'), ('prefix', 'ingestion_control/poc/'),
                             ('knowledge_base_id', 'replace_from_terraform_output'), ('timeout', 0)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                Settings(**{**SETTINGS.__dict__, field: value}).validate()
