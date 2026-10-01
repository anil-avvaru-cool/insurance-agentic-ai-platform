"""Explicit operator commands; AWS clients are created only by live commands."""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from urllib.parse import urlsplit

from evaluation.judge import CUSTOM_METRIC, METRICS, digest, estimate, job_request


def add_commands(sub):
    capture = sub.add_parser('capture', help='Send exactly six paid API requests with evidence capture; no retries')
    capture.add_argument('--prepared', type=Path, required=True)
    capture.add_argument('--output', type=Path, required=True)
    for name in ('upload', 'submit'):
        command = sub.add_parser(name, help='Upload private inputs' if name == 'upload' else 'Submit one paid job; reuse saved request on retry')
        command.add_argument('--prepared', type=Path, required=True)
        command.add_argument('--export', dest='export_dir', type=Path, required=True)
        command.add_argument('--state', type=Path, required=True)
    for name in ('status', 'collect'):
        command = sub.add_parser(name, help='Inspect saved job' if name == 'status' else 'Download only this completed job and summarize results')
        command.add_argument('--state', type=Path, required=True)
        command.add_argument('--output', type=Path, required=True)
    summarize = sub.add_parser('summarize', help='Offline summary of downloaded AWS JSONL artifacts')
    summarize.add_argument('--export', dest='export_dir', type=Path, required=True)
    summarize.add_argument('--results', type=Path, required=True)
    summarize.add_argument('--output', type=Path, required=True)


