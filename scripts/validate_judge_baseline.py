"""Check the current PDFs, fixtures, and six-case baseline without AWS calls."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from evaluation.fixtures import validate_baseline

if __name__ == '__main__':
    print(json.dumps(validate_baseline(ROOT / 'data/sample_insurance_policies',
                                      ROOT / 'tests/fixtures/aws_poc/questions.json',
                                      ROOT / 'tests/fixtures/aws_poc/judge_baseline.json'), indent=2))
