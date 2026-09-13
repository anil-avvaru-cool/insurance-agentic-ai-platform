mock_provider "aws" {}
variables {
  aws_region        = "us-east-1"
  aws_account_id    = "123456789012"
  project_name      = "insurance"
  environment       = "development"
  owner             = "test"
  state_bucket_name = "insuranceteststate123456789012"
}
run "protected_state" {
  command = plan
  assert {
    condition     = aws_s3_bucket_versioning.state.versioning_configuration[0].status == "Enabled" && aws_s3_bucket_server_side_encryption_configuration.state.rule != null && aws_s3_bucket_public_access_block.state.block_public_policy && !aws_s3_bucket.state.force_destroy
    error_message = "State must retain versions, encryption and public access protection."
  }
}
