"""Validate all four policy PDFs before writing Bedrock metadata sidecars."""

import json
from pathlib import Path

from ingestion.metadata import POLICIES, extract_metadata, validate_metadata
from ingestion.pdf import parse_pdf

ROOT = Path(__file__).resolve().parents[2] / 'policies' / 'aws_poc'


def prepare(root, check=False):
    documents = json.loads((root / 'documents.json').read_text())
    prepared = {}
    policies = set()
    errors = []
    for document in documents:
        try:
            expected = document['metadata']
            validate_metadata(expected)
            document_id = expected['document_id']
            if document_id in prepared or expected['policy_id'] in policies:
                raise ValueError('duplicate document_id or policy_id')
            path = root / f'{document_id}.pdf'
            actual = extract_metadata(parse_pdf(path))
            if actual != expected:
                differences = [key for key in expected if actual[key] != expected[key]]
                raise ValueError('PDF differs from documents.json: ' + ', '.join(differences))
            prepared[document_id] = (path, {'metadataAttributes': actual})
            policies.add(actual['policy_id'])
        except (ValueError, KeyError, OSError) as error:
            errors.append(f"{document.get('metadata', {}).get('document_id', '<unknown>')}: {error}")
    if policies != set(POLICIES):
        errors.append('corpus must contain each of the four expected policies exactly once')
    if {path.stem for path in root.glob('*.pdf')} != set(prepared):
        errors.append('PDF inventory does not match the validated document IDs')
    if errors:
        raise ValueError('\n'.join(errors))
    for path, sidecar in prepared.values():
        target = path.with_name(path.name + '.metadata.json')
        if check:
            if not target.exists() or json.loads(target.read_text()) != sidecar:
                raise ValueError(f'{target.name}: missing or stale sidecar; regenerate metadata')
        else:
            target.write_text(json.dumps(sidecar, indent=2) + '\n')
    return [sidecar['metadataAttributes'] for _, sidecar in prepared.values()]

