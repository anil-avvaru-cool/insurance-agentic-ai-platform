moved {
  from = google_compute_network.lab
  to   = module.network.google_compute_network.lab
}
moved {
  from = google_compute_subnetwork.lab
  to   = module.network.google_compute_subnetwork.lab
}
moved {
  from = google_compute_router.lab
  to   = module.network.google_compute_router.lab
}
moved {
  from = google_compute_router_nat.lab
  to   = module.network.google_compute_router_nat.lab
}
moved {
  from = google_service_account.nodes
  to   = module.gke.google_service_account.nodes
}
moved {
  from = google_project_iam_member.nodes
  to   = module.gke.google_project_iam_member.nodes
}
moved {
  from = google_container_cluster.lab
  to   = module.gke.google_container_cluster.lab
}
moved {
  from = google_container_node_pool.cpu
  to   = module.gke.google_container_node_pool.cpu
}
moved {
  from = google_container_node_pool.gpu
  to   = module.gke.google_container_node_pool.gpu
}
