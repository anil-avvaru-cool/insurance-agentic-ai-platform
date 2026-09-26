#!/usr/bin/env bash
# Grant backend access to an existing IAM role or user using the current AWS credentials.
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "Usage: bash $0 BUCKET bootstrap|development role|user IDENTITY_NAME" >&2
  echo "Example: AWS_PROFILE=admin bash $0 my-state-bucket development role TerraformDevelopment" >&2
  exit 2
fi

state_bucket=$1
state_root=$2
identity_type=$3
identity_name=$4

if [[ ! $state_bucket =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]]; then
  echo "Provide an S3 bucket name, not an ARN or s3:// URL." >&2
  exit 2
fi
case "$state_root" in
  bootstrap|development) ;;
  *) echo "State root must be bootstrap or development." >&2; exit 2 ;;
esac
case "$identity_type" in
  role|user) ;;
  *) echo "Identity type must be role or user." >&2; exit 2 ;;
esac
if [[ ! $identity_name =~ ^[a-zA-Z0-9_+=,.@-]+$ ]]; then
  echo "Provide an IAM identity name, not an ARN." >&2
  exit 2
fi
if [[ $identity_type == role && $identity_name == AWSReservedSSO_* ]]; then
  echo "For an IAM Identity Center role, update its permission set instead." >&2
  exit 2
fi

state_key="$state_root/terraform.tfstate"
policy_name="TerraformState-$state_bucket-$state_root"
policy_document=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::$state_bucket"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::$state_bucket/$state_key"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::$state_bucket/$state_key.tflock"
    }
  ]
}
EOF
)

AWS_PAGER="" aws iam "put-$identity_type-policy" \
  "--$identity_type-name" "$identity_name" \
  --policy-name "$policy_name" \
  --policy-document "$policy_document"

echo "Applied $policy_name to $identity_type $identity_name."
