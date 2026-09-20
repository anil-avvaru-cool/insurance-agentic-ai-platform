resource "aws_bedrockagentcore_agent_runtime" "service" {
  agent_runtime_name = "${local.name}_agent"
  role_arn           = var.infrastructure.agentcore_role_arn
  description        = "Development model and retrieval smoke runtime; no claims actions"
  agent_runtime_artifact {
    container_configuration {
      container_uri = "${var.infrastructure.ecr_repository_url}@${var.agentcore_image_digest}"
    }
  }
  # PUBLIC is managed outbound networking. Inbound invocation still requires IAM.
  # This smoke runtime has no database or private application connectivity.
  network_configuration { network_mode = "PUBLIC" }
  protocol_configuration { server_protocol = "HTTP" }
  environment_variables = {
    AWS_REGION                = var.infrastructure.aws_region
    BEDROCK_MODEL_ID          = var.infrastructure.model_id
    BEDROCK_KNOWLEDGE_BASE_ID = var.infrastructure.knowledge_base_id
    MODEL_MAX_TOKENS          = "512"
    MODEL_TEMPERATURE         = "0"
    KNOWLEDGE_RESULT_COUNT    = "3"
  }
}
resource "aws_iam_role_policy" "worker_agentcore" {
  name = "invoke_agentcore"
  role = var.infrastructure.worker_role_name
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect   = "Allow", Action = ["bedrock-agentcore:InvokeAgentRuntime"],
    Resource = [aws_bedrockagentcore_agent_runtime.service.agent_runtime_arn, "${aws_bedrockagentcore_agent_runtime.service.agent_runtime_arn}/runtime-endpoint/DEFAULT"]
  }] })
}
