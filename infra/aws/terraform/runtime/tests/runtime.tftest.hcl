mock_provider "aws" {}
variables {
  infrastructure = {
    aws_region         = "us-east-1"
    aws_account_id     = "123456789012"
    project_name       = "insurance"
    environment        = "development"
    owner              = "test"
    model_id           = "amazon.nova-lite-v1:0"
    knowledge_base_id  = "TESTKB1234"
    ecr_repository_url = "123456789012.dkr.ecr.us-east-1.amazonaws.com/insurance_development_agentcore"
    agentcore_role_arn = "arn:aws:iam::123456789012:role/insurance_development_agentcore"
    worker_role_name   = "insurance_development_worker"
  }
  agentcore_image_digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
run "mandatory_runtime" {
  command = plan
  assert {
    condition     = aws_bedrockagentcore_agent_runtime.service.agent_runtime_artifact[0].container_configuration[0].container_uri == "${var.infrastructure.ecr_repository_url}@${var.agentcore_image_digest}" && aws_bedrockagentcore_agent_runtime.service.environment_variables["BEDROCK_KNOWLEDGE_BASE_ID"] == var.infrastructure.knowledge_base_id
    error_message = "Use the published immutable image and infrastructure knowledge base."
  }
  assert {
    condition     = aws_bedrockagentcore_agent_runtime.service.network_configuration[0].network_mode == "PUBLIC" && aws_bedrockagentcore_agent_runtime.service.protocol_configuration[0].server_protocol == "HTTP" && length(aws_bedrockagentcore_agent_runtime.service.authorizer_configuration) == 0 && aws_iam_role_policy.worker_agentcore.role == var.infrastructure.worker_role_name
    error_message = "Preserve HTTP, default IAM authentication and the infrastructure worker identity."
  }
}
run "reject_missing_image" {
  command = plan
  variables { agentcore_image_digest = "" }
  expect_failures = [var.agentcore_image_digest]
}
run "reject_tag" {
  command = plan
  variables { agentcore_image_digest = "latest" }
  expect_failures = [var.agentcore_image_digest]
}
