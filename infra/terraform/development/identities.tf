data "aws_iam_policy_document" "ecs_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.aws_account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:*"]
    }
  }
}
resource "aws_iam_role" "service" {
  for_each           = toset(["api", "worker", "action_service"])
  name               = "${local.name}_${each.key}"
  assume_role_policy = data.aws_iam_policy_document.ecs_trust.json
}
data "aws_iam_policy_document" "producer" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.tasks.arn]
  }
}
data "aws_iam_policy_document" "consumer" {
  statement {
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.tasks.arn]
  }
}
resource "aws_iam_role_policy" "producer" {
  name   = "task_producer"
  role   = aws_iam_role.service["api"].id
  policy = data.aws_iam_policy_document.producer.json
}
resource "aws_iam_role_policy" "consumer" {
  name   = "task_consumer"
  role   = aws_iam_role.service["worker"].id
  policy = data.aws_iam_policy_document.consumer.json
}
# Action service permissions wait for the approved core sandbox contract.
# No workload role can read the RDS administrator secret.
