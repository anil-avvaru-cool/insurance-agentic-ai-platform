"""Validate and ingest all four POC policies; settings come from Terraform or .env."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import uuid

from adapters.models.bedrock import client
from ingestion.corpus import ROOT
from ingestion.offline import Settings, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--terraform-dir', type=Path,
                        help='read ingestion_environment from an initialized, applied Terraform root')
    parser.add_argument('--report', type=Path, help='JSON run report; default: ingestion_reports/<unique run>.json')
    args = parser.parse_args()
    report_path = args.report or Path('ingestion_reports') / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex + '.json')
    try:
        if args.terraform_dir:
            result = subprocess.run(['terraform', f'-chdir={args.terraform_dir}', 'output', '-json',
                                     'ingestion_environment'], check=True, text=True, capture_output=True)
            environment = json.loads(result.stdout)
            os.environ.update({key: str(value) for key, value in environment.items()})
        settings = Settings.from_env()
        result = run(settings, args.root, report_path, client('s3'), client('bedrock-agent'), client('s3vectors'))
    except Exception as error:
        parser.exit(1, f'Ingestion failed: {error}\nRun report (if initialized): {report_path}\n')
    print(json.dumps({'status': result['status'], 'job': result['job'], 'report': str(report_path)}, default=str))


if __name__ == '__main__':
    main()
