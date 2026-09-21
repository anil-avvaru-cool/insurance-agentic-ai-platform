output "bedrock" {
  value = {
    model_id           = var.bedrock_model_id
    embedding_model_id = local.embedding_model_id
    knowledge_bucket   = aws_s3_bucket.knowledge.id
    knowledge_base_id  = aws_bedrockagent_knowledge_base.service.id
    data_source_id     = aws_bedrockagent_data_source.service.data_source_id
    vector_index_arn   = aws_s3vectors_index.knowledge.index_arn
  }
}
