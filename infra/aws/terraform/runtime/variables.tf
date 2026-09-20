variable "infrastructure" {
  description = "Contract exported by the applied development infrastructure root."
  type = object({
    aws_region         = string
    aws_account_id     = string
    project_name       = string
    environment        = string
    owner              = string
    model_id           = string
    knowledge_base_id  = string
    ecr_repository_url = string
    agentcore_role_arn = string
    worker_role_name   = string
  })
  validation {
    condition     = var.infrastructure.environment == "development" && can(regex("^[0-9]{12}$", var.infrastructure.aws_account_id))
    error_message = "Use development infrastructure with a twelve digit AWS account ID."
  }
  validation {
    condition     = startswith(var.infrastructure.ecr_repository_url, "${var.infrastructure.aws_account_id}.dkr.ecr.${var.infrastructure.aws_region}.amazonaws.com/") && startswith(var.infrastructure.agentcore_role_arn, "arn:aws:iam::${var.infrastructure.aws_account_id}:role/")
    error_message = "The ECR repository and execution role must belong to the configured account and region."
  }
}
locals {
  name = "${var.infrastructure.project_name}_${var.infrastructure.environment}"
}
variable "agentcore_image_digest" {
  description = "Immutable ECR image digest, including sha256:."
  type        = string
  validation {
    condition     = can(regex("^sha256:[a-f0-9]{64}$", var.agentcore_image_digest))
    error_message = "Supply an image digest sha256: followed by 64 lowercase hex characters."
  }
}
