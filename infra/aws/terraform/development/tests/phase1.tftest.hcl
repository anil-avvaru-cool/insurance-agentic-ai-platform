mock_provider "aws" {
  mock_resource "aws_iam_role" { defaults = { arn = "arn:aws:iam::123456789012:role/mock" } }
  mock_resource "aws_s3vectors_index" { defaults = { index_arn = "arn:aws:s3vectors:us-east-1:123456789012:bucket/mock/index/mock" } }
  mock_resource "aws_s3_bucket" { defaults = { arn = "arn:aws:s3:::mock-bucket" } }
  mock_resource "aws_cloudwatch_log_group" { defaults = { arn = "arn:aws:logs:us-east-1:123456789012:log-group:mock" } }
  mock_resource "aws_lambda_function" { defaults = { invoke_arn = "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:123456789012:function:mock/invocations" } }
  mock_resource "aws_api_gateway_rest_api" { defaults = { execution_arn = "arn:aws:execute-api:us-east-1:123456789012:mock" } }
}
variables {
  log_retention_days        = 14
  aws_region                = "us-east-1"
  aws_account_id            = "123456789012"
  project_name              = "insurance"
  environment               = "development"
  owner                     = "test"
  enable_query_api          = false
  enable_evaluation_capture = false
  index_validation_passed   = false
  query_operator_arn        = ""
  query_lambda_zip          = ""
}
run "offline_monitoring" {
  command = plan
  assert {
    condition     = length(aws_lambda_function.query) == 0 && length(aws_api_gateway_stage.query) == 0 && length(aws_s3_bucket.evaluation_capture) == 0
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
run "evaluation_capture" {
  command = apply
  variables {
    enable_query_api          = true
    enable_evaluation_capture = true
    index_validation_passed   = true
    query_lambda_zip          = "tests/phase1.tftest.hcl"
    query_operator_arn        = "arn:aws:iam::123456789012:user/operator"
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.evaluation_capture[0].block_public_acls && aws_s3_bucket_public_access_block.evaluation_capture[0].block_public_policy && aws_s3_bucket_public_access_block.evaluation_capture[0].ignore_public_acls && aws_s3_bucket_public_access_block.evaluation_capture[0].restrict_public_buckets && !aws_s3_bucket.evaluation_capture[0].force_destroy
    error_message = "Capture storage must be private and protected from forced deletion."
  }
  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.evaluation_capture[0].rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256" && one(aws_s3_bucket_lifecycle_configuration.evaluation_capture[0].rule).expiration[0].days == 30
    error_message = "Encrypt captures and configure retention."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.evaluation_capture[0].policy).Statement[0].Action == ["s3:PutObject"] && jsondecode(aws_iam_role_policy.evaluation_capture[0].policy).Statement[0].Resource == ["${aws_s3_bucket.evaluation_capture[0].arn}/captures/*"]
    error_message = "Lambda may only write the capture prefix."
  }
  assert {
    condition     = jsondecode(aws_s3_bucket_policy.evaluation_capture[0].policy).Statement[1].Condition.ArnEquals["aws:PrincipalArn"] == var.query_operator_arn && jsondecode(aws_s3_bucket_policy.evaluation_capture[0].policy).Statement[1].Action == "s3:GetObject" && jsondecode(aws_s3_bucket_policy.evaluation_capture[0].policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false"
    error_message = "Grant capture reads to the configured operator and require TLS."
  }
  assert {
    condition     = aws_lambda_function.query[0].environment[0].variables.QUERY_CAPTURE_ENABLED == "true" && aws_lambda_function.query[0].environment[0].variables.QUERY_MAX_CONTEXT_CHARS == "24000" && aws_lambda_function.query[0].environment[0].variables.QUERY_DEPLOYMENT_ID == filebase64sha256(var.query_lambda_zip)
    error_message = "Pass capture opt-in, evidence limits, and code hash to Lambda."
  }
}
run "judge_disabled" {
  command = plan
  assert {
    condition     = length(aws_s3_bucket.rag_judge) == 0 && length(aws_iam_role.rag_judge) == 0 && length(aws_iam_policy.rag_judge_operator) == 0
    error_message = "Judge resources must remain opt-in."
  }
}
run "judge_requires_evaluators" {
  command = plan
  variables { enable_rag_judge = true }
  expect_failures = [aws_iam_role.rag_judge]
}
run "judge_scoped_permissions" {
  command = apply
  variables {
    enable_rag_judge                = true
    judge_evaluator_model_id        = "amazon.nova-pro-v1:0"
    judge_custom_evaluator_model_id = "amazon.nova-lite-v1:0"
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.rag_judge[0].block_public_policy && aws_s3_bucket_public_access_block.rag_judge[0].restrict_public_buckets && !aws_s3_bucket.rag_judge[0].force_destroy && one(aws_s3_bucket_server_side_encryption_configuration.rag_judge[0].rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "Evaluation data must be private, encrypted and protected from forced deletion."
  }
  assert {
    condition     = jsondecode(aws_iam_role.rag_judge[0].assume_role_policy).Statement[0].Condition.StringEquals["aws:SourceAccount"] == var.aws_account_id && jsondecode(aws_iam_role.rag_judge[0].assume_role_policy).Statement[0].Condition.ArnLike["aws:SourceArn"] == local.judge_job_arn
    error_message = "Only Bedrock evaluations in this account and region may assume the judge role."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.rag_judge[0].policy).Statement[2].Resource == ["${aws_s3_bucket.rag_judge[0].arn}/datasets/*"] && jsondecode(aws_iam_role_policy.rag_judge[0].policy).Statement[3].Resource == ["${aws_s3_bucket.rag_judge[0].arn}/results/*"] && toset(jsondecode(aws_iam_role_policy.rag_judge[0].policy).Statement[4].Resource) == toset(local.judge_model_arns)
    error_message = "Judge role must use only input/output prefixes and the configured evaluator models."
  }
  assert {
    condition     = jsondecode(aws_iam_policy.rag_judge_operator[0].policy).Statement[2].Resource == [aws_iam_role.rag_judge[0].arn] && jsondecode(aws_iam_policy.rag_judge_operator[0].policy).Statement[2].Condition.StringEquals["iam:PassedToService"] == "bedrock.amazonaws.com" && length(aws_iam_role_policy_attachment.rag_judge_operator) == 0
    error_message = "Scope PassRole and avoid guessing an operator attachment."
  }
  assert {
    condition     = output.rag_judge_environment.JUDGE_EVALUATOR_MODEL_ID == var.judge_evaluator_model_id && output.rag_judge_environment.JUDGE_CUSTOM_EVALUATOR_MODEL_ID == var.judge_custom_evaluator_model_id
    error_message = "Export both independently configured evaluators."
  }
  assert {
    condition     = toset(jsondecode(aws_iam_policy.rag_judge_operator[0].policy).Statement[0].Resource) == toset(local.judge_model_arns) && jsondecode(aws_iam_policy.rag_judge_operator[0].policy).Statement[1].Resource == [local.judge_job_arn]
    error_message = "CreateEvaluationJob authorizes on model ARNs; GetEvaluationJob authorizes on job ARNs."
  }
}