def write_json(path, value, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        with path.open('x') as stream:
            json.dump(value, stream, indent=2, default=str, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
    else:
        temporary = path.with_name(path.name + '.tmp')
        with temporary.open('w') as stream:
            json.dump(value, stream, indent=2, default=str, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)


def load_prepared(path, root):
    from evaluation.fixtures import validate_baseline
    prepared = json.loads(path.read_text())
    validation = validate_baseline(root / 'data/sample_insurance_policies', root / 'tests/fixtures/aws_poc/questions.json', root / 'tests/fixtures/aws_poc/judge_baseline.json')
    identity = prepared['identity']
    if identity['fixture_sha256'] != hashlib.sha256((root / 'tests/fixtures/aws_poc/questions.json').read_bytes()).hexdigest() or identity['corpus_sha256'] != digest(validation['sha256']):
        raise ValueError('prepared fixture/corpus inputs are stale')
    if prepared['job_request'] != job_request(prepared['config'], prepared['run_id'], identity):
        raise ValueError('prepared request changed')
    if prepared['estimate'] != estimate(prepared['config']):
        raise ValueError('prepared estimate changed')
    return prepared


def load_export(directory, prepared=None):
    encoded = (directory / 'dataset.jsonl').read_bytes()
    rows = [json.loads(line) for line in encoded.splitlines()]
    manifest = json.loads((directory / 'manifest.json').read_text())
    cases = manifest['cases']
    if len(rows) != 6 or len(cases) != 6 or len({case['case_id'] for case in cases}) != 6 or manifest['metrics'] != METRICS:
        raise ValueError('exactly six unique cases and all three metrics required')
    for row, case in zip(rows, cases):
        if digest(row) != case['row_sha256'] or case['deterministic_checks_passed'] is not True:
            raise ValueError('export association or deterministic checks changed')
        if row['conversationTurns'][0]['output']['knowledgeBaseIdentifier'] != manifest['identity']['rag_source_id']:
            raise ValueError('dataset RAG source mismatch')
    if prepared and (manifest['identity'] != prepared['identity'] or manifest['run_id'] != prepared['run_id']):
        raise ValueError('export does not match prepared run')
    return encoded, rows, manifest


def s3_location(uri):
    parsed = urlsplit(uri)
    if parsed.scheme != 's3' or not parsed.netloc or not parsed.path.strip('/') or parsed.query or parsed.fragment:
        raise ValueError('invalid S3 URI')
    return parsed.netloc, parsed.path.lstrip('/')


def read_object(storage, bucket, key):
    stream = storage.get_object(Bucket=bucket, Key=key)['Body']
    try:
        return stream.read()
    finally:
        stream.close()


def upload(storage, prepared, encoded):
    """Conditional write prevents accidentally replacing an existing job's inputs."""
    from botocore.exceptions import ClientError
    bucket, key = s3_location(prepared['config']['dataset_s3_uri'])
    try:
        storage.put_object(Bucket=bucket, Key=key, Body=encoded, ContentType='application/jsonl',
                           ServerSideEncryption='AES256', IfNoneMatch='*')
    except ClientError as error:
        if error.response['Error']['Code'] not in ('PreconditionFailed', '412'):
            raise
        if read_object(storage, bucket, key) != encoded:
            raise ValueError('S3 input already exists with different content; use a new run/input key') from error


def submit(bedrock, storage, prepared, encoded, manifest, state_path):
    """Persist request before sending; ambiguous failures retain the same token."""
    state = {'schema_version': 1, 'region': prepared['config']['region'], 'run_id': prepared['run_id'],
             'request': prepared['job_request'], 'dataset_sha256': hashlib.sha256(encoded).hexdigest(),
             'manifest': manifest, 'job_arn': None}
    if state_path.exists():
        existing = json.loads(state_path.read_text())
        if any(existing[key] != state[key] for key in state if key != 'job_arn'):
            raise ValueError('saved submission differs; cannot reuse this state file')
        state = existing
        if state['job_arn']:
            return state
    else:
        write_json(state_path, state, exclusive=True)
    bucket, key = s3_location(prepared['config']['dataset_s3_uri'])
    if read_object(storage, bucket, key) != encoded:
        raise ValueError('S3 input differs from validated export')
    response = bedrock.create_evaluation_job(**state['request'])
    state['job_arn'] = response['jobArn']
    write_json(state_path, state)
    return state


def summarize(rows, manifest, records):
    """Associate by returned input, never output ordering; retain unknown results."""
    by_hash = {digest(row): index for index, row in enumerate(rows)}
    if len(by_hash) != 6:
        raise ValueError('duplicate dataset rows')
    cases = [{**case, 'scores': {metric: None for metric in METRICS},
              'explanations': {}, 'review_notes': None} for case in manifest['cases']]
    issues, unmatched, seen = [], [], set()
    for record in records:
        input_record = record.get('inputRecord')
        index = by_hash.get(digest(input_record))
        if index is None:
            unmatched.append(record)
            issues.append('Result inputRecord does not match a validated dataset row')
            continue
        scores = record.get('automatedEvaluationResult', {}).get('scores', [])
        if not scores:
            issues.append(f"No recognized scores for {cases[index]['case_id']}")
        for item in scores:
            metric, value = item.get('metricName'), item.get('result')
            if metric not in METRICS:
                issues.append(f'Unrecognized metric: {metric}')
                continue
            pair = index, metric
            if pair in seen:
                raise ValueError('duplicate case/metric result; inspect artifacts')
            seen.add(pair)
            explanation = item.get('explanation', item.get('reason'))
            if explanation is not None:
                cases[index]['explanations'][metric] = explanation
            if type(value) not in (int, float) or not math.isfinite(value) or (metric == CUSTOM_METRIC and value not in (0, 1)):
                issues.append(f"Invalid or unavailable {metric} for {cases[index]['case_id']}")
                continue
            cases[index]['scores'][metric] = value
    groups = {}
    for name, selected in [('all', cases), ('abstention', [case for case in cases if case['expected_status'] == 'insufficient_information']),
                           ('answerable', [case for case in cases if case['expected_status'] != 'insufficient_information'])]:
        values = [case['scores'][CUSTOM_METRIC] for case in selected if case['scores'][CUSTOM_METRIC] is not None]
        groups[name] = {'expected_cases': len(selected), 'scored_cases': len(values),
                        'pass_count': sum(value == 1 for value in values), 'fail_count': sum(value == 0 for value in values),
                        'complete': len(values) == len(selected),
                        'mean_available_scores': sum(values) / len(values) if values else None}
    missing = [{'case_id': case['case_id'], 'metric': metric} for case in cases for metric, value in case['scores'].items() if value is None]
    return {'schema_version': 1, 'metrics': METRICS, 'cases': cases, 'custom_metric_summary': groups,
            'scores_complete': not missing and not issues, 'missing_scores': missing, 'issues': issues,
            'unmatched_results': unmatched, 'human_review_required': True,
            'limitations': ['Live output schema and empty-retrieval handling require first-run verification.',
                            'Judge scores do not prove retrieval isolation or citation support; deterministic checks retained.',
                            'Available-score means exclude missing scores; incomplete groups are not passes.']}


def result_records(directory):
    records = []
    for path in sorted(directory.rglob('*.jsonl')):
        for line in path.read_text().splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def collect(storage, state, output):
    bucket, base = s3_location(state['request']['outputDataConfig']['s3Uri'])
    job_id = state['job_arn'].rsplit('/', 1)[-1]
    prefix = base.rstrip('/') + '/' + state['request']['jobName'] + '/' + job_id + '/'
    output.mkdir(parents=True, exist_ok=False)
    artifacts = []
    for page in storage.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefix):
        for entry in page.get('Contents', []):
            key = entry['Key']
            if key.endswith('/'):
                continue
            relative = Path(key[len(prefix):])
            if relative.is_absolute() or '..' in relative.parts or not key.startswith(prefix):
                raise ValueError('unsafe result artifact path')
            path = output / 'artifacts' / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(read_object(storage, bucket, key))
            artifacts.append({'s3_uri': f's3://{bucket}/{key}', 'local_path': str(path)})
    write_json(output / 'downloads.json', {'job_arn': state['job_arn'], 'prefix': prefix, 'artifacts': artifacts})
    return output / 'artifacts'


def capture(prepared, root, output):
    import boto3
    import httpx
    from scripts.test_online_rag import RequestSigner, run, scenarios
    endpoint = os.environ['RAG_QUERY_ENDPOINT']
    url = urlsplit(endpoint)
    bucket, prefix = os.environ['QUERY_CAPTURE_BUCKET'], os.environ['QUERY_CAPTURE_PREFIX']
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('provide an HTTPS endpoint without credentials, query string or fragment')
    if not bucket or not prefix or not prefix.endswith('/'):
        raise ValueError('capture bucket and prefix ending in / required')
    fixtures = json.loads((root / 'tests/fixtures/aws_poc/questions.json').read_text())
    cases = [next(case for case in fixtures if case['case_id'] == key) for key in prepared['validation']['case_ids']]
    report = {key: prepared['identity'][key] for key in ('fixture_sha256', 'corpus_sha256')}
    report.update(created_at=datetime.now(timezone.utc).isoformat(), results=[], semantic_review_required=True)
    write_json(output, report, exclusive=True)
    session = boto3.Session(region_name=prepared['config']['region'])
    signer = RequestSigner(session)
    storage = session.client('s3')
    try:
        with httpx.Client(timeout=40, follow_redirects=False) as client:
            for case in cases:
                report['results'].extend(run(client, endpoint, scenarios([case], True), 0, signer, storage, bucket, prefix))
                serialized = json.dumps(report)
                for secret in sorted(signer.secrets, key=len, reverse=True):
                    serialized = serialized.replace(secret, '[REDACTED]')
                write_json(output, json.loads(serialized))
                if not report['results'][-1]['passed']:
                    return 1
    except Exception as error:
        report['capture_error'] = type(error).__name__
        serialized = json.dumps(report)
        for secret in sorted(signer.secrets, key=len, reverse=True):
            serialized = serialized.replace(secret, '[REDACTED]')
        write_json(output, json.loads(serialized))
        raise
    return 0


def execute(args, root):
    if args.command == 'summarize':
        _, rows, manifest = load_export(args.export_dir)
        report = summarize(rows, manifest, result_records(args.results))
        write_json(args.output, report, exclusive=True)
        return 0 if report['scores_complete'] else 1
    if args.command in ('capture', 'upload', 'submit'):
        if args.command == 'submit' and args.state.exists():
            # Recovery uses the original request even after pricing/captures expire.
            prepared = json.loads(args.prepared.read_text())
            if prepared['job_request'] != job_request(prepared['config'], prepared['run_id'], prepared['identity']):
                raise ValueError('prepared request changed')
        else:
            prepared = load_prepared(args.prepared, root)
        if args.command == 'capture':
            return capture(prepared, root, args.output)
        encoded, _, manifest = load_export(args.export_dir, prepared)
        receipt = {'run_id': prepared['run_id'], 'dataset_s3_uri': prepared['config']['dataset_s3_uri'],
                   'dataset_sha256': hashlib.sha256(encoded).hexdigest()}
        if args.command == 'upload' and args.state.exists() and json.loads(args.state.read_text()) != receipt:
            raise ValueError('upload receipt differs; use a separate state file')
        import boto3
        session = boto3.Session(region_name=prepared['config']['region'])
        storage = session.client('s3')
        if args.command == 'upload':
            upload(storage, prepared, encoded)
            if not args.state.exists():
                write_json(args.state, receipt, exclusive=True)
            print('Validated dataset uploaded.')
        else:
            state = submit(session.client('bedrock'), storage, prepared, encoded, manifest, args.state)
            print(f"Job ARN: {state['job_arn']}")
        return 0
    state = json.loads(args.state.read_text())
    if not state['job_arn']:
        raise ValueError('submission ARN unavailable; retry submit using the same saved request')
    import boto3
    session = boto3.Session(region_name=state['region'])
    job = session.client('bedrock').get_evaluation_job(jobIdentifier=state['job_arn'])
    if args.command == 'status':
        write_json(args.output, job)
        print(json.dumps({key: job.get(key) for key in ('status', 'failureMessages', 'outputDataConfig')}, default=str))
        return 0
    if job['status'] != 'Completed':
        raise ValueError(f"Job is {job['status']}: {job.get('failureMessages', [])}; inspect status before another submission")
    if job['outputDataConfig'] != state['request']['outputDataConfig'] or job['jobName'] != state['request']['jobName']:
        raise ValueError('job output destination/name differs from saved request')
    storage = session.client('s3')
    bucket, key = s3_location(state['request']['evaluationConfig']['automated']['datasetMetricConfigs'][0]['dataset']['datasetLocation']['s3Uri'])
    encoded = read_object(storage, bucket, key)
    if hashlib.sha256(encoded).hexdigest() != state['dataset_sha256']:
        raise ValueError('submitted input changed; cannot safely associate results')
    rows = [json.loads(line) for line in encoded.splitlines()]
    artifacts = collect(storage, state, args.output)
    write_json(args.output / 'job.json', job)
    report = summarize(rows, state['manifest'], result_records(artifacts))
    report['job_arn'] = state['job_arn']
    write_json(args.output / 'report.json', report)
    print(f"Report: {args.output / 'report.json'}; human review remains required.")
    return 0 if report['scores_complete'] else 1
