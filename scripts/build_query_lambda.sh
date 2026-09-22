#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_file="${repo_root}/lambda/query.py"
artifact_dir="${repo_root}/build/lambda"
artifact="${artifact_dir}/query.zip"

mkdir -p "${artifact_dir}"
python3 -m py_compile "${source_file}"
python3 -c 'import sys, zipfile
source, artifact = sys.argv[1:]
with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    archive.write(source, "query.py")
' "${source_file}" "${artifact}"
echo "${artifact}"
