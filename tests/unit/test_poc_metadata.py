import json
from pathlib import Path
import shutil
import tempfile
import unittest

from ingestion.metadata import extract_metadata, validate_metadata
from ingestion.pdf import parse_pdf
from scripts.prepare_poc_metadata import ROOT, prepare


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.expected = json.loads((ROOT / 'documents.json').read_text())[0]['metadata']
        self.text = parse_pdf(ROOT / 'auto_user_1_v1.pdf')

    def test_real_pdfs_and_checked_in_sidecars(self):
        result = prepare(ROOT, check=True)
        self.assertEqual(len(result), 4)
        self.assertEqual(len({item['document_id'] for item in result}), 4)
        for owner in ('customer_one', 'customer_two'):
            self.assertEqual({item['lob'] for item in result if item['owner_id'] == owner},
                             {'auto', 'property'})

    def test_extracts_exact_metadata(self):
        self.assertEqual(extract_metadata(self.text), self.expected)

    def test_rejects_missing_duplicate_and_unknown_labels(self):
        for text in (self.text.replace('owner_id:', 'owner:'),
                     self.text + '\nowner_id: customer_one',
                     self.text.replace(' | owner_id: customer_one', ''),
                     self.text.replace('DOCUMENT REFERENCE', ''),
                     self.text + '\nDOCUMENT REFERENCE\n'):
            with self.subTest(text=text[-100:]), self.assertRaises(ValueError):
                extract_metadata(text)

    def test_rejects_invalid_values_and_owner_assignments(self):
        for field, value in [('owner_id', 'customer_two'), ('policy_id', 'UNKNOWN'),
                             ('lob', 'Auto'), ('product_name', 'Other'),
                             ('version', '0'), ('document_id', '../other'),
                             ('effective_date', '2026-02-30'),
                             ('effective_date', '20260101'), ('owner_id', '')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_metadata({**self.expected, field: value})

    def test_batch_failure_writes_no_sidecars(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy(ROOT / 'documents.json', root)
            for path in ROOT.glob('*.pdf'):
                shutil.copy(path, root)
            documents = json.loads((root / 'documents.json').read_text())
            documents[-1]['metadata']['effective_date'] = '2027-01-01'
            (root / 'documents.json').write_text(json.dumps(documents))
            with self.assertRaisesRegex(ValueError, 'PDF differs'):
                prepare(root)
            self.assertEqual(list(root.glob('*.metadata.json')), [])

    def test_missing_duplicate_extra_documents_and_stale_sidecar(self):
        for failure in ('missing', 'duplicate', 'extra', 'stale'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / 'corpus'
                shutil.copytree(ROOT, root)
                if failure == 'missing':
                    (root / 'auto_user_1_v1.pdf').unlink()
                elif failure == 'duplicate':
                    documents = json.loads((root / 'documents.json').read_text())
                    documents.append(documents[0])
                    (root / 'documents.json').write_text(json.dumps(documents))
                elif failure == 'extra':
                    shutil.copy(root / 'auto_user_1_v1.pdf', root / 'unexpected.pdf')
                else:
                    (root / 'auto_user_1_v1.pdf.metadata.json').write_text('{}')
                with self.assertRaises(ValueError):
                    prepare(root, check=True)
