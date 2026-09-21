mock_provider "aws" {}
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
    condition     = length(aws_lambda_function.query) == 0 && length(aws_apigatewayv2_stage.query) == 0 && length(aws_cognito_user_pool.poc) == 0
    error_message = "Online resources and identity provider must be opt-in."
  }
  assert {
    condition     = aws_cloudwatch_log_group.ingestion.retention_in_days == 14 && length(aws_cloudwatch_log_metric_filter.ingestion) == 6
    error_message = "Offline monitoring must exist before enabling the API."
  }
}
run "external_jwt_api" {
  command = plan
  variables {
    enable_query_api        = true
    index_validation_passed = true
    # Plan-only hash input, deliberately not a deployable Lambda ZIP.
    query_lambda_zip = "tests/phase1.tftest.hcl"
    jwt_issuer       = "https://issuer.example.test"
    jwt_audience     = ["poc-client"]
    jwt_scopes       = ["policy:query"]
    owner_by_subject = { subject_one = "customer_one", subject_two = "customer_two" }
  }
  assert {
    condition     = aws_apigatewayv2_route.query[0].authorization_type == "JWT" && aws_apigatewayv2_route.query[0].authorization_scopes == toset(["policy:query"]) && aws_apigatewayv2_route.query[0].route_key == "POST /query"
    error_message = "The query route must require scoped JWT authorization."
  }
  assert {
    condition     = aws_lambda_function.query[0].timeout * 1000 < aws_apigatewayv2_integration.query[0].timeout_milliseconds && aws_apigatewayv2_stage.query[0].default_route_settings[0].throttling_rate_limit == 2
    error_message = "Bound synchronous query duration and request rate."
  }
  assert {
    condition     = jsondecode(aws_lambda_function.query[0].environment[0].variables.OWNER_BY_SUBJECT_JSON).subject_one == "customer_one" && aws_lambda_function.query[0].environment[0].variables.JWT_ISSUER == var.jwt_issuer
    error_message = "Pass issuer-bound subject mappings to the handler."
  }
  assert {
    condition     = length(aws_cloudwatch_log_metric_filter.query) == 6 && length(aws_cloudwatch_log_metric_filter.api_authentication) == 1 && aws_cloudwatch_log_group.query[0].retention_in_days == 14
    error_message = "Online monitoring must include query and pre-Lambda authentication signals."
  }
}
run "cognito_before_api" {
  command = plan
  variables { create_cognito = true }
  assert {
    condition     = length(aws_cognito_user_pool.poc) == 1 && length(aws_lambda_function.query) == 0 && aws_cognito_user_pool.poc[0].admin_create_user_config[0].allow_admin_create_user_only && !aws_cognito_user_pool_client.poc[0].generate_secret
    error_message = "Allow controlled identity provisioning before mapping subjects and enabling queries."
  }
}
run "reject_unvalidated_index" {
  command = plan
  variables {
    enable_query_api = true
    query_lambda_zip = "tests/phase1.tftest.hcl"
    jwt_issuer       = "https://issuer.example.test"
    jwt_audience     = ["poc-client"]
    jwt_scopes       = ["policy:query"]
    owner_by_subject = { subject_one = "customer_one", subject_two = "customer_two" }
  }
  expect_failures = [aws_lambda_function.query]
}
run "reject_missing_artifact" {
  command = plan
  variables {
    enable_query_api        = true
    index_validation_passed = true
    jwt_issuer              = "https://issuer.example.test"
    jwt_audience            = ["poc-client"]
    jwt_scopes              = ["policy:query"]
    owner_by_subject        = { subject_one = "customer_one", subject_two = "customer_two" }
  }
  expect_failures = [aws_lambda_function.query]
}
run "reject_missing_identity" {
  command = plan
  variables {
    enable_query_api        = true
    index_validation_passed = true
    query_lambda_zip        = "tests/phase1.tftest.hcl"
    owner_by_subject        = { subject_one = "customer_one", subject_two = "customer_two" }
  }
  expect_failures = [aws_lambda_function.query]
}
run "reject_incomplete_mapping" {
  command = plan
  variables {
    enable_query_api        = true
    index_validation_passed = true
    query_lambda_zip        = "tests/phase1.tftest.hcl"
    jwt_issuer              = "https://issuer.example.test"
    jwt_audience            = ["poc-client"]
    jwt_scopes              = ["policy:query"]
    owner_by_subject        = { subject_one = "customer_one" }
  }
  expect_failures = [aws_lambda_function.query]
}
run "cognito_query_api" {
  command = plan
  variables {
    create_cognito          = true
    enable_query_api        = true
    index_validation_passed = true
    query_lambda_zip        = "tests/phase1.tftest.hcl"
    owner_by_subject        = { subject_one = "customer_one", subject_two = "customer_two" }
  }
  assert {
    condition     = aws_apigatewayv2_route.query[0].authorization_scopes == toset(["aws.cognito.signin.user.admin"]) && contains(aws_cognito_user_pool_client.poc[0].explicit_auth_flows, "ALLOW_USER_SRP_AUTH")
    error_message = "Cognito must support SRP and require the access-token scope."
  }
}
