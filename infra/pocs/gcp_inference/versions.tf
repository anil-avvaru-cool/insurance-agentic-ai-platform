terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.29.0"
    }
  }
  backend "s3" {}
}
provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}
