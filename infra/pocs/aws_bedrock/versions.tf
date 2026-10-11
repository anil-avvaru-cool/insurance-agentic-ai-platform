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
  region              = var.aws_region
  allowed_account_ids = [var.aws_account_id]
  default_tags {
    tags = { project = var.project_name, environment = var.environment, managed_by = "terraform", owner = var.owner }
  }
}
variable "aws_region" { type = string }
variable "aws_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "Supply the target twelve digit AWS account ID."
  }
}
variable "project_name" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{2,24}$", var.project_name))
    error_message = "Use 3 to 25 lowercase letters, numbers or underscores, beginning with a letter."
  }
}
variable "environment" {
  type = string
  validation {
    condition     = var.environment == "development"
    error_message = "These roots are scoped to development. Create separate roots and identities for later environments."
  }
}
variable "owner" { type = string }
locals {
  name = "${var.project_name}_${var.environment}"
  # S3 bucket names forbid underscores: omit separators for those AWS names.
  aws_name = replace(local.name, "_", "")
}
