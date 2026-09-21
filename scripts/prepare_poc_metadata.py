"""Validate all four policy PDFs before writing Bedrock metadata sidecars."""

import argparse
import json
from pathlib import Path

from ingestion.corpus import ROOT, prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--check', action='store_true', help='verify existing sidecars without writing')
    args = parser.parse_args()
    try:
        metadata = prepare(args.root, args.check)
    except (ValueError, OSError) as error:
        parser.exit(1, f'Metadata validation failed:\n{error}\n')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
