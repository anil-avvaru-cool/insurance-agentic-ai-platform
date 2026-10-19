output "network_id" { value = google_compute_network.lab.id }
output "subnetwork_id" {
  value      = google_compute_subnetwork.lab.id
  depends_on = [google_compute_router_nat.lab]
}
