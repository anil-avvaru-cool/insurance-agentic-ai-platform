mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
}
variables {
  aws_region                = "us-east-1"
  aws_account_id            = "123456789012"
  project_name              = "insurance"
  environment               = "development"
  owner                     = "test"
  postgres_engine_version   = "16.6"
  postgres_parameter_family = "postgres16"
  db_instance_class         = "db.t4g.micro"
  db_allocated_storage_gib  = 20
  db_deletion_protection    = true
  final_snapshot_identifier = "insurancetestfinal"
}
override_data {
  target = data.aws_availability_zones.available
  values = { names = ["us-east-1a", "us-east-1b"] }
}
run "private_foundation" {
  command = plan
  assert {
    condition     = aws_vpc.development.enable_dns_support && aws_vpc.development.enable_dns_hostnames && length(aws_subnet.private) == 2 && aws_subnet.private[0].availability_zone != aws_subnet.private[1].availability_zone && alltrue([for subnet in aws_subnet.private : !subnet.map_public_ip_on_launch]) && length(aws_route_table_association.private) == 2
    error_message = "Create two private subnets in separate AZs with no internet route."
  }
  assert {
    condition     = !aws_db_instance.checkpoint.publicly_accessible && aws_db_instance.checkpoint.storage_encrypted && aws_db_instance.checkpoint.manage_master_user_password && aws_db_instance.checkpoint.deletion_protection && !aws_db_instance.checkpoint.skip_final_snapshot
    error_message = "Checkpoint storage must be private, encrypted, password managed and recoverable."
  }
  assert {
    condition     = aws_sqs_queue.tasks.sqs_managed_sse_enabled && aws_sqs_queue.dead_letter.message_retention_seconds > aws_sqs_queue.tasks.message_retention_seconds
    error_message = "Queues must be encrypted and dead letters retained longer than tasks."
  }
  assert {
    condition     = length(aws_iam_role.service) == 3 && aws_iam_role.service["api"].name != aws_iam_role.service["worker"].name
    error_message = "API, worker and action identities must be separate."
  }
}
run "bedrock_foundation" {
  command = plan
  assert {
    condition     = aws_s3vectors_index.knowledge.dimension == aws_bedrockagent_knowledge_base.service.knowledge_base_configuration[0].vector_knowledge_base_configuration[0].embedding_model_configuration[0].bedrock_embedding_model_configuration[0].dimensions && contains(aws_s3vectors_index.knowledge.metadata_configuration[0].non_filterable_metadata_keys, "AMAZON_BEDROCK_TEXT")
    error_message = "Embedding dimensions must match and document text must be non-filterable."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.knowledge.block_public_policy && aws_s3_bucket_public_access_block.knowledge.restrict_public_buckets && !aws_s3_bucket.knowledge.force_destroy && aws_s3_bucket_versioning.knowledge.versioning_configuration[0].status == "Enabled"
    error_message = "Knowledge documents must be private and recoverable."
  }
  assert {
    condition     = aws_bedrockagent_data_source.service.data_source_configuration[0].s3_configuration[0].inclusion_prefixes == toset(["approved/"]) && aws_ecr_repository.agentcore.image_tag_mutability == "IMMUTABLE"
    error_message = "Ingestion must use the approved prefix; initial deployment must wait for an immutable image."
  }
}
