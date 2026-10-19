output "cluster_name" { value = google_container_cluster.lab.name }
output "cluster_version" { value = google_container_cluster.lab.master_version }
output "get_credentials_command" {
  value = "gcloud container clusters get-credentials ${google_container_cluster.lab.name} --zone ${var.zone} --project ${var.project_id}"
}
output "gpu_node_selector" { value = { "cloud.google.com/gke-nodepool" = google_container_node_pool.gpu.name } }
output "cpu_node_selector" { value = { "cloud.google.com/gke-nodepool" = google_container_node_pool.cpu.name } }
output "node_service_account" { value = google_service_account.nodes.email }
