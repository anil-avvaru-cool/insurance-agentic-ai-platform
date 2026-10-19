resource "google_compute_network" "lab" {
  name                    = "${var.name}-vpc"
  auto_create_subnetworks = false
}
resource "google_compute_subnetwork" "lab" {
  name                     = "${var.name}-subnet"
  network                  = google_compute_network.lab.id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true
  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_cidr
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_cidr
  }
}
resource "google_compute_router" "lab" {
  count   = var.enable_cloud_nat ? 1 : 0
  name    = "${var.name}-router"
  network = google_compute_network.lab.id
}
resource "google_compute_router_nat" "lab" {
  count                              = var.enable_cloud_nat ? 1 : 0
  name                               = "${var.name}-nat"
  router                             = google_compute_router.lab[0].name
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"
  subnetwork {
    name                    = google_compute_subnetwork.lab.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }
}
