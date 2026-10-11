moved {
  from = aws_s3_bucket.knowledge[0]
  to   = aws_s3_bucket.knowledge
}

moved {
  from = aws_s3_bucket_public_access_block.knowledge[0]
  to   = aws_s3_bucket_public_access_block.knowledge
}

moved {
  from = aws_s3_bucket_ownership_controls.knowledge[0]
  to   = aws_s3_bucket_ownership_controls.knowledge
}

moved {
  from = aws_s3_bucket_versioning.knowledge[0]
  to   = aws_s3_bucket_versioning.knowledge
}

moved {
  from = aws_s3_bucket_server_side_encryption_configuration.knowledge[0]
  to   = aws_s3_bucket_server_side_encryption_configuration.knowledge
}

moved {
  from = aws_s3_bucket_policy.knowledge[0]
  to   = aws_s3_bucket_policy.knowledge
}

moved {
  from = aws_s3vectors_vector_bucket.knowledge[0]
  to   = aws_s3vectors_vector_bucket.knowledge
}

moved {
  from = aws_s3vectors_index.knowledge[0]
  to   = aws_s3vectors_index.knowledge
}

moved {
  from = aws_iam_role.knowledge[0]
  to   = aws_iam_role.knowledge
}

moved {
  from = aws_iam_role_policy.knowledge[0]
  to   = aws_iam_role_policy.knowledge
}

moved {
  from = aws_bedrockagent_knowledge_base.service[0]
  to   = aws_bedrockagent_knowledge_base.service
}

moved {
  from = aws_bedrockagent_data_source.service[0]
  to   = aws_bedrockagent_data_source.service
}
