"""Opt-in live evaluation using synthetic messages; exits nonzero on any failure."""
import json
import os
from pathlib import Path
import time

from apps.config import configured_language
from insurance_domain.catalogs import Catalogs
from insurance_domain.intake import DomainError


def main():
    if os.environ['LLM_PROVIDER'] != 'bedrock':
        raise SystemExit('LLM_PROVIDER=bedrock is required; no evaluation was run.')
    adapter = configured_language()
    catalogs = Catalogs(os.environ['CATALOGS_PATH'])
    cases = json.loads(Path('tests/fixtures/language_cases.json').read_text())
    results = []
    for case in cases:
        started = time.monotonic()
        try:
            output, metadata = adapter.interpret(case['text'], catalogs.sources())
            facts = {fact.name: fact.value for fact in output.facts}
            passed = (output.intent == case['intent'] and
                      all(facts.get(k) == v for k, v in case['facts'].items()) and
                      all(k in case['facts'] or k == 'description' for k in facts) and
                      output.object_ref == case.get('object_ref') and
                      output.source_ref == case.get('source_ref'))
            results.append({'id': case['id'], 'passed': passed, 'metadata': metadata,
                            'seconds': round(time.monotonic() - started, 3)})
        except DomainError:
            results.append({'id': case['id'], 'passed': False, 'error': 'language_unavailable'})
    print(json.dumps({'catalog_version': catalogs.data['version'], 'results': results,
                      'passed': sum(r['passed'] for r in results), 'total': len(results)}, indent=2))
    return 0 if all(r['passed'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
