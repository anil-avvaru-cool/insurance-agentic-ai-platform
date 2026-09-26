output "bedrock" {
  value = {
    rag_answer_model_id = var.bedrock_rag_answer_model_id
    embedding_model_id  = var.bedrock_embedding_model_id
    knowledge_bucket    = aws_s3_bucket.knowledge.id
    knowledge_base_id   = aws_bedrockagent_knowledge_base.service.id
    data_source_id      = aws_bedrockagent_data_source.service.data_source_id
    vector_index_arn    = aws_s3vectors_index.knowledge.index_arn
  }
}
output "query_endpoint" {
  value = var.enable_query_api ? "${aws_api_gateway_stage.query[0].invoke_url}/query" : null
}
