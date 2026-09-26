mock_provider "aws" {
  mock_resource "aws_iam_role" { defaults = { arn = "arn:aws:iam::123456789012:role/mock" } }
  mock_resource "aws_s3vectors_index" { defaults = { index_arn = "arn:aws:s3vectors:us-east-1:123456789012:bucket/mock/index/mock" } }
  mock_resource "aws_s3_bucket" { defaults = { arn = "arn:aws:s3:::mock-bucket" } }
  mock_resource "aws_cloudwatch_log_group" { defaults = { arn = "arn:aws:logs:us-east-1:123456789012:log-group:mock" } }
  mock_resource "aws_lambda_function" { defaults = { invoke_arn = "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:123456789012:function:mock/invocations" } }
  mock_resource "aws_api_gateway_rest_api" { defaults = { execution_arn = "arn:aws:execute-api:us-east-1:123456789012:mock" } }
}
variables {
  aws_region     = "us-east-1"
  aws_account_id = "123456789012"
  project_name   = "insurance"
  environment    = "development"
  owner          = "test"
}
run "offline_monitoring" {
  command = plan
  assert {
    condition     = length(aws_lambda_function.query) == 0 && length(aws_api_gateway_stage.query) == 0
    error_message = "Online resources must be opt-in."
  }
  assert {
    condition     = aws_cloudwatch_log_group.ingestion.retention_in_days == 14 && length(aws_cloudwatch_log_metric_filter.ingestion) == 6
    error_message = "Offline monitoring must exist before enabling the API."
  }
}
run "operator_iam_api" {
  command = apply
  variables {
    enable_query_api        = true
    index_validation_passed = true
    query_lambda_zip        = "tests/phase1.tftest.hcl"
    query_operator_arn      = "arn:aws:iam::123456789012:root"
  }
  assert {
    condition     = aws_api_gateway_method.query[0].authorization == "AWS_IAM" && aws_api_gateway_method.query[0].http_method == "POST"
    error_message = "The query method must require IAM authentication."
  }
  assert {
    condition     = jsondecode(aws_api_gateway_rest_api_policy.query[0].policy).Statement[1].Effect == "Deny" && jsondecode(aws_api_gateway_rest_api_policy.query[0].policy).Statement[1].Condition.ArnNotEquals["aws:PrincipalArn"] == var.query_operator_arn && jsondecode(aws_api_gateway_rest_api_policy.query[0].policy).Statement[1].Resource == "${aws_api_gateway_rest_api.query[0].execution_arn}/*"
    error_message = "Explicitly deny all API invocation by other principals, including same-account identities."
  }
  assert {
    condition     = jsondecode(aws_api_gateway_rest_api_policy.query[0].policy).Statement[0].Condition.ArnEquals["aws:PrincipalArn"] == var.query_operator_arn && jsondecode(aws_api_gateway_rest_api_policy.query[0].policy).Statement[0].Resource == "${aws_api_gateway_rest_api.query[0].execution_arn}/poc/POST/query"
    error_message = "Allow only the exact principal and query method, not the entire account."
  }
  assert {
    condition     = aws_lambda_function.query[0].timeout * 1000 < aws_api_gateway_integration.query[0].timeout_milliseconds && aws_api_gateway_method_settings.query[0].settings[0].throttling_rate_limit == 2
    error_message = "Bound synchronous query duration and request rate."
  }
  assert {
    condition     = aws_lambda_function.query[0].environment[0].variables.QUERY_OPERATOR_ARN == var.query_operator_arn && aws_lambda_permission.api[0].source_arn == "${aws_api_gateway_rest_api.query[0].execution_arn}/poc/POST/query"
    error_message = "Pass the operator to the handler and restrict API Gateway's Lambda permission."
  }
  assert {
    condition     = length(aws_cloudwatch_log_metric_filter.query) == 6 && length(aws_cloudwatch_log_metric_filter.api_authentication) == 1
    error_message = "Keep handler and gateway authentication monitoring."
  }
}
run "reject_unvalidated_index" {
  command = plan
  variables {
    enable_query_api   = true
    query_lambda_zip   = "tests/phase1.tftest.hcl"
    query_operator_arn = "arn:aws:iam::123456789012:user/operator"
  }
  expect_failures = [aws_lambda_function.query]
}
run "reject_missing_artifact" {
  command = plan
  variables {
    enable_query_api        = true
    index_validation_passed = true
    query_operator_arn      = "arn:aws:iam::123456789012:user/operator"
  }
  expect_failures = [aws_lambda_function.query]
}
run "reject_missing_operator" {
  command = plan
  variables {
    enable_query_api        = true
    index_validation_passed = true
    query_lambda_zip        = "tests/phase1.tftest.hcl"
  }
  expect_failures = [aws_lambda_function.query]
}
run "reject_wildcard_operator" {
  command = plan
  variables { query_operator_arn = "arn:aws:iam::123456789012:user/*" }
  expect_failures = [var.query_operator_arn]
}
run "reject_other_account_operator" {
  command = plan
  variables {
    enable_query_api        = true
    index_validation_passed = true
    query_lambda_zip        = "tests/phase1.tftest.hcl"
    query_operator_arn      = "arn:aws:iam::999999999999:user/operator"
  }
  expect_failures = [aws_lambda_function.query]
}
