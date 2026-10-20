resource "google_service_account" "nodes" {
  account_id   = "${substr(var.name, 0, 24)}-nodes"
  display_name = "Inference lab GKE nodes"
}
resource "google_project_iam_member" "nodes" {
  project = var.project_id
  role    = "roles/container.defaultNodeServiceAccount"
  member  = "serviceAccount:${google_service_account.nodes.email}"
}
resource "google_container_cluster" "lab" {
  name                     = "${var.name}-gke"
  location                 = var.zone
  network                  = var.network_id
  subnetwork               = var.subnetwork_id
  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection      = var.deletion_protection
  resource_labels          = var.labels
  networking_mode          = "VPC_NATIVE"
  release_channel { channel = var.release_channel }
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }
  private_cluster_config {
    enable_private_nodes    = var.enable_private_nodes
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }
  master_authorized_networks_config {
    dynamic "cidr_blocks" {
      for_each = toset(var.master_authorized_cidrs)
      content {
        cidr_block   = cidr_blocks.value
        display_name = "operator"
      }
    }
  }
  workload_identity_config { workload_pool = "${var.project_id}.svc.id.goog" }
  logging_config {
    enable_components = ["SYSTEM_COMPONENTS","WORKLOADS"]    
  }
  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus { enabled = true }
  }
  node_config {
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
  }
  lifecycle {
    precondition {
      condition     = !var.enable_private_nodes || var.enable_cloud_nat
      error_message = "Private nodes need Cloud NAT for model and image downloads."
    }
    precondition {
      condition     = startswith(var.zone, "${var.region}-")
      error_message = "The zone must belong to the selected region."
    }
  }
  depends_on = [google_project_iam_member.nodes]
}
resource "google_container_node_pool" "cpu" {
  name           = "cpu"
  cluster        = google_container_cluster.lab.id
  location       = var.zone
  node_locations = [var.zone]
  node_count     = var.cpu_node_count
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  node_config {
    machine_type    = var.cpu_machine_type
    image_type      = var.node_image_type
    disk_type       = var.cpu_disk_type
    disk_size_gb    = var.cpu_disk_size_gb
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    labels          = merge(var.labels, { workload = "cpu" })
    workload_metadata_config { mode = "GKE_METADATA" }
    shielded_instance_config { enable_secure_boot = true }
  }
}
resource "google_container_node_pool" "gpu" {
  name           = "gpu"
  cluster        = google_container_cluster.lab.id
  location       = var.zone
  node_locations = [var.zone]
  node_count     = var.gpu_node_count
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  upgrade_settings {
    max_surge       = var.gpu_max_surge
    max_unavailable = var.gpu_max_unavailable
  }
  node_config {
    machine_type    = var.gpu_machine_type
    image_type      = var.node_image_type
    disk_type       = var.gpu_disk_type
    disk_size_gb    = var.gpu_disk_size_gb
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    labels          = merge(var.labels, { workload = "gpu" })
    workload_metadata_config { mode = "GKE_METADATA" }
    guest_accelerator {
      type  = var.gpu_type
      count = var.gpu_count_per_node
      gpu_driver_installation_config { gpu_driver_version = var.gpu_driver_version }
    }
    taint {
      key    = "nvidia.com/gpu"
      value  = "present"
      effect = "NO_SCHEDULE"
    }
  }
  depends_on = [google_container_node_pool.cpu]
}
