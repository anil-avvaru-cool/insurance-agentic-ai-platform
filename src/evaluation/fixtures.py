"""Offline validation of the reviewed policy questions and six-case baseline."""

import hashlib
import json
from pathlib import Path
import re

from ingestion.corpus import prepare
from ingestion.pdf import parse_pdf


INSUFFICIENT = "The selected policy document does not provide this information."


def validate_baseline(corpus: Path, questions: Path, manifest: Path) -> dict:
    prepare(corpus, check=True)
    documents = {d['metadata']['document_id']: d for d in json.loads((corpus / 'documents.json').read_text())}
    cases = json.loads(questions.read_text())
    by_id = {c['case_id']: c for c in cases}
    if len(by_id) != len(cases):
        raise ValueError('duplicate question IDs')
    normalize = lambda text: ' '.join(text.split())
    pdf_text = {key: normalize(parse_pdf(corpus / f'{key}.pdf')) for key in documents}
    for case in cases:
        allowed = case['allowed_document_ids']
        if not allowed or len(allowed) != len(set(allowed)):
            raise ValueError('missing or duplicate allowed document IDs')
        for key in allowed:
            if key not in documents:
                raise ValueError(f"{case['case_id']}: obsolete or unknown document {key}")
            metadata = documents[key]['metadata']
            if any(metadata[field] != case[field] for field in ('owner_id', 'lob')):
                raise ValueError('fixture owner/LOB mismatch')
        for passage in case['supporting_passages']:
            key = passage['document_id']
            if key not in allowed:
                raise ValueError('passage outside allowed documents')
            source = {p['id']: p['text'] for p in documents[key]['passages']}
            if source.get(passage['passage_id']) != passage['text'] or normalize(passage['text']) not in pdf_text[key]:
                raise ValueError(f"{case['case_id']}: supporting passage differs from source/PDF")
        if case['expected_status'] == 'supported':
            if not case['supporting_passages']:
                raise ValueError('supported case needs evidence')
            amounts = lambda text: set(re.findall(r'\$[\d,]+', text))
            if not amounts(case['expected_answer']) <= amounts(' '.join(p['text'] for p in case['supporting_passages'])):
                raise ValueError('expected amount absent from supporting passages')
        elif case['expected_status'] != 'insufficient_information' or case['expected_answer'] != INSUFFICIENT or case['supporting_passages']:
            raise ValueError('invalid insufficient-information reference')
    baseline = json.loads(manifest.read_text())
    ids = baseline['case_ids']
    if baseline['schema_version'] != 1 or len(ids) != 6 or len(set(ids)) != 6 or any(key not in by_id for key in ids):
        raise ValueError('baseline must select exactly six unique existing cases')
    selected = [by_id[key] for key in ids]
    expected = [('customer_one', 'auto', 'supported'), ('customer_two', 'auto', 'supported'),
                ('customer_one', 'property', 'supported'), ('customer_two', 'property', 'supported'),
                ('customer_one', 'auto', 'insufficient_information'), ('customer_one', 'auto', 'insufficient_information')]
    if [(c['owner_id'], c['lob'], c['expected_status']) for c in selected] != expected:
        raise ValueError('baseline does not match the six Phase 1 scenarios')
    if selected[0]['question'] != selected[1]['question'] or selected[0]['expected_answer'] == selected[1]['expected_answer']:
        raise ValueError('paired deductible questions must match and answers must differ')
    if 'customer_two' not in selected[5]['question']:
        raise ValueError('last scenario must request the other owner')
    files = [questions, manifest, corpus / 'documents.json', *sorted(corpus.glob('*.pdf')), *sorted(corpus.glob('*.metadata.json'))]
    return {'case_ids': ids, 'validated_questions': len(cases),
            'sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}}
