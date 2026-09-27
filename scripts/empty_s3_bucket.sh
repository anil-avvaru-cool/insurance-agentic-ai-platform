#!/usr/bin/env bash
# Permanently delete every object version and delete marker in one S3 bucket.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash scripts/empty_s3_bucket.sh BUCKET EXPECTED_ACCOUNT_ID [--profile PROFILE] [--region REGION]

Permanently empties the bucket, including all versions and delete markers.
Leaves the bucket itself for Terraform to delete. Stop writers before running.
Requires AWS CLI and jq. Uses your configured AWS credentials by default.
EOF
}

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  usage
  exit 0
fi
if (( $# < 2 )); then
  usage >&2
  exit 1
fi

bucket=$1
owner=$2
shift 2
if [[ -z $bucket || ! $owner =~ ^[0-9]{12}$ ]]; then
  echo 'Provide a bucket name and a 12-digit expected AWS account ID.' >&2
  exit 1
fi

aws_options=(--no-cli-pager --output json)
while (( $# )); do
  case $1 in
    --profile|--region)
      if (( $# < 2 )) || [[ -z $2 || $2 == --* ]]; then
        printf 'Missing value for %s\n' "$1" >&2
        exit 1
      fi
      aws_options+=("$1" "$2")
      shift 2
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

for dependency in aws jq; do
  if ! command -v "$dependency" >/dev/null 2>&1; then
    printf 'Required command not found: %s\n' "$dependency" >&2
    exit 1
  fi
done

payload_file=$(mktemp)
trap 'rm -f "$payload_file"' EXIT
total=0
printf 'Permanently emptying s3://%s (expected owner: %s)\n' "$bucket" "$owner"

while true; do
  # Re-read the first page after each deletion to handle any number of versions.
  aws "${aws_options[@]}" s3api list-object-versions \
    --bucket "$bucket" \
    --expected-bucket-owner "$owner" \
    --max-keys 1000 --no-paginate |
    jq '{Objects: [(.Versions // [])[], (.DeleteMarkers // [])[] |
        {Key, VersionId}], Quiet: true}' > "$payload_file"

  count=$(jq '.Objects | length' "$payload_file")
  if (( count == 0 )); then
    printf 'Bucket is empty. Deleted %s versions/delete markers.\n' "$total"
    break
  fi

  result=$(aws "${aws_options[@]}" s3api delete-objects \
    --bucket "$bucket" \
    --expected-bucket-owner "$owner" \
    --delete "file://$payload_file")

  if jq -e '(.Errors // []) | length > 0' <<< "$result" >/dev/null; then
    echo 'Some deletions failed; stopping. AWS errors:' >&2
    jq '.Errors' <<< "$result" >&2
    exit 1
  fi
  total=$((total + count))
  printf 'Deleted %s entries (%s total).\n' "$count" "$total"
done
