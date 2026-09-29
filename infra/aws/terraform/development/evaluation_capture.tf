variable "enable_evaluation_capture" {
  description = "Allow the approved query operator to request exact evidence capture. No judge jobs are submitted."
  type        = bool
  default     = false
}
variable "evaluation_capture_retention_days" {
  type    = number
  default = 30
  validation {
    condition     = var.evaluation_capture_retention_days >= 1 && floor(var.evaluation_capture_retention_days) == var.evaluation_capture_retention_days
    error_message = "Capture retention must be a positive number of whole days."
  }
}
variable "query_max_passage_chars" {
  type    = number
  default = 6000
  validation {
    condition     = var.query_max_passage_chars >= 1 && var.query_max_passage_chars <= 100000 && floor(var.query_max_passage_chars) == var.query_max_passage_chars
    error_message = "Use an integer passage character limit of 1..100000."
  }
}
variable "query_max_context_chars" {
  type    = number
  default = 24000
  validation {
    condition     = var.query_max_context_chars >= 1 && var.query_max_context_chars <= 100000 && floor(var.query_max_context_chars) == var.query_max_context_chars
    error_message = "Use an integer context character limit of 1..100000."
  }
}
locals {
  capture_count  = var.enable_evaluation_capture && var.enable_query_api ? 1 : 0
  capture_prefix = "captures/"
}
resource "aws_s3_bucket" "evaluation_capture" {
  count         = local.capture_count
  bucket        = "${local.aws_name}${var.aws_account_id}evaluation"
  force_destroy = false
}
resource "aws_s3_bucket_public_access_block" "evaluation_capture" {
  count                   = local.capture_count
  bucket                  = aws_s3_bucket.evaluation_capture[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_ownership_controls" "evaluation_capture" {
  count  = local.capture_count
  bucket = aws_s3_bucket.evaluation_capture[0].id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "evaluation_capture" {
  count  = local.capture_count
  bucket = aws_s3_bucket.evaluation_capture[0].id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_lifecycle_configuration" "evaluation_capture" {
  count  = local.capture_count
  bucket = aws_s3_bucket.evaluation_capture[0].id
  rule {
    id     = "capture_retention"
    status = "Enabled"
    filter { prefix = local.capture_prefix }
    expiration { days = var.evaluation_capture_retention_days }
  }
}
resource "aws_s3_bucket_policy" "evaluation_capture" {
  count  = local.capture_count
  bucket = aws_s3_bucket.evaluation_capture[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect    = "Deny", Principal = "*", Action = "s3:*",
      Resource  = [aws_s3_bucket.evaluation_capture[0].arn, "${aws_s3_bucket.evaluation_capture[0].arn}/*"],
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    },
    { Effect    = "Allow", Principal = "*", Action = "s3:GetObject",
      Resource  = "${aws_s3_bucket.evaluation_capture[0].arn}/${local.capture_prefix}*",
      Condition = { ArnEquals = { "aws:PrincipalArn" = var.query_operator_arn } }
    }
  ] })
}
resource "aws_iam_role_policy" "evaluation_capture" {
  count = local.capture_count
  name  = "evaluation_capture"
  role  = aws_iam_role.query[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect   = "Allow", Action = ["s3:PutObject"],
    Resource = ["${aws_s3_bucket.evaluation_capture[0].arn}/${local.capture_prefix}*"]
  }] })
}
output "evaluation_capture_environment" {
  value = local.capture_count == 0 ? {} : {
    QUERY_CAPTURE_BUCKET = aws_s3_bucket.evaluation_capture[0].id
    QUERY_CAPTURE_PREFIX = local.capture_prefix
  }
}
