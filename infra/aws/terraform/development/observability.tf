variable "log_retention_days" {
  type    = number
  default = 14
  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90], var.log_retention_days)
    error_message = "Select a supported POC retention period: 1, 3, 5, 7, 14, 30, 60 or 90 days."
  }
}
locals {
  metric_namespace = "${var.project_name}/${var.environment}/Phase1"
  ingestion_metrics = {
    IngestionFailures       = { pattern = "{ $.event = \"ingestion_failed\" }", value = "1", unit = "Count" }
    IngestionRuns           = { pattern = "{ $.event = \"ingestion_completed\" || $.event = \"ingestion_failed\" }", value = "1", unit = "Count" }
    IngestionDuration       = { pattern = "{ $.duration_seconds = * }", value = "$.duration_seconds", unit = "Seconds" }
    DocumentsProcessed      = { pattern = "{ $.documents_processed = * }", value = "$.documents_processed", unit = "Count" }
    DocumentsFailed         = { pattern = "{ $.documents_failed = * }", value = "$.documents_failed", unit = "Count" }
    IndexValidationFailures = { pattern = "{ $.event = \"index_validation_failed\" }", value = "1", unit = "Count" }
  }
  query_metrics = {
    RetrievalResults        = { pattern = "{ $.retrieval_count = * }", value = "$.retrieval_count" }
    AnswersWithCitations    = { pattern = "{ $.has_citations = true }", value = "1" }
    InsufficientInformation = { pattern = "{ $.insufficient_information = true }", value = "1" }
    AuthorizationFailures   = { pattern = "{ $.event = \"authorization_failed\" }", value = "1" }
    InputTokens             = { pattern = "{ $.input_tokens = * }", value = "$.input_tokens" }
    OutputTokens            = { pattern = "{ $.output_tokens = * }", value = "$.output_tokens" }
  }
}
resource "aws_cloudwatch_log_group" "ingestion" {
  name              = "/${local.name}/ingestion"
  retention_in_days = var.log_retention_days
}
resource "aws_cloudwatch_log_group" "query" {
  count             = local.query_count
  name              = "/aws/lambda/${local.query_name}"
  retention_in_days = var.log_retention_days
}
resource "aws_cloudwatch_log_group" "api" {
  count             = local.query_count
  name              = "/aws/vendedlogs/${local.name}/api"
  retention_in_days = var.log_retention_days
}
# API Gateway's CloudWatch role is a regional account setting; import if already managed.
resource "aws_iam_role" "api_logs" {
  count = local.query_count
  name  = "${local.name}_api_logs"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "apigateway.amazonaws.com" }
  }] })
}
resource "aws_iam_role_policy" "api_logs" {
  count = local.query_count
  role  = aws_iam_role.api_logs[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["logs:DescribeLogGroups"], Resource = "*" },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:DescribeLogStreams", "logs:PutLogEvents", "logs:GetLogEvents", "logs:FilterLogEvents"], Resource = "${aws_cloudwatch_log_group.api[0].arn}:*" }
  ] })
}
resource "aws_api_gateway_account" "query" {
  count               = local.query_count
  cloudwatch_role_arn = aws_iam_role.api_logs[0].arn
  depends_on          = [aws_iam_role_policy.api_logs]
}
resource "aws_cloudwatch_log_metric_filter" "ingestion" {
  for_each       = local.ingestion_metrics
  name           = each.key
  log_group_name = aws_cloudwatch_log_group.ingestion.name
  pattern        = each.value.pattern
  metric_transformation {
    name      = each.key
    namespace = local.metric_namespace
    value     = each.value.value
    unit      = each.value.unit
  }
}
resource "aws_cloudwatch_log_metric_filter" "query" {
  for_each       = var.enable_query_api ? local.query_metrics : {}
  name           = each.key
  log_group_name = aws_cloudwatch_log_group.query[0].name
  pattern        = each.value.pattern
  metric_transformation {
    name      = each.key
    namespace = local.metric_namespace
    value     = each.value.value
    unit      = "Count"
  }
}
resource "aws_cloudwatch_log_metric_filter" "api_authentication" {
  count          = local.query_count
  name           = "ApiAuthenticationFailures"
  log_group_name = aws_cloudwatch_log_group.api[0].name
  pattern        = "{ $.status = \"401\" || $.status = \"403\" }"
  metric_transformation {
    name      = "ApiAuthenticationFailures"
    namespace = local.metric_namespace
    value     = "1"
    unit      = "Count"
  }
}
resource "aws_cloudwatch_dashboard" "poc" {
  dashboard_name = "${local.name}_poc"
  dashboard_body = jsonencode({ widgets = concat([
    { type = "metric", x = 0, y = 0, width = 12, height = 6, properties = {
      title   = "Ingestion and index validation", region = var.aws_region, period = 60, stat = "Sum",
      metrics = [for name in keys(local.ingestion_metrics) : [local.metric_namespace, name]]
    } }
    ], var.enable_query_api ? [
    { type = "metric", x = 12, y = 0, width = 12, height = 6, properties = {
      title   = "API requests and errors", region = var.aws_region, period = 60, stat = "Sum",
      metrics = [for name in ["Count", "4XXError", "5XXError"] : ["AWS/ApiGateway", name, "ApiName", local.query_name, "Stage", "poc"]]
    } },
    { type = "metric", x = 0, y = 6, width = 12, height = 6, properties = {
      title   = "Lambda requests, errors and throttles", region = var.aws_region, period = 60, stat = "Sum",
      metrics = [for name in ["Invocations", "Errors", "Throttles"] : ["AWS/Lambda", name, "FunctionName", local.query_name]]
    } },
    { type = "metric", x = 12, y = 6, width = 12, height = 6, properties = {
      title   = "API and Lambda latency (ms)", region = var.aws_region, period = 60, stat = "p95",
      metrics = [["AWS/ApiGateway", "Latency", "ApiName", local.query_name, "Stage", "poc"], ["AWS/Lambda", "Duration", "FunctionName", local.query_name]]
    } },
    { type = "metric", x = 0, y = 12, width = 24, height = 6, properties = {
      title   = "Query and authentication signals", region = var.aws_region, period = 60, stat = "Sum",
      metrics = [for name in concat(keys(local.query_metrics), ["ApiAuthenticationFailures"]) : [local.metric_namespace, name]]
    } }
  ] : []) })
}
output "observability" {
  value = {
    ingestion_log_group = aws_cloudwatch_log_group.ingestion.name
    query_log_group     = try(aws_cloudwatch_log_group.query[0].name, null)
    api_log_group       = try(aws_cloudwatch_log_group.api[0].name, null)
    metric_namespace    = local.metric_namespace
    dashboard_name      = aws_cloudwatch_dashboard.poc.dashboard_name
  }
}
