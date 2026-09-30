"""Local preparation and validation for a single six-case Bedrock evaluation."""
from contextlib import closing
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from pathlib import Path
import sqlite3

from apps.query_lambda.query import _evidence
from evaluation.online import check_answer

METRICS = ['Builtin.Correctness', 'Builtin.Faithfulness']


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def positive(value, name):
    number = Decimal(str(value))
    if not number.is_finite() or number <= 0:
        raise ValueError(f'{name} must be finite and positive')
    return number


def estimate(config, today=None):
    """Explicit operator bounds, including overhead for each of two metrics."""
    today = today or date.today()
    priced = date.fromisoformat(config['pricing_date'])
    if not 0 <= (today - priced).days <= 30:
        raise ValueError('pricing inputs must be dated within the last 30 days')
    for key in ('region', 'evaluator_model_id', 'pricing_source'):
        if not isinstance(config[key], str) or not config[key].strip():
            raise ValueError(f'missing {key}')
    budget = positive(config['budget_usd'], 'budget_usd')
    margin = positive(config['safety_multiplier'], 'safety_multiplier')
    if margin < 1:
        raise ValueError('safety_multiplier must be at least one')
    total = Decimal(0)
    for component, calls in (('capture', 6), ('judge', 12)):
        for direction in ('input', 'output'):
            bound = positive(config[f'{component}_{direction}_token_bound'], 'token bound')
            if bound != int(bound):
                raise ValueError('token bounds must be integers')
            rate = positive(config[f'{component}_{direction}_usd_per_million'], 'token rate')
            total += calls * bound * rate / 1_000_000
    total += positive(config['supporting_cost_bound_usd'], 'supporting cost bound')
    reserved = (total * margin).quantize(Decimal('0.000001'), rounding=ROUND_CEILING)
    if reserved > budget:
        raise ValueError('estimate exceeds budget')
    return {'estimated_usd': str(reserved), 'budget_usd': str(budget),
            'capture_requests': 6, 'judge_metric_calls': 12,
            'pricing_date': config['pricing_date'], 'pricing_config_sha256': digest(config),
            'billing_cap': False}


