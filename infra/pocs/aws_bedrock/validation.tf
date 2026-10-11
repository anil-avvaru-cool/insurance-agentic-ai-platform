# Operator-only capability: deliberately separate from upload/sync permissions.
variable "validation_runner_role_name" {
  description = "Existing trusted operator role for retrieval and answer evaluation; never attach to end users."
  type        = string
  default     = null
}
resource "aws_iam_policy" "validation_runner" {
  name = "${local.name}_validation_runner"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["bedrock:Retrieve"], Resource = [aws_bedrockagent_knowledge_base.service.arn] },
    { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = [local.rag_answer_model_arn] },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = ["${aws_cloudwatch_log_group.ingestion.arn}:*"] }
  ] })
}
resource "aws_iam_role_policy_attachment" "validation_runner" {
  count      = var.validation_runner_role_name == null ? 0 : 1
  role       = var.validation_runner_role_name
  policy_arn = aws_iam_policy.validation_runner.arn
}
output "validation_runner_policy_arn" { value = aws_iam_policy.validation_runner.arn }
