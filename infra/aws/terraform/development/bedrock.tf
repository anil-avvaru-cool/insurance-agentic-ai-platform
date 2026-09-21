variable "bedrock_model_id" {
  description = "Regional on-demand Converse model ID; inference profiles require different IAM configuration."
  type        = string
  default     = "amazon.nova-lite-v1:0"
  validation {
    condition     = can(regex("^[a-z0-9]+\\.[A-Za-z0-9.:-]+$", var.bedrock_model_id)) && !can(regex("^(us|eu|apac|global)\\.", var.bedrock_model_id))
    error_message = "Use a regional foundation model ID, not an inference profile or ARN."
  }
}
locals {
  embedding_model_id  = "amazon.titan-embed-text-v2:0"
  embedding_dimension = 1024
  model_arn           = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}"
  embedding_model_arn = "arn:aws:bedrock:${var.aws_region}::foundation-model/${local.embedding_model_id}"
}
resource "aws_s3_bucket" "knowledge" {
  bucket        = "${local.aws_name}${var.aws_account_id}knowledge"
  force_destroy = false
}
resource "aws_s3_bucket_public_access_block" "knowledge" {
  bucket                  = aws_s3_bucket.knowledge.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_ownership_controls" "knowledge" {
  bucket = aws_s3_bucket.knowledge.id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_versioning" "knowledge" {
  bucket = aws_s3_bucket.knowledge.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "knowledge" {
  bucket = aws_s3_bucket.knowledge.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_policy" "knowledge" {
  bucket = aws_s3_bucket.knowledge.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Deny", Principal = "*", Action = "s3:*",
    Resource  = [aws_s3_bucket.knowledge.arn, "${aws_s3_bucket.knowledge.arn}/*"],
    Condition = { Bool = { "aws:SecureTransport" = "false" } }
  }] })
}
resource "aws_s3vectors_vector_bucket" "knowledge" {
  vector_bucket_name = "${local.aws_name}vectors"
  force_destroy      = false
  encryption_configuration { sse_type = "AES256" }
}
resource "aws_s3vectors_index" "knowledge" {
  index_name         = "serviceknowledge"
  vector_bucket_name = aws_s3vectors_vector_bucket.knowledge.vector_bucket_name
  data_type          = "float32"
  dimension          = local.embedding_dimension
  distance_metric    = "cosine"
  metadata_configuration {
    non_filterable_metadata_keys = ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
  }
}
resource "aws_iam_role" "knowledge" {
  name = "${local.name}_knowledge"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "bedrock.amazonaws.com" },
    Condition = {
      StringEquals = { "aws:SourceAccount" = var.aws_account_id },
      ArnLike      = { "aws:SourceArn" = "arn:aws:bedrock:${var.aws_region}:${var.aws_account_id}:knowledge-base/*" }
    }
  }] })
}
resource "aws_iam_role_policy" "knowledge" {
  name = "knowledge_ingestion"
  role = aws_iam_role.knowledge.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = [local.embedding_model_arn] },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = [aws_s3_bucket.knowledge.arn],
    Condition = { StringLike = { "s3:prefix" = [var.knowledge_poc_prefix, "${var.knowledge_poc_prefix}*"] } } },
    { Effect = "Allow", Action = ["s3:GetObject"], Resource = ["${aws_s3_bucket.knowledge.arn}/${var.knowledge_poc_prefix}*"] },
    { Effect = "Allow", Action = ["s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:DeleteVectors", "s3vectors:QueryVectors", "s3vectors:GetIndex"], Resource = [aws_s3vectors_index.knowledge.index_arn] }
  ] })
}
resource "aws_bedrockagent_knowledge_base" "service" {
  name     = "${local.name}_service"
  role_arn = aws_iam_role.knowledge.arn
  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = local.embedding_model_arn
      embedding_model_configuration {
        bedrock_embedding_model_configuration {
          dimensions          = local.embedding_dimension
          embedding_data_type = "FLOAT32"
        }
      }
    }
  }
  storage_configuration {
    type = "S3_VECTORS"
    s3_vectors_configuration { index_arn = aws_s3vectors_index.knowledge.index_arn }
  }
  depends_on = [aws_iam_role_policy.knowledge, aws_s3_bucket_policy.knowledge, aws_s3_bucket_public_access_block.knowledge, aws_s3_bucket_server_side_encryption_configuration.knowledge]
}
resource "aws_bedrockagent_data_source" "service" {
  name                 = "approved_service_documents"
  knowledge_base_id    = aws_bedrockagent_knowledge_base.service.id
  data_deletion_policy = "DELETE"
  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn         = aws_s3_bucket.knowledge.arn
      inclusion_prefixes = [var.knowledge_poc_prefix]
    }
  }
  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"
      fixed_size_chunking_configuration {
        max_tokens         = 300
        overlap_percentage = 15
      }
    }
  }
}
