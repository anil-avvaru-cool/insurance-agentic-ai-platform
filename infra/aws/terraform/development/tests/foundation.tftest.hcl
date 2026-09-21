mock_provider "aws" {}
variables {
  aws_region     = "us-east-1"
  aws_account_id = "123456789012"
  project_name   = "insurance"
  environment    = "development"
  owner          = "test"
}
run "bedrock_foundation" {
  command = plan
  assert {
    condition     = aws_s3vectors_index.knowledge.dimension == aws_bedrockagent_knowledge_base.service.knowledge_base_configuration[0].vector_knowledge_base_configuration[0].embedding_model_configuration[0].bedrock_embedding_model_configuration[0].dimensions && contains(aws_s3vectors_index.knowledge.metadata_configuration[0].non_filterable_metadata_keys, "AMAZON_BEDROCK_TEXT")
    error_message = "Embedding dimensions must match and document text must be non-filterable."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.knowledge.block_public_policy && aws_s3_bucket_public_access_block.knowledge.restrict_public_buckets && !aws_s3_bucket.knowledge.force_destroy && aws_s3_bucket_versioning.knowledge.versioning_configuration[0].status == "Suspended"
    error_message = "Knowledge documents must be private, protected from forced destruction, and have versioning suspended by default for the POC."
  }
  assert {
    condition     = aws_bedrockagent_data_source.service.data_source_configuration[0].s3_configuration[0].inclusion_prefixes == toset([var.knowledge_poc_prefix])
    error_message = "Ingestion must use only the approved POC prefix."
  }
}
run "knowledge_versioning_enabled" {
  command = plan
  variables {
    knowledge_bucket_versioning_enabled = true
  }
  assert {
    condition     = aws_s3_bucket_versioning.knowledge.versioning_configuration[0].status == "Enabled"
    error_message = "Knowledge bucket versioning must be enabled when explicitly requested."
  }
}
run "poc_ingestion" {
  command = plan
  assert {
    condition     = var.knowledge_poc_prefix == "approved/aws_poc/" && aws_bedrockagent_data_source.service.data_deletion_policy == "DELETE"
    error_message = "POC must use a dedicated prefix and remove embeddings when its data source is deleted."
  }
  assert {
    condition     = aws_bedrockagent_data_source.service.vector_ingestion_configuration[0].chunking_configuration[0].fixed_size_chunking_configuration[0].max_tokens == 300 && aws_bedrockagent_data_source.service.vector_ingestion_configuration[0].chunking_configuration[0].fixed_size_chunking_configuration[0].overlap_percentage == 15
    error_message = "POC chunking must use 300 tokens and 15 percent overlap."
  }
  assert {
    condition     = !contains(aws_s3vectors_index.knowledge.metadata_configuration[0].non_filterable_metadata_keys, "owner_id") && !contains(aws_s3vectors_index.knowledge.metadata_configuration[0].non_filterable_metadata_keys, "lob") && length(local.poc_document_arns) == 8
    error_message = "Owner/LOB must remain filterable and runner uploads must cover only four PDF/sidecar pairs."
  }
  assert {
    condition     = length(aws_iam_role_policy_attachment.ingestion_runner) == 0 && var.knowledge_ingestion_timeout_seconds == 900
    error_message = "Do not guess an operator identity; use a 900-second initial timeout."
  }
}
