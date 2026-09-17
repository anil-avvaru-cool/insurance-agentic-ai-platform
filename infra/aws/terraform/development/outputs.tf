output "vpc_id" { value = aws_vpc.development.id }
output "private_subnet_ids" { value = aws_subnet.private[*].id }
output "checkpoint_endpoint" { value = aws_db_instance.checkpoint.endpoint }
output "checkpoint_database" { value = aws_db_instance.checkpoint.db_name }
output "checkpoint_admin_secret_arn" {
  description = "Migration/operator identity only. Secret value is managed by RDS, never read by Terraform."
  value       = aws_db_instance.checkpoint.master_user_secret[0].secret_arn
}
output "checkpoint_client_security_group_id" { value = aws_security_group.checkpoint_client.id }
output "task_queue_url" { value = aws_sqs_queue.tasks.id }
output "dead_letter_queue_url" { value = aws_sqs_queue.dead_letter.id }
output "service_role_arns" { value = { for name, role in aws_iam_role.service : name => role.arn } }
