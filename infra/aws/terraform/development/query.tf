variable "enable_query_api" {
  type    = bool
  default = false
}
variable "index_validation_passed" {
  description = "Operator attestation that retrieval, source, replacement and owner/LOB isolation checks passed."
  type        = bool
  default     = false
}
variable "query_lambda_zip" {
  description = "Path to the built Python 3.12 x86_64 query ZIP; required when enabling the API."
  type        = string
  default     = ""
}
variable "query_lambda_handler" {
  type    = string
  default = "query.handler"
}
variable "query_operator_arn" {
  description = "Exact IAM principal allowed to invoke this POC (user, role, or root ARN; never an STS session ARN)."
  type        = string
  default     = ""
  validation {
    condition     = var.query_operator_arn == "" || can(regex("^arn:aws:iam::[0-9]{12}:(root|user/[A-Za-z0-9+=,.@_/-]+|role/[A-Za-z0-9+=,.@_/-]+)$", var.query_operator_arn))
    error_message = "Supply an exact IAM user, role or root ARN, without wildcards."
  }
}
variable "query_timeout_seconds" {
  type    = number
  default = 28
  validation {
    condition     = var.query_timeout_seconds >= 5 && var.query_timeout_seconds <= 28 && floor(var.query_timeout_seconds) == var.query_timeout_seconds
    error_message = "Use an integer Lambda timeout of 5..28 seconds, below the 29-second integration timeout."
  }
}
variable "query_max_tokens" {
  type    = number
  default = 512
  validation {
    condition     = var.query_max_tokens >= 1 && var.query_max_tokens <= 4096 && floor(var.query_max_tokens) == var.query_max_tokens
    error_message = "Use an integer output token limit of 1..4096."
  }
}
locals {
  query_count = var.enable_query_api ? 1 : 0
  query_name  = "${local.name}_query"
}
resource "aws_iam_role" "query" {
  count = local.query_count
  name  = local.query_name
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "lambda.amazonaws.com" }
  }] })
}
resource "aws_iam_role_policy" "query" {
  count = local.query_count
  name  = "query"
  role  = aws_iam_role.query[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["bedrock:Retrieve"], Resource = [aws_bedrockagent_knowledge_base.service.arn] },
    { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = [local.rag_answer_model_arn] },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = ["${aws_cloudwatch_log_group.query[0].arn}:*"] }
  ] })
}
resource "aws_lambda_function" "query" {
  count            = local.query_count
  function_name    = local.query_name
  role             = aws_iam_role.query[0].arn
  filename         = var.query_lambda_zip
  source_code_hash = try(filebase64sha256(var.query_lambda_zip), null)
  handler          = var.query_lambda_handler
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  memory_size      = 512
  timeout          = var.query_timeout_seconds
  environment {
    variables = {
      BEDROCK_KNOWLEDGE_BASE_ID   = aws_bedrockagent_knowledge_base.service.id
      BEDROCK_RAG_ANSWER_MODEL_ID = var.bedrock_rag_answer_model_id
      QUERY_OPERATOR_ARN          = var.query_operator_arn
      MODEL_MAX_TOKENS            = tostring(var.query_max_tokens)
      MODEL_TEMPERATURE           = "0"
      KNOWLEDGE_RESULT_COUNT      = "5"
      QUERY_DEADLINE_SECONDS      = tostring(var.query_timeout_seconds - 2)
    }
  }
  lifecycle {
    precondition {
      condition     = var.index_validation_passed
      error_message = "Complete offline retrieval and isolation validation before enabling query traffic."
    }
    precondition {
      condition     = can(filebase64sha256(var.query_lambda_zip))
      error_message = "Build and supply a readable query Lambda ZIP before enabling the API."
    }
    precondition {
      condition     = startswith(var.query_operator_arn, "arn:aws:iam::${var.aws_account_id}:")
      error_message = "Supply the approved operator's exact IAM ARN in this account."
    }
  }
  depends_on = [aws_iam_role_policy.query]
}
resource "aws_api_gateway_rest_api" "query" {
  count = local.query_count
  name  = local.query_name
  endpoint_configuration { types = ["REGIONAL"] }
}
resource "aws_api_gateway_rest_api_policy" "query" {
  count       = local.query_count
  rest_api_id = aws_api_gateway_rest_api.query[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect   = "Allow", Principal = "*", Action = "execute-api:Invoke",
      Resource = "${aws_api_gateway_rest_api.query[0].execution_arn}/poc/POST/query",
    Condition = { ArnEquals = { "aws:PrincipalArn" = var.query_operator_arn } } },
    { Effect   = "Deny", Principal = "*", Action = "execute-api:Invoke",
      Resource = "${aws_api_gateway_rest_api.query[0].execution_arn}/*",
    Condition = { ArnNotEquals = { "aws:PrincipalArn" = var.query_operator_arn } } }
  ] })
}
resource "aws_api_gateway_resource" "query" {
  count       = local.query_count
  rest_api_id = aws_api_gateway_rest_api.query[0].id
  parent_id   = aws_api_gateway_rest_api.query[0].root_resource_id
  path_part   = "query"
}
resource "aws_api_gateway_method" "query" {
  count         = local.query_count
  rest_api_id   = aws_api_gateway_rest_api.query[0].id
  resource_id   = aws_api_gateway_resource.query[0].id
  http_method   = "POST"
  authorization = "AWS_IAM"
}
resource "aws_api_gateway_integration" "query" {
  count                   = local.query_count
  rest_api_id             = aws_api_gateway_rest_api.query[0].id
  resource_id             = aws_api_gateway_resource.query[0].id
  http_method             = aws_api_gateway_method.query[0].http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.query[0].invoke_arn
  timeout_milliseconds    = 29000
}
resource "aws_api_gateway_deployment" "query" {
  count       = local.query_count
  rest_api_id = aws_api_gateway_rest_api.query[0].id
  triggers = { redeployment = sha1(jsonencode([
    aws_api_gateway_resource.query[0], aws_api_gateway_method.query[0],
    aws_api_gateway_integration.query[0], aws_api_gateway_rest_api_policy.query[0].policy
  ])) }
  lifecycle { create_before_destroy = true }
}
resource "aws_api_gateway_stage" "query" {
  count         = local.query_count
  rest_api_id   = aws_api_gateway_rest_api.query[0].id
  deployment_id = aws_api_gateway_deployment.query[0].id
  stage_name    = "poc"
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api[0].arn
    format = jsonencode({ request_id = "$context.requestId", status = "$context.status", resource = "$context.resourcePath",
    latency_ms = "$context.responseLatency", integration_status = "$context.integrationStatus" })
  }
  depends_on = [aws_api_gateway_account.query, aws_lambda_permission.api]
}
resource "aws_api_gateway_method_settings" "query" {
  count       = local.query_count
  rest_api_id = aws_api_gateway_rest_api.query[0].id
  stage_name  = aws_api_gateway_stage.query[0].stage_name
  method_path = "*/*"
  settings {
    metrics_enabled        = true
    throttling_burst_limit = 5
    throttling_rate_limit  = 2
  }
}
resource "aws_lambda_permission" "api" {
  count          = local.query_count
  statement_id   = "QueryApiOnly"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.query[0].function_name
  principal      = "apigateway.amazonaws.com"
  source_account = var.aws_account_id
  source_arn     = "${aws_api_gateway_rest_api.query[0].execution_arn}/poc/POST/query"
}
