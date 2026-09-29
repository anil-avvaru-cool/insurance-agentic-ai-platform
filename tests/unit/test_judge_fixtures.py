import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from evaluation.fixtures import validate_baseline

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / 'data/sample_insurance_policies'
QUESTIONS = ROOT / 'tests/fixtures/aws_poc/questions.json'
MANIFEST = ROOT / 'tests/fixtures/aws_poc/judge_baseline.json'


class JudgeFixtureTests(TestCase):
    def test_current_pdf_sources_and_six_cases(self):
        report = validate_baseline(CORPUS, QUESTIONS, MANIFEST)
        self.assertEqual(report['validated_questions'], 36)
        self.assertEqual(len(report['case_ids']), 6)
        self.assertIn('auto_user_1_v2.pdf', report['sha256'])

    def test_stale_version_passage_amount_and_owner_are_rejected(self):
        for failure in ('version', 'passage', 'amount', 'owner'):
            cases = json.loads(QUESTIONS.read_text())
            if failure == 'version':
                cases[0]['allowed_document_ids'] = ['auto_user_1_v1']
            elif failure == 'passage':
                cases[0]['supporting_passages'][0]['text'] = 'Old $500 deductible'
            elif failure == 'amount':
                cases[0]['expected_answer'] = '$500'
            else:
                cases[0]['owner_id'] = 'customer_two'
            with self.subTest(failure=failure), TemporaryDirectory() as directory:
                path = Path(directory) / 'questions.json'
                path.write_text(json.dumps(cases))
                with self.assertRaises(ValueError):
                    validate_baseline(CORPUS, path, MANIFEST)

    def test_baseline_rejects_missing_duplicate_or_wrong_scenarios(self):
        manifest = json.loads(MANIFEST.read_text())
        ids = manifest['case_ids']
        for altered in (ids[:-1], ids[:-1] + [ids[0]], list(reversed(ids)), ids[:-1] + ['missing']):
            with TemporaryDirectory() as directory:
                path = Path(directory) / 'baseline.json'
                path.write_text(json.dumps({**manifest, 'case_ids': altered}))
                with self.assertRaises(ValueError):
                    validate_baseline(CORPUS, QUESTIONS, path)
