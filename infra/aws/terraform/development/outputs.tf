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

# Export only the runtime contract, not access to the entire infrastructure state.
output "runtime_inputs" {
  value = {
    infrastructure = {
      aws_region         = var.aws_region
      aws_account_id     = var.aws_account_id
      project_name       = var.project_name
      environment        = var.environment
      owner              = var.owner
      model_id           = var.bedrock_model_id
      knowledge_base_id  = aws_bedrockagent_knowledge_base.service.id
      ecr_repository_url = aws_ecr_repository.agentcore.repository_url
      agentcore_role_arn = aws_iam_role.agentcore.arn
      worker_role_name   = aws_iam_role.service["worker"].name
    }
  }
}
