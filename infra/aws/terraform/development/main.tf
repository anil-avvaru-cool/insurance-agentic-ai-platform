variable "postgres_engine_version" { type = string }
variable "postgres_parameter_family" { type = string }
variable "db_instance_class" { type = string }
variable "db_allocated_storage_gib" {
  type = number
  validation {
    condition     = var.db_allocated_storage_gib >= 20 && floor(var.db_allocated_storage_gib) == var.db_allocated_storage_gib
    error_message = "RDS storage must be an integer of at least 20 GiB."
  }
}
variable "db_deletion_protection" { type = bool }
variable "final_snapshot_identifier" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{0,62}$", var.final_snapshot_identifier))
    error_message = "Supply a unique lowercase alphanumeric final snapshot identifier."
  }
}
resource "aws_security_group" "checkpoint_client" {
  name        = "${local.name}_checkpoint_client"
  description = "Attach only to authorized checkpoint clients; database egress only"
  vpc_id      = aws_vpc.development.id
}
resource "aws_security_group" "checkpoint" {
  name        = "${local.name}_checkpoint"
  description = "Private PostgreSQL checkpoint database"
  vpc_id      = aws_vpc.development.id
}
resource "aws_vpc_security_group_ingress_rule" "postgres" {
  security_group_id            = aws_security_group.checkpoint.id
  referenced_security_group_id = aws_security_group.checkpoint_client.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}
resource "aws_vpc_security_group_egress_rule" "postgres" {
  security_group_id            = aws_security_group.checkpoint_client.id
  referenced_security_group_id = aws_security_group.checkpoint.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}
resource "aws_db_subnet_group" "checkpoint" {
  name       = "${local.name}_checkpoint"
  subnet_ids = aws_subnet.private[*].id
}
resource "aws_db_parameter_group" "checkpoint" {
  name   = "${local.aws_name}checkpoint"
  family = var.postgres_parameter_family
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}
resource "aws_db_instance" "checkpoint" {
  identifier                      = "${local.aws_name}checkpoint"
  engine                          = "postgres"
  engine_version                  = var.postgres_engine_version
  instance_class                  = var.db_instance_class
  allocated_storage               = var.db_allocated_storage_gib
  storage_type                    = "gp3"
  storage_encrypted               = true
  db_name                         = "checkpoints"
  username                        = "checkpoint_admin"
  manage_master_user_password     = true
  db_subnet_group_name            = aws_db_subnet_group.checkpoint.name
  parameter_group_name            = aws_db_parameter_group.checkpoint.name
  vpc_security_group_ids          = [aws_security_group.checkpoint.id]
  publicly_accessible             = false
  multi_az                        = false
  backup_retention_period         = 7
  auto_minor_version_upgrade      = true
  apply_immediately               = false
  deletion_protection             = var.db_deletion_protection
  skip_final_snapshot             = false
  final_snapshot_identifier       = var.final_snapshot_identifier
  copy_tags_to_snapshot           = true
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
}
resource "aws_sqs_queue" "dead_letter" {
  name                      = "${local.name}_dead_letter"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}
resource "aws_sqs_queue" "tasks" {
  name                       = "${local.name}_tasks"
  message_retention_seconds  = 345600
  visibility_timeout_seconds = 300
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dead_letter.arn, maxReceiveCount = 5 })
}
resource "aws_sqs_queue_redrive_allow_policy" "dead_letter" {
  queue_url            = aws_sqs_queue.dead_letter.id
  redrive_allow_policy = jsonencode({ redrivePermission = "byQueue", sourceQueueArns = [aws_sqs_queue.tasks.arn] })
}
data "aws_iam_policy_document" "queue_tls" {
  for_each = { tasks = aws_sqs_queue.tasks.arn, dead_letter = aws_sqs_queue.dead_letter.arn }
  statement {
    effect    = "Deny"
    actions   = ["sqs:*"]
    resources = [each.value]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}
resource "aws_sqs_queue_policy" "tls" {
  for_each  = { tasks = aws_sqs_queue.tasks.id, dead_letter = aws_sqs_queue.dead_letter.id }
  queue_url = each.value
  policy    = data.aws_iam_policy_document.queue_tls[each.key].json
}
