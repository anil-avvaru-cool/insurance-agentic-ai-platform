terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.27.0"
    }
  }
}
provider "aws" {
  region              = var.infrastructure.aws_region
  allowed_account_ids = [var.infrastructure.aws_account_id]
  default_tags {
    tags = { project = var.infrastructure.project_name, environment = var.infrastructure.environment, managed_by = "terraform", owner = var.infrastructure.owner }
  }
}
