"""Upload four validated policy PDFs and metadata to S3, then run Bedrock ingestion, one run at a time."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import uuid

from ingestion.corpus import prepare
from ingestion.jobs import TERMINAL, poll_job


@dataclass(frozen=True)
class Settings:
    region: str
    bucket: str
    prefix: str
    knowledge_base_id: str
    data_source_id: str
    timeout: int

    @classmethod
    def from_env(cls):
        settings = cls(os.environ['AWS_REGION'], os.environ['KNOWLEDGE_BUCKET'],
                       os.environ['KNOWLEDGE_POC_PREFIX'], os.environ['BEDROCK_KNOWLEDGE_BASE_ID'],
                       os.environ['BEDROCK_DATA_SOURCE_ID'],
                       int(os.environ['KNOWLEDGE_INGESTION_TIMEOUT_SECONDS']))
        settings.validate()
        return settings

    def validate(self):
        if not re.fullmatch(r'[a-z]{2}(?:-[a-z]+)+-\d', self.region):
            raise ValueError('AWS_REGION must be an AWS region')
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', self.bucket):
            raise ValueError('KNOWLEDGE_BUCKET must be a bucket name')
        if not re.fullmatch(r'(?:[a-z0-9_]+/){2,}', self.prefix):
            raise ValueError('KNOWLEDGE_POC_PREFIX needs a dedicated nested prefix ending in /')
        if self.prefix.startswith('ingestion_control/'):
            raise ValueError('Document prefix must not include ingestion_control/')
        if not all(re.fullmatch(r'[A-Za-z0-9]{10}', value)
                   for value in (self.knowledge_base_id, self.data_source_id)):
            raise ValueError('Supply actual ten-character Bedrock IDs from Terraform')
        if self.timeout <= 0:
            raise ValueError('KNOWLEDGE_INGESTION_TIMEOUT_SECONDS must be positive')

    @property
    def args(self):
        return {'knowledgeBaseId': self.knowledge_base_id, 'dataSourceId': self.data_source_id}

    @property
    def lock_key(self):
        return f'ingestion_control/{self.knowledge_base_id}/{self.data_source_id}/run_lock.json'


def readiness(settings, s3, agent, vectors):
    """Read actual deployed configuration, not just Terraform definitions."""
    s3.head_bucket(Bucket=settings.bucket)
    location = s3.get_bucket_location(Bucket=settings.bucket)['LocationConstraint'] or 'us-east-1'
    if location == 'EU':
        location = 'eu-west-1'
    if location != settings.region:
        raise ValueError('Document bucket is in a different region')
    kb = agent.get_knowledge_base(knowledgeBaseId=settings.knowledge_base_id)['knowledgeBase']
    if kb['status'] != 'ACTIVE':
        raise ValueError('Knowledge base is not ACTIVE')
    storage = kb['storageConfiguration']
    if storage['type'] != 'S3_VECTORS':
        raise ValueError('POC requires S3_VECTORS storage')
    vector = kb['knowledgeBaseConfiguration']['vectorKnowledgeBaseConfiguration']
    embedding = vector['embeddingModelConfiguration']['bedrockEmbeddingModelConfiguration']
    if (not vector['embeddingModelArn'].endswith('/amazon.titan-embed-text-v2:0')
            or embedding['dimensions'] != 1024 or embedding['embeddingDataType'] != 'FLOAT32'):
        raise ValueError('POC requires Titan Text Embeddings V2, FLOAT32, 1024 dimensions')
    index = vectors.get_index(indexArn=storage['s3VectorsConfiguration']['indexArn'])['index']
    nonfilterable = set(index.get('metadataConfiguration', {}).get('nonFilterableMetadataKeys', []))
    if (index['dimension'] != 1024 or index['dataType'] != 'float32'
            or index['distanceMetric'] != 'cosine' or {'owner_id', 'lob'} & nonfilterable):
        raise ValueError('Vector index dimensions/type/distance or owner/LOB filtering is incompatible')
    source = agent.get_data_source(**settings.args)['dataSource']
    config = source['dataSourceConfiguration']
    if (source['status'] != 'AVAILABLE' or config['type'] != 'S3'
            or config['s3Configuration']['bucketArn'] != f'arn:aws:s3:::{settings.bucket}'
            or config['s3Configuration'].get('inclusionPrefixes') != [settings.prefix]):
        raise ValueError('Data source must be AVAILABLE and read exactly the configured bucket/POC prefix')
    ingestion = source['vectorIngestionConfiguration']
    chunking = ingestion['chunkingConfiguration']
    if (chunking['chunkingStrategy'] != 'FIXED_SIZE'
            or chunking['fixedSizeChunkingConfiguration'] != {'maxTokens': 300, 'overlapPercentage': 15}
            or ingestion.get('parsingConfiguration') or source.get('syncSchedule')):
        raise ValueError('POC requires default text parsing, 300 tokens/15% overlap and explicit sync only')
    token = None
    while True:
        page = agent.list_ingestion_jobs(**settings.args, **({'nextToken': token} if token else {}))
        for job in page.get('ingestionJobSummaries', []):
            if job['status'] not in TERMINAL:
                raise RuntimeError(f"Existing ingestion job {job['ingestionJobId']} is {job['status']}")
        token = page.get('nextToken')
        if not token:
            break


def snapshot(root):
    # Read and validate a private copy so an edit during upload cannot change the bytes.
    with tempfile.TemporaryDirectory(prefix='poc_corpus_') as directory:
        copy = Path(directory)
        for path in root.iterdir():
            if path.name == 'documents.json' or path.name.endswith(('.pdf', '.pdf.metadata.json')):
                shutil.copyfile(path, copy / path.name)
        metadata = prepare(copy, check=True)
        files = {}
        for item in metadata:
            if len(json.dumps(item).encode()) > 1024:
                raise ValueError('S3 Vectors custom metadata exceeds 1 KiB')
            name = item['document_id'] + '.pdf'
            # A new document_id/version replaces the SAME policy's source object.
            key = item['policy_id'] + '.pdf'
            files[key] = (copy / name).read_bytes()
            files[key + '.metadata.json'] = (copy / (name + '.metadata.json')).read_bytes()
        return files


def run(settings, root, report_path, s3, agent, vectors, *, clock=time.monotonic, sleep=time.sleep):
    """Validate and upload the POC corpus, then monitor ingestion under a lock and record the outcome."""
    started = clock()
    report = {'run_id': str(uuid.uuid4()), 'started_at': datetime.now(timezone.utc).isoformat(),
              'status': 'VALIDATING', 'bucket': settings.bucket, 'prefix': settings.prefix,
              **settings.args, 'uploaded': [], 'job': None, 'start_attempted': False,
              'lock_retained': False}
    etag = None
    start_attempted = False
    terminal = False

    def save():
        report['duration_seconds'] = round(clock() - started, 3)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = report_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2, default=str) + '\n')
        temporary.replace(report_path)

    def update(job):
        nonlocal terminal
        terminal = job['status'] in TERMINAL
        report['job'] = job
        save()

    try:
        save()  # Verify report destination before any AWS write.
        settings.validate()
        files = snapshot(root)
        report['sha256'] = {name: hashlib.sha256(body).hexdigest() for name, body in files.items()}
        readiness(settings, s3, agent, vectors)
        report['status'] = 'UPLOADING'
        report['lock_key'] = settings.lock_key
        # No lease expiry: a slow uploader or timed-out job must never lose its lock.
        lock = {'run_id': report['run_id'], **settings.args, 'started_at': report['started_at'],
                'client_token': report['run_id'], 'description': f"poc_run_{report['run_id']}"}
        try:
            result = s3.put_object(Bucket=settings.bucket, Key=settings.lock_key,
                                   Body=json.dumps(lock).encode(), ContentType='application/json',
                                   IfNoneMatch='*')
        except BaseException:
            # A lost response can mean the lock was created; never delete a lock
            # without the ETag returned by our successful acquisition.
            report['lock_retained'] = True
            report['lock_note'] = 'Lock exists or acquisition outcome is uncertain; inspect its run_id before recovery.'
            raise
        etag = result['ETag']
        # Close the check/acquire race before changing any document.
        readiness(settings, s3, agent, vectors)
        expected = {settings.prefix + name for name in files}
        for page in s3.get_paginator('list_objects_v2').paginate(Bucket=settings.bucket, Prefix=settings.prefix):
            unexpected = {item['Key'] for item in page.get('Contents', [])} - expected
            if unexpected:
                raise ValueError('Unmanaged objects in POC prefix; refusing sync or cleanup: ' + ', '.join(sorted(unexpected)))
        for name, body in sorted(files.items()):
            key = settings.prefix + name
            s3.put_object(Bucket=settings.bucket, Key=key, Body=body,
                          ContentType='application/json' if name.endswith('.json') else 'application/pdf')
            report['uploaded'].append(key)
            save()
        report['status'] = 'STARTING'
        report['start_attempted'] = True
        save()
        # Persist token in the lock BEFORE this call; even a lost response is recoverable.
        start_attempted = True
        job = agent.start_ingestion_job(**settings.args, clientToken=report['run_id'],
                                        description=lock['description'])['ingestionJob']
        report['job'] = job
        report['status'] = 'INGESTING'
        save()
        poll_job(agent, settings.args, job, settings.timeout, update, clock, sleep)
        report['status'] = 'COMPLETE'
    except BaseException as error:
        report['status'] = 'TIMEOUT' if isinstance(error, TimeoutError) else 'FAILED'
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        if etag:
            if not start_attempted or terminal:
                try:
                    s3.delete_object(Bucket=settings.bucket, Key=settings.lock_key, IfMatch=etag)
                except Exception as error:
                    report['lock_retained'] = True
                    report['lock_release_error'] = str(error)
                    report['status'] = 'FAILED'
                    save()
                    raise
            else:
                report['lock_retained'] = True
        save()
    return report
