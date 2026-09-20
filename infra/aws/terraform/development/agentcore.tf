resource "aws_ecr_repository" "agentcore" {
  name                 = "${local.name}_agentcore"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  encryption_configuration { encryption_type = "AES256" }
  image_scanning_configuration { scan_on_push = true }
}
resource "aws_iam_role" "agentcore" {
  name = "${local.name}_agentcore"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "bedrock-agentcore.amazonaws.com" },
    Condition = {
      StringEquals = { "aws:SourceAccount" = var.aws_account_id },
      ArnLike      = { "aws:SourceArn" = "arn:aws:bedrock-agentcore:${var.aws_region}:${var.aws_account_id}:*" }
    }
  }] })
}
resource "aws_iam_role_policy" "agentcore" {
  name = "model_runtime"
  role = aws_iam_role.agentcore.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"], Resource = aws_ecr_repository.agentcore.arn },
    { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = local.model_arn },
    { Effect = "Allow", Action = ["bedrock:Retrieve"], Resource = aws_bedrockagent_knowledge_base.service.arn },
    { Effect = "Allow", Action = ["logs:CreateLogGroup", "logs:DescribeLogStreams", "logs:CreateLogStream", "logs:PutLogEvents"],
    Resource = "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/bedrock-agentcore/runtimes/${local.name}_agent*" },
    { Effect = "Allow", Action = ["logs:DescribeLogGroups"], Resource = "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:*" }
  ] })
}
output "bedrock" {
  value = {
    model_id           = var.bedrock_model_id
    embedding_model_id = local.embedding_model_id
    knowledge_bucket   = aws_s3_bucket.knowledge.id
    knowledge_base_id  = aws_bedrockagent_knowledge_base.service.id
    data_source_id     = aws_bedrockagent_data_source.service.data_source_id
    vector_index_arn   = aws_s3vectors_index.knowledge.index_arn
    ecr_repository_url = aws_ecr_repository.agentcore.repository_url
    agentcore_role_arn = aws_iam_role.agentcore.arn
  }
}
