locals {
  # GCP API names forbid underscores; Terraform identifiers and labels retain them.
  name   = replace("${var.project_name}_${var.environment}", "_", "-")
  labels = { project = var.project_name, environment = var.environment, owner = var.owner, managed_by = "terraform" }
}
resource "google_project_service" "required" {
  for_each           = toset(["compute.googleapis.com", "container.googleapis.com", "iam.googleapis.com", "logging.googleapis.com", "monitoring.googleapis.com"])
  service            = each.value
  disable_on_destroy = false
}

module "network" {
  source           = "./modules/network"
  name             = local.name
  subnet_cidr      = var.subnet_cidr
  pods_cidr        = var.pods_cidr
  services_cidr    = var.services_cidr
  enable_cloud_nat = var.enable_cloud_nat
  depends_on       = [google_project_service.required]
}

module "gke" {
  source                  = "./modules/gke"
  name                    = local.name
  labels                  = local.labels
  network_id              = module.network.network_id
  subnetwork_id           = module.network.subnetwork_id
  project_id              = var.project_id
  region                  = var.region
  zone                    = var.zone
  release_channel         = var.release_channel
  node_image_type         = var.node_image_type
  cpu_machine_type        = var.cpu_machine_type
  cpu_disk_type           = var.cpu_disk_type
  gpu_machine_type        = var.gpu_machine_type
  gpu_type                = var.gpu_type
  gpu_disk_type           = var.gpu_disk_type
  gpu_driver_version      = var.gpu_driver_version
  cpu_node_count          = var.cpu_node_count
  cpu_disk_size_gb        = var.cpu_disk_size_gb
  gpu_count_per_node      = var.gpu_count_per_node
  gpu_node_count          = var.gpu_node_count
  gpu_disk_size_gb        = var.gpu_disk_size_gb
  gpu_max_surge           = var.gpu_max_surge
  gpu_max_unavailable     = var.gpu_max_unavailable
  gpu_autoscaling         = var.gpu_autoscaling
  enable_private_nodes    = var.enable_private_nodes
  enable_cloud_nat        = var.enable_cloud_nat
  deletion_protection     = var.deletion_protection
  master_authorized_cidrs = var.master_authorized_cidrs
  depends_on              = [google_project_service.required]
}
