variable "knowledge_poc_prefix" {
  description = "Dedicated four-policy inventory; no other objects or automated sync writers."
  type        = string
  default     = "approved/aws_poc/"
  validation {
    condition     = can(regex("^([a-z0-9_]+/){2,}$", var.knowledge_poc_prefix)) && !startswith(var.knowledge_poc_prefix, "ingestion_control/")
    error_message = "Use a nested lowercase underscore prefix ending in / outside ingestion_control/."
  }
}
variable "knowledge_ingestion_timeout_seconds" {
  type    = number
  default = 900
  validation {
    condition     = var.knowledge_ingestion_timeout_seconds > 0 && floor(var.knowledge_ingestion_timeout_seconds) == var.knowledge_ingestion_timeout_seconds
    error_message = "Ingestion timeout must be a positive integer in seconds."
  }
}
variable "ingestion_runner_role_name" {
  description = "Existing operator IAM role to receive POC permissions. Null exports a managed policy for attachment through your identity system."
  type        = string
  default     = null
  nullable    = true
}
locals {
  poc_policy_ids = ["POC_AUTO_001", "POC_AUTO_002", "POC_PROPERTY_001", "POC_PROPERTY_002"]
  poc_document_arns = flatten([for id in local.poc_policy_ids : [
    "${aws_s3_bucket.knowledge.arn}/${var.knowledge_poc_prefix}${id}.pdf",
    "${aws_s3_bucket.knowledge.arn}/${var.knowledge_poc_prefix}${id}.pdf.metadata.json"
  ]])
  ingestion_lock_key = "ingestion_control/${aws_bedrockagent_knowledge_base.service.id}/${aws_bedrockagent_data_source.service.data_source_id}/run_lock.json"
}
resource "aws_iam_policy" "ingestion_runner" {
  name = "${local.name}_ingestion_runner"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:ListBucket", "s3:GetBucketLocation"], Resource = [aws_s3_bucket.knowledge.arn] },
    { Effect = "Allow", Action = ["s3:PutObject"], Resource = local.poc_document_arns },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = ["${aws_s3_bucket.knowledge.arn}/${local.ingestion_lock_key}"] },
    { Effect = "Allow", Action = ["bedrock:GetKnowledgeBase", "bedrock:GetDataSource", "bedrock:ListIngestionJobs", "bedrock:StartIngestionJob", "bedrock:GetIngestionJob"], Resource = [aws_bedrockagent_knowledge_base.service.arn] },
    { Effect = "Allow", Action = ["s3vectors:GetIndex"], Resource = [aws_s3vectors_index.knowledge.index_arn] },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = ["${aws_cloudwatch_log_group.ingestion.arn}:*"] }
  ] })
}
resource "aws_iam_role_policy_attachment" "ingestion_runner" {
  count      = var.ingestion_runner_role_name == null ? 0 : 1
  role       = var.ingestion_runner_role_name
  policy_arn = aws_iam_policy.ingestion_runner.arn
}
output "ingestion_runner_policy_arn" { value = aws_iam_policy.ingestion_runner.arn }
output "ingestion_environment" {
  description = "Non-secret configuration consumed directly by scripts/ingest_poc.py --terraform-dir."
  value = {
    AWS_REGION                          = var.aws_region
    KNOWLEDGE_BUCKET                    = aws_s3_bucket.knowledge.id
    KNOWLEDGE_POC_PREFIX                = var.knowledge_poc_prefix
    BEDROCK_KNOWLEDGE_BASE_ID           = aws_bedrockagent_knowledge_base.service.id
    BEDROCK_DATA_SOURCE_ID              = aws_bedrockagent_data_source.service.data_source_id
    KNOWLEDGE_INGESTION_TIMEOUT_SECONDS = tostring(var.knowledge_ingestion_timeout_seconds)
  }
}
