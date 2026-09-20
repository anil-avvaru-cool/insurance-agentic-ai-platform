"""Deterministic metadata extraction from the POC's parsed document text."""

from datetime import date
import re

FIELDS = ('document_id', 'owner_id', 'policy_id', 'product_name', 'lob',
          'version', 'effective_date')
# Trusted POC identity mapping, independent of document-supplied metadata.
POLICIES = {
    'POC_AUTO_001': ('customer_one', 'auto', 'Standard Auto'),
    'POC_AUTO_002': ('customer_two', 'auto', 'Standard Auto'),
    'POC_PROPERTY_001': ('customer_one', 'property', 'Standard Property'),
    'POC_PROPERTY_002': ('customer_two', 'property', 'Standard Property'),
}


def validate_metadata(metadata):
    """Reject incomplete, malformed, or incorrectly assigned POC metadata."""
    if set(metadata) != set(FIELDS):
        raise ValueError('metadata must contain exactly: ' + ', '.join(FIELDS))
    for key, value in metadata.items():
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ValueError(f'{key}: expected a nonempty, trimmed string')
    for key in ('document_id', 'owner_id', 'policy_id'):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', metadata[key]):
            raise ValueError(f'{key}: invalid identifier')
    if metadata['lob'] not in ('auto', 'property'):
        raise ValueError('lob: expected auto or property')
    if not re.fullmatch(r'[1-9][0-9]*', metadata['version']):
        raise ValueError('version: expected a positive integer string')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', metadata['effective_date']):
        raise ValueError('effective_date: expected YYYY-MM-DD')
    try:
        date.fromisoformat(metadata['effective_date'])
    except ValueError as error:
        raise ValueError('effective_date: invalid calendar date') from error
    expected = POLICIES.get(metadata['policy_id'])
    if expected != tuple(metadata[key] for key in ('owner_id', 'lob', 'product_name')):
        raise ValueError('policy_id: unknown policy or incorrect owner/LOB/product mapping')


def extract_metadata(text):
    """Read exact labels in a single DOCUMENT REFERENCE block; no PDF or LLM I/O."""
    blocks = re.split(r'(?m)^DOCUMENT REFERENCE\s*$', text)
    if len(blocks) != 2:
        raise ValueError('expected exactly one DOCUMENT REFERENCE block')
    metadata = {}
    for token in re.split(r'[|\n]', blocks[1].strip()):
        if not token.strip():
            continue
        key, separator, value = token.strip().partition(':')
        if not separator or key not in FIELDS:
            raise ValueError(f'unrecognized metadata label: {key}')
        if key in metadata:
            raise ValueError(f'duplicate metadata label: {key}')
        metadata[key] = value.strip()
    validate_metadata(metadata)
    return metadata
