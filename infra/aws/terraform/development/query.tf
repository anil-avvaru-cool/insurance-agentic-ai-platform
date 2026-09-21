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
variable "jwt_issuer" {
  type    = string
  default = ""
}
variable "jwt_audience" {
  type    = list(string)
  default = []
}
variable "jwt_scopes" {
  description = "Required access-token scopes for an external issuer. Cognito uses its API sign-in scope."
  type        = list(string)
  default     = []
}
variable "owner_by_subject" {
  description = "Verified subject to approved corpus owner mapping, scoped to the single configured issuer. No passwords or tokens."
  type        = map(string)
  default     = {}
  validation {
    condition     = alltrue([for subject, owner in var.owner_by_subject : trimspace(subject) != "" && contains(["customer_one", "customer_two"], owner)])
    error_message = "Map nonempty verified subjects only to approved POC corpus owners."
  }
}
variable "query_timeout_seconds" {
  type    = number
  default = 28
  validation {
    condition     = var.query_timeout_seconds >= 5 && var.query_timeout_seconds <= 28 && floor(var.query_timeout_seconds) == var.query_timeout_seconds
    error_message = "Use an integer Lambda timeout of 5..28 seconds, below the 30-second integration timeout."
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
  query_count  = var.enable_query_api ? 1 : 0
  query_name   = "${local.name}_query"
  jwt_issuer   = var.create_cognito ? "https://${aws_cognito_user_pool.poc[0].endpoint}" : var.jwt_issuer
  jwt_audience = var.create_cognito ? [aws_cognito_user_pool_client.poc[0].id] : var.jwt_audience
  jwt_scopes   = var.create_cognito ? ["aws.cognito.signin.user.admin"] : var.jwt_scopes
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
    { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = [local.model_arn] },
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
      BEDROCK_KNOWLEDGE_BASE_ID = aws_bedrockagent_knowledge_base.service.id
      BEDROCK_MODEL_ID          = var.bedrock_model_id
      JWT_ISSUER                = local.jwt_issuer
      OWNER_BY_SUBJECT_JSON     = jsonencode(var.owner_by_subject)
      MODEL_MAX_TOKENS          = tostring(var.query_max_tokens)
      MODEL_TEMPERATURE         = "0"
      KNOWLEDGE_RESULT_COUNT    = "5"
      QUERY_DEADLINE_SECONDS    = tostring(var.query_timeout_seconds - 2)
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
      condition     = length(var.owner_by_subject) == 2 && length(toset(values(var.owner_by_subject))) == 2 && length(jsonencode(var.owner_by_subject)) < 2500
      error_message = "Supply two verified subjects mapping to the two distinct POC owners within the Lambda environment size budget."
    }
    precondition {
      condition     = var.create_cognito || (can(regex("^https://[^ ]+$", var.jwt_issuer)) && length(var.jwt_audience) > 0 && length(var.jwt_scopes) > 0 && alltrue([for v in concat(var.jwt_audience, var.jwt_scopes) : trimspace(v) != ""]))
      error_message = "Configure an HTTPS JWT issuer, audience and access-token scopes, or enable Cognito."
    }
  }
  depends_on = [aws_iam_role_policy.query]
}
resource "aws_apigatewayv2_api" "query" {
  count         = local.query_count
  name          = local.query_name
  protocol_type = "HTTP"
}
resource "aws_apigatewayv2_authorizer" "query" {
  count            = local.query_count
  api_id           = aws_apigatewayv2_api.query[0].id
  name             = "verified_owner"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  jwt_configuration {
    issuer   = local.jwt_issuer
    audience = local.jwt_audience
  }
}
resource "aws_apigatewayv2_integration" "query" {
  count                  = local.query_count
  api_id                 = aws_apigatewayv2_api.query[0].id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.query[0].invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000
}
resource "aws_apigatewayv2_route" "query" {
  count                = local.query_count
  api_id               = aws_apigatewayv2_api.query[0].id
  route_key            = "POST /query"
  target               = "integrations/${aws_apigatewayv2_integration.query[0].id}"
  authorization_type   = "JWT"
  authorizer_id        = aws_apigatewayv2_authorizer.query[0].id
  authorization_scopes = local.jwt_scopes
}
resource "aws_apigatewayv2_stage" "query" {
  count       = local.query_count
  api_id      = aws_apigatewayv2_api.query[0].id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    detailed_metrics_enabled = true
    throttling_burst_limit   = 5
    throttling_rate_limit    = 2
  }
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api[0].arn
    format = jsonencode({ request_id = "$context.requestId", status = "$context.status", route = "$context.routeKey",
    latency_ms = "$context.responseLatency", integration_status = "$context.integrationStatus" })
  }
  depends_on = [aws_cloudwatch_log_resource_policy.api, aws_lambda_permission.api]
}
resource "aws_lambda_permission" "api" {
  count          = local.query_count
  statement_id   = "QueryApiOnly"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.query[0].function_name
  principal      = "apigateway.amazonaws.com"
  source_account = var.aws_account_id
  source_arn     = "${aws_apigatewayv2_api.query[0].execution_arn}/$default/POST/query"
}
