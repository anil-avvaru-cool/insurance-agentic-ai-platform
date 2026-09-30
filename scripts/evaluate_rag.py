"""Offline judge preparation and exact evidence export. No AWS calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from evaluation.fixtures import validate_baseline
from evaluation.judge import BudgetLedger, digest, estimate, export_dataset, job_request


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare', help='Validate fixtures and estimate costs without inference')
    prepare.add_argument('--output', type=Path, required=True)
    reserve = sub.add_parser('reserve', help='Atomically reserve a prepared estimate in a shared local ledger')
    reserve.add_argument('--prepared', type=Path, required=True)
    reserve.add_argument('--ledger', type=Path, required=True)
    export = sub.add_parser('export', help='Validate six captured responses and write AWS JSONL')
    export.add_argument('--prepared', type=Path, required=True)
    export.add_argument('--captures', type=Path, required=True)
    export.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    validation = validate_baseline(ROOT / 'data/sample_insurance_policies', ROOT / 'tests/fixtures/aws_poc/questions.json', ROOT / 'tests/fixtures/aws_poc/judge_baseline.json')
    fixture_hash = hashlib.sha256((ROOT / 'tests/fixtures/aws_poc/questions.json').read_bytes()).hexdigest()
    corpus_hash = digest(validation['sha256'])
    if args.command == 'prepare':
        keys = ('pricing_date', 'region', 'evaluator_model_id', 'pricing_source', 'budget_usd',
                'safety_multiplier', 'supporting_cost_bound_usd', 'deployment_id', 'model_id',
                'knowledge_base_id', 'max_age_seconds', 'evaluation_role_arn', 'dataset_s3_uri', 'output_s3_uri')
        config = {key: os.environ['JUDGE_' + key.upper()] for key in keys}
        config['max_age_seconds'] = int(config['max_age_seconds'])
        for component in ('capture', 'judge'):
            for direction in ('input', 'output'):
                for suffix in ('token_bound', 'usd_per_million'):
                    key = f'{component}_{direction}_{suffix}'
                    config[key] = os.environ['JUDGE_' + key.upper()]
        estimate_result = estimate(config)
        identity = {key: config[key] for key in ('deployment_id', 'model_id', 'knowledge_base_id', 'max_age_seconds')}
        if type(identity['max_age_seconds']) is not int or identity['max_age_seconds'] <= 0 or any(not isinstance(identity[key], str) or not identity[key].strip() for key in ('deployment_id', 'model_id', 'knowledge_base_id')):
            raise ValueError('explicit deployment identity and positive capture age required')
        prepared = {'schema_version': 1, 'run_id': uuid.uuid4().hex, 'validation': validation,
                    'identity': {**identity, 'fixture_sha256': fixture_hash, 'corpus_sha256': corpus_hash},
                    'config': config, 'estimate': estimate_result, 'aws_verified': False}
        prepared['job_request'] = job_request(config, prepared['run_id'], prepared['identity'])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as stream:
            stream.write(json.dumps(prepared, indent=2) + '\n')
    else:
        prepared = json.loads(args.prepared.read_text())
        if prepared['identity']['fixture_sha256'] != fixture_hash or prepared['identity']['corpus_sha256'] != corpus_hash:
            raise ValueError('prepared inputs are stale')
        if prepared['job_request'] != job_request(prepared['config'], prepared['run_id'], prepared['identity']):
            raise ValueError('prepared job request changed')
        if estimate(prepared['config']) != prepared['estimate']:
            raise ValueError('prepared estimate changed')
        if args.command == 'reserve':
            BudgetLedger(args.ledger).reserve(prepared['run_id'], prepared['estimate']['estimated_usd'], prepared['estimate']['budget_usd'])
        else:
            rows, manifest = export_dataset([case for key in validation['case_ids'] for case in json.loads((ROOT / 'tests/fixtures/aws_poc/questions.json').read_text()) if case['case_id'] == key], json.loads(args.captures.read_text()), prepared['identity'])
            manifest['run_id'] = prepared['run_id']
            args.output.mkdir(parents=True, exist_ok=False)
            (args.output / 'dataset.jsonl').write_text(''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in rows))
            (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'{args.command} completed locally; deployed verification and paid evaluation remain pending.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
