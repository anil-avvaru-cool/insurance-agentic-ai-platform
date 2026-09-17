resource "aws_ecr_repository" "agentcore" {
  count                = var.enable_bedrock ? 1 : 0
  name                 = "${local.name}_agentcore"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  encryption_configuration { encryption_type = "AES256" }
  image_scanning_configuration { scan_on_push = true }
}
resource "aws_iam_role" "agentcore" {
  count = var.enable_bedrock ? 1 : 0
  name  = "${local.name}_agentcore"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "bedrock-agentcore.amazonaws.com" },
    Condition = {
      StringEquals = { "aws:SourceAccount" = var.aws_account_id },
      ArnLike      = { "aws:SourceArn" = "arn:aws:bedrock-agentcore:${var.aws_region}:${var.aws_account_id}:*" }
    }
  }] })
}
resource "aws_iam_role_policy" "agentcore" {
  count = var.enable_bedrock ? 1 : 0
  name  = "model_runtime"
  role  = aws_iam_role.agentcore[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"], Resource = aws_ecr_repository.agentcore[0].arn },
    { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = local.model_arn },
    { Effect = "Allow", Action = ["bedrock:Retrieve"], Resource = aws_bedrockagent_knowledge_base.service[0].arn },
    { Effect = "Allow", Action = ["logs:CreateLogGroup", "logs:DescribeLogStreams", "logs:CreateLogStream", "logs:PutLogEvents"],
    Resource = "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/bedrock-agentcore/runtimes/${local.name}_agent*" },
    { Effect = "Allow", Action = ["logs:DescribeLogGroups"], Resource = "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:*" }
  ] })
}
resource "aws_bedrockagentcore_agent_runtime" "service" {
  count              = var.enable_agentcore_runtime ? 1 : 0
  agent_runtime_name = "${local.name}_agent"
  role_arn           = try(aws_iam_role.agentcore[0].arn, "")
  description        = "Development model and retrieval smoke runtime; no claims actions"
  agent_runtime_artifact {
    container_configuration {
      container_uri = "${try(aws_ecr_repository.agentcore[0].repository_url, "")}@${var.agentcore_image_digest}"
    }
  }
  # PUBLIC is managed outbound networking. Inbound invocation still requires IAM.
  # This smoke runtime has no database or private application connectivity.
  network_configuration { network_mode = "PUBLIC" }
  protocol_configuration { server_protocol = "HTTP" }
  environment_variables = {
    AWS_REGION                = var.aws_region
    BEDROCK_MODEL_ID          = var.bedrock_model_id
    BEDROCK_KNOWLEDGE_BASE_ID = try(aws_bedrockagent_knowledge_base.service[0].id, "")
    MODEL_MAX_TOKENS          = "512"
    MODEL_TEMPERATURE         = "0"
    KNOWLEDGE_RESULT_COUNT    = "3"
  }
  lifecycle {
    precondition {
      condition     = var.enable_bedrock && var.agentcore_image_digest != ""
      error_message = "Enable Bedrock and publish an ARM64 image before enabling the runtime."
    }
  }
  depends_on = [aws_iam_role_policy.agentcore]
}
resource "aws_iam_role_policy" "worker_agentcore" {
  count = var.enable_agentcore_runtime ? 1 : 0
  name  = "invoke_agentcore"
  role  = aws_iam_role.service["worker"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect   = "Allow", Action = ["bedrock-agentcore:InvokeAgentRuntime"],
    Resource = [aws_bedrockagentcore_agent_runtime.service[0].agent_runtime_arn, "${aws_bedrockagentcore_agent_runtime.service[0].agent_runtime_arn}/runtime-endpoint/DEFAULT"]
  }] })
}
output "bedrock" {
  value = var.enable_bedrock ? {
    model_id              = var.bedrock_model_id
    embedding_model_id    = local.embedding_model_id
    knowledge_bucket      = aws_s3_bucket.knowledge[0].id
    knowledge_base_id     = aws_bedrockagent_knowledge_base.service[0].id
    data_source_id        = aws_bedrockagent_data_source.service[0].data_source_id
    vector_index_arn      = aws_s3vectors_index.knowledge[0].index_arn
    ecr_repository_url    = aws_ecr_repository.agentcore[0].repository_url
    agentcore_role_arn    = aws_iam_role.agentcore[0].arn
    agentcore_runtime_arn = try(aws_bedrockagentcore_agent_runtime.service[0].agent_runtime_arn, null)
  } : null
}
