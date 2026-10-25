output "cluster_name" { value = module.gke.cluster_name }
output "cluster_version" { value = module.gke.cluster_version }
output "get_credentials_command" { value = module.gke.get_credentials_command }
output "gpu_node_selector" { value = module.gke.gpu_node_selector }
output "cpu_node_selector" { value = module.gke.cpu_node_selector }
output "node_service_account" { value = module.gke.node_service_account }
output "dashboard_id" {
  value = one(google_monitoring_dashboard.inference[*].id)
}