class BudgetLedger:
    """One shared local SQLite ledger; unresolved reservations never expire."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('CREATE TABLE IF NOT EXISTS reservations (run_id TEXT PRIMARY KEY, amount TEXT NOT NULL, state TEXT NOT NULL)')
            connection.execute('CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY CHECK(id=1), amount TEXT NOT NULL)')

    def reserve(self, run_id, amount, budget):
        amount, budget = positive(amount, 'reservation'), positive(budget, 'budget')
        if not run_id:
            raise ValueError('run_id required')
        with closing(sqlite3.connect(self.path, timeout=30)) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            stored = connection.execute('SELECT amount FROM budget WHERE id=1').fetchone()
            if stored and Decimal(stored[0]) != budget:
                raise ValueError('shared ledger budget cannot change')
            connection.execute('INSERT OR IGNORE INTO budget VALUES (1, ?)', (str(budget),))
            used = sum((Decimal(row[0]) for row in connection.execute('SELECT amount FROM reservations')), Decimal(0))
            if used + amount > budget:
                raise ValueError('remaining budget insufficient')
            connection.execute('INSERT INTO reservations VALUES (?, ?, ?)', (run_id, str(amount), 'reserved'))


def export_dataset(cases, report, identity, now=None):
    """Return AWS JSONL rows and a hash-based association manifest, never references as evidence."""
    now = now or datetime.now(timezone.utc)
    if len(cases) != 6 or len({case['case_id'] for case in cases}) != 6:
        raise ValueError('exactly six unique cases required')
    if report.get('fixture_sha256') != identity['fixture_sha256'] or report.get('corpus_sha256') != identity['corpus_sha256']:
        raise ValueError('stale fixture or corpus hashes')
    samples = report['results']
    if len(samples) != 6 or len({item['case_id'] for item in samples}) != 6:
        raise ValueError('exactly six unique samples required')
    by_id = {item['case_id']: item for item in samples}
    rows, associations, request_ids = [], [], set()
    for case in cases:
        item = by_id[case['case_id']]
        if item.get('passed') is not True or item.get('errors') or item.get('http_status') != 200:
            raise ValueError('failed capture cannot be evaluated')
        artifact = item['evaluation_evidence']
        if item['response'].get('evaluation_capture', {}).get('sha256') != digest(artifact):
            raise ValueError('capture hash mismatch')
        response = {key: item['response'][key] for key in ('request_id', 'answer', 'citations')}
        request = {key: case[key] for key in ('question', 'owner_id', 'lob')}
        if artifact['schema_version'] != 1 or artifact['request'] != request or artifact['response'] != response:
            raise ValueError('capture request/response mismatch')
        request_id = artifact['request_id']
        if not request_id or request_id != response['request_id'] or request_id in request_ids:
            raise ValueError('duplicate or invalid request ID')
        request_ids.add(request_id)
        created = datetime.fromisoformat(artifact['created_at'])
        if created.tzinfo is None or not 0 <= (now - created).total_seconds() <= identity['max_age_seconds']:
            raise ValueError('stale capture timestamp')
        config = artifact['configuration']
        if artifact['deployment_id'] != identity['deployment_id'] or config['model_id'] != identity['model_id'] or config['knowledge_base_id'] != identity['knowledge_base_id']:
            raise ValueError('deployment/model/knowledge base mismatch')
        expected_filter = {'andAll': [{'equals': {'key': key, 'value': request[key]}} for key in ('owner_id', 'lob')]}
        if artifact['retrieval_filter'] != expected_filter or artifact['context_truncated'] is not False:
            raise ValueError('filter mismatch or truncated evidence')
        retrieved = artifact['retrieval_results']
        if any(result.get('metadata', {}).get('document_id') not in case['allowed_document_ids'] for result in retrieved):
            raise ValueError('retrieval outside allowed documents')
        try:
            evidence, references = _evidence(retrieved, config, case['owner_id'], case['lob'])
        except RuntimeError as error:
            raise ValueError(str(error)) from error
        if evidence != artifact['generation_evidence'] or references != artifact['evidence_references']:
            raise ValueError('generation context differs from retrieval')
        if artifact['model_invoked'] is not bool(references):
            raise ValueError('invalid model invocation flag')
        for count in artifact['usage'].values():
            if type(count) is not int or count < 0:
                raise ValueError('missing or invalid usage')
        if set(artifact['usage']) != {'input_tokens', 'output_tokens'}:
            raise ValueError('missing usage fields')
        if check_answer(case, response):
            raise ValueError('answer contract or isolation checks failed')
        for citation in response['citations']:
            if references.get(citation['evidence_id']) != citation:
                raise ValueError('citation differs from captured evidence')
        row = {'conversationTurns': [{'prompt': {'content': [{'text': case['question']}]},
               'referenceResponses': [{'content': [{'text': case['expected_answer']}]}],
               'output': {'text': response['answer'], 'modelIdentifier': config['model_id'],
                          'knowledgeBaseIdentifier': config['knowledge_base_id'],
                          'retrievedPassages': {'retrievalResults': [
                              {'name': key, 'content': {'text': retrieved[int(key[1:]) - 1]['content']['text'].strip()},
                               'metadata': retrieved[int(key[1:]) - 1]['metadata']} for key in references]}}}]}
        rows.append(row)
        associations.append({'case_id': case['case_id'], 'request_id': request_id,
                             'capture_sha256': digest(artifact), 'row_sha256': digest(row),
                             'reviewer': None, 'reviewed_at': None, 'passed': None, 'reasons': None})
    return rows, {'schema_version': 1, 'identity': identity, 'metrics': METRICS,
                  'empty_retrieval_service_verification_required': any(not row['conversationTurns'][0]['output']['retrievedPassages']['retrievalResults'] for row in rows),
                  'cases': associations}


def job_request(config, run_id, identity):
    """Construct and SDK-validate a request without creating a client or job."""
    from urllib.parse import urlsplit
    from botocore.session import Session
    from botocore.validate import validate_parameters
    for key in ('dataset_s3_uri', 'output_s3_uri'):
        uri = urlsplit(config[key])
        if uri.scheme != 's3' or not uri.netloc or not uri.path.strip('/') or uri.query or uri.fragment:
            raise ValueError(f'invalid {key}')
    if config['dataset_s3_uri'].startswith(config['output_s3_uri']):
        raise ValueError('dataset must be separate from output prefix')
    request = {'jobName': f'rag_judge_{run_id}', 'clientRequestToken': digest({'run_id': run_id, 'identity': identity}),
               'roleArn': config['evaluation_role_arn'], 'applicationType': 'RagEvaluation',
               'evaluationConfig': {'automated': {
                   'datasetMetricConfigs': [{'taskType': 'General', 'dataset': {'name': 'six_case_baseline',
                       'datasetLocation': {'s3Uri': config['dataset_s3_uri']}}, 'metricNames': METRICS}],
                   'evaluatorModelConfig': {'bedrockEvaluatorModels': [{'modelIdentifier': config['evaluator_model_id']}]}}},
               'inferenceConfig': {'ragConfigs': [{'precomputedRagSourceConfig': {
                   'retrieveAndGenerateSourceConfig': {'ragSourceIdentifier': identity['knowledge_base_id']}}}]},
               'outputDataConfig': {'s3Uri': config['output_s3_uri']}}
    shape = Session().get_service_model('bedrock').operation_model('CreateEvaluationJob').input_shape
    validate_parameters(request, shape)
    return request
