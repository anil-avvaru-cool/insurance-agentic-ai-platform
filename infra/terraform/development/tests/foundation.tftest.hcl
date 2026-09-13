mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
}
variables {
  aws_region                = "us-east-1"
  aws_account_id            = "123456789012"
  project_name              = "insurance"
  environment               = "development"
  owner                     = "test"
  vpc_id                    = "vpc_test"
  private_subnet_ids        = ["subnet_one", "subnet_two"]
  postgres_engine_version   = "16.6"
  postgres_parameter_family = "postgres16"
  db_instance_class         = "db.t4g.micro"
  db_allocated_storage_gib  = 20
  db_deletion_protection    = true
  final_snapshot_identifier = "insurancetestfinal"
}
override_data {
  target = data.aws_subnet.private["subnet_one"]
  values = { vpc_id = "vpc_test", availability_zone = "us-east-1a", map_public_ip_on_launch = false }
}
override_data {
  target = data.aws_subnet.private["subnet_two"]
  values = { vpc_id = "vpc_test", availability_zone = "us-east-1b", map_public_ip_on_launch = false }
}
run "private_foundation" {
  command = plan
  assert {
    condition     = !aws_db_instance.checkpoint.publicly_accessible && aws_db_instance.checkpoint.storage_encrypted && aws_db_instance.checkpoint.manage_master_user_password && aws_db_instance.checkpoint.deletion_protection && !aws_db_instance.checkpoint.skip_final_snapshot
    error_message = "Checkpoint storage must be private, encrypted, password managed and recoverable."
  }
  assert {
    condition     = aws_sqs_queue.tasks.sqs_managed_sse_enabled && aws_sqs_queue.dead_letter.message_retention_seconds > aws_sqs_queue.tasks.message_retention_seconds
    error_message = "Queues must be encrypted and dead letters retained longer than tasks."
  }
  assert {
    condition     = length(aws_iam_role.service) == 3 && aws_iam_role.service["api"].name != aws_iam_role.service["worker"].name
    error_message = "API, worker and action identities must be separate."
  }
}
run "reject_wrong_vpc" {
  command = plan
  variables { vpc_id = "vpc_wrong" }
  expect_failures = [aws_db_subnet_group.checkpoint]
}
run "reject_single_az" {
  command = plan
  override_data {
    target = data.aws_subnet.private["subnet_two"]
    values = { vpc_id = "vpc_test", availability_zone = "us-east-1a", map_public_ip_on_launch = false }
  }
  expect_failures = [aws_db_subnet_group.checkpoint]
}
run "reject_public_ip_subnet" {
  command = plan
  override_data {
    target = data.aws_subnet.private["subnet_two"]
    values = { vpc_id = "vpc_test", availability_zone = "us-east-1b", map_public_ip_on_launch = true }
  }
  expect_failures = [aws_db_subnet_group.checkpoint]
}
