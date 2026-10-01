variable "enable_rag_judge" {
  description = "Create optional evaluation storage and IAM only; never submits a paid judge job."
  type        = bool
  default     = false
}
variable "judge_evaluator_model_id" {
  description = "Supported regional foundation model ID for built-in metrics."
  type        = string
  default     = ""
  validation {
    condition     = var.judge_evaluator_model_id == "" || (can(regex("^[a-z0-9]+\\.[A-Za-z0-9.:-]+$", var.judge_evaluator_model_id)) && !can(regex("^(us|eu|apac|global)\\.", var.judge_evaluator_model_id)))
    error_message = "Use a regional foundation model ID; inference profiles need separate IAM configuration."
  }
}
variable "judge_custom_evaluator_model_id" {
  description = "Supported regional foundation model ID for the custom metric."
  type        = string
  default     = ""
  validation {
    condition     = var.judge_custom_evaluator_model_id == "" || (can(regex("^[a-z0-9]+\\.[A-Za-z0-9.:-]+$", var.judge_custom_evaluator_model_id)) && !can(regex("^(us|eu|apac|global)\\.", var.judge_custom_evaluator_model_id)))
    error_message = "Use a regional foundation model ID; inference profiles need separate IAM configuration."
  }
}
variable "judge_operator_role_name" {
  description = "Existing operator role to attach evaluation permissions to; null exports a policy for manual attachment."
  type        = string
  default     = null
}
locals {
  judge_count         = var.enable_rag_judge ? 1 : 0
  judge_input_prefix  = "datasets/"
  judge_output_prefix = "results/"
  judge_job_arn       = "arn:aws:bedrock:${var.aws_region}:${var.aws_account_id}:evaluation-job/*"
  judge_model_arns    = distinct([for id in [var.judge_evaluator_model_id, var.judge_custom_evaluator_model_id] : "arn:aws:bedrock:${var.aws_region}::foundation-model/${id}"])
}
resource "aws_s3_bucket" "rag_judge" {
  count         = local.judge_count
  bucket        = "${local.aws_name}${var.aws_account_id}judge"
  force_destroy = false
}
resource "aws_s3_bucket_public_access_block" "rag_judge" {
  count                   = local.judge_count
  bucket                  = aws_s3_bucket.rag_judge[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_ownership_controls" "rag_judge" {
  count  = local.judge_count
  bucket = aws_s3_bucket.rag_judge[0].id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "rag_judge" {
  count  = local.judge_count
  bucket = aws_s3_bucket.rag_judge[0].id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_policy" "rag_judge" {
  count  = local.judge_count
  bucket = aws_s3_bucket.rag_judge[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Deny", Principal = "*", Action = "s3:*",
    Resource  = [aws_s3_bucket.rag_judge[0].arn, "${aws_s3_bucket.rag_judge[0].arn}/*"],
    Condition = { Bool = { "aws:SecureTransport" = "false" } }
  }] })
}
resource "aws_iam_role" "rag_judge" {
  count = local.judge_count
  name  = "${local.name}_rag_judge"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "bedrock.amazonaws.com" },
    Condition = {
      StringEquals = { "aws:SourceAccount" = var.aws_account_id },
      ArnLike      = { "aws:SourceArn" = local.judge_job_arn }
    }
  }] })
  lifecycle {
    precondition {
      condition     = var.judge_evaluator_model_id != "" && var.judge_custom_evaluator_model_id != ""
      error_message = "Set both supported evaluator model IDs before enabling the judge."
    }
  }
}
resource "aws_iam_role_policy" "rag_judge" {
  count = local.judge_count
  name  = "rag_judge"
  role  = aws_iam_role.rag_judge[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:GetBucketLocation"], Resource = [aws_s3_bucket.rag_judge[0].arn] },
    { Effect = "Allow", Action = ["s3:ListBucket", "s3:ListBucketMultipartUploads"], Resource = [aws_s3_bucket.rag_judge[0].arn],
    Condition = { StringLike = { "s3:prefix" = ["${local.judge_input_prefix}*", "${local.judge_output_prefix}*"] } } },
    { Effect = "Allow", Action = ["s3:GetObject"], Resource = ["${aws_s3_bucket.rag_judge[0].arn}/${local.judge_input_prefix}*"] },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload"], Resource = ["${aws_s3_bucket.rag_judge[0].arn}/${local.judge_output_prefix}*"] },
    { Effect = "Allow", Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"], Resource = local.judge_model_arns },
    { Effect = "Allow", Action = ["bedrock:CreateModelInvocationJob"], Resource = concat(local.judge_model_arns, ["arn:aws:bedrock:${var.aws_region}:${var.aws_account_id}:model-invocation-job/*"]) },
    { Effect = "Allow", Action = ["bedrock:StopModelInvocationJob"], Resource = ["arn:aws:bedrock:${var.aws_region}:${var.aws_account_id}:model-invocation-job/*"] }
  ] })
}
resource "aws_iam_policy" "rag_judge_operator" {
  count = local.judge_count
  name  = "${local.name}_rag_judge_operator"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["bedrock:CreateEvaluationJob"], Resource = local.judge_model_arns },
    { Effect = "Allow", Action = ["bedrock:GetEvaluationJob"], Resource = [local.judge_job_arn] },
    { Effect = "Allow", Action = ["iam:PassRole"], Resource = [aws_iam_role.rag_judge[0].arn],
    Condition = { StringEquals = { "iam:PassedToService" = "bedrock.amazonaws.com" } } },
    { Effect = "Allow", Action = ["s3:GetBucketLocation"], Resource = [aws_s3_bucket.rag_judge[0].arn] },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = [aws_s3_bucket.rag_judge[0].arn],
    Condition = { StringLike = { "s3:prefix" = ["${local.judge_input_prefix}*", "${local.judge_output_prefix}*"] } } },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = ["${aws_s3_bucket.rag_judge[0].arn}/${local.judge_input_prefix}*"] },
    { Effect = "Allow", Action = ["s3:GetObject"], Resource = ["${aws_s3_bucket.rag_judge[0].arn}/${local.judge_output_prefix}*"] }
  ] })
}
resource "aws_iam_role_policy_attachment" "rag_judge_operator" {
  count      = var.enable_rag_judge && var.judge_operator_role_name != null ? 1 : 0
  role       = var.judge_operator_role_name
  policy_arn = aws_iam_policy.rag_judge_operator[0].arn
}
output "rag_judge_operator_policy_arn" {
  value = var.enable_rag_judge ? aws_iam_policy.rag_judge_operator[0].arn : null
}
output "rag_judge_environment" {
  value = var.enable_rag_judge ? {
    JUDGE_REGION                    = var.aws_region
    JUDGE_EVALUATOR_MODEL_ID        = var.judge_evaluator_model_id
    JUDGE_CUSTOM_EVALUATOR_MODEL_ID = var.judge_custom_evaluator_model_id
    JUDGE_EVALUATION_ROLE_ARN       = aws_iam_role.rag_judge[0].arn
    JUDGE_RAG_SOURCE_ID             = "insurance_api"
    JUDGE_DATASET_S3_URI            = "s3://${aws_s3_bucket.rag_judge[0].id}/${local.judge_input_prefix}baseline.jsonl"
    JUDGE_OUTPUT_S3_URI             = "s3://${aws_s3_bucket.rag_judge[0].id}/${local.judge_output_prefix}"
  } : {}
}
