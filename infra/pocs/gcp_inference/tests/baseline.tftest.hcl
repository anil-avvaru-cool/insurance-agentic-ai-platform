mock_provider "google" {}

variables {
  project_name            = "inference_lab"
  environment             = "development"
  owner                   = "insurance_platform_team"
  region                  = "us-central1"
  zone                    = "us-central1-a"
  release_channel         = "REGULAR"
  node_image_type         = "COS_CONTAINERD"
  cpu_machine_type        = "e2-standard-2"
  cpu_node_count          = 1
  cpu_disk_type           = "pd-balanced"
  cpu_disk_size_gb        = 50
  gpu_machine_type        = "g2-standard-4"
  gpu_type                = "nvidia-l4"
  gpu_count_per_node      = 1
  gpu_node_count          = 1
  gpu_disk_type           = "pd-balanced"
  gpu_disk_size_gb        = 100
  gpu_driver_version      = "DEFAULT"
  gpu_autoscaling         = false
  gpu_max_surge           = 0
  gpu_max_unavailable     = 1
  subnet_cidr             = "10.40.0.0/24"
  pods_cidr               = "10.44.0.0/16"
  services_cidr           = "10.48.0.0/20"
  enable_private_nodes    = true
  enable_cloud_nat        = true
  deletion_protection     = false
  project_id              = "inference-lab-test"
  master_authorized_cidrs = ["198.51.100.10/32"]
}

run "fixed_baseline" {
  command = plan
  module { source = "./modules/gke" }
  variables {
    name          = "inference-lab-development"
    labels        = { project = "inference_lab", environment = "development" }
    network_id    = "test-network"
    subnetwork_id = "test-subnetwork"
  }

  assert {
    condition     = google_container_cluster.lab.location == var.zone && google_container_cluster.lab.remove_default_node_pool
    error_message = "Use a zonal cluster with the default pool removed."
  }
  assert {
    condition     = google_container_node_pool.gpu.node_count == 1 && length(google_container_node_pool.gpu.node_locations) == 1 && google_container_node_pool.gpu.node_config[0].guest_accelerator[0].count == 1
    error_message = "The baseline must provision exactly one GPU node with one GPU in one zone."
  }
  assert {
    condition     = length(google_container_node_pool.gpu.autoscaling) == 0 && google_container_node_pool.gpu.upgrade_settings[0].max_surge == 0
    error_message = "The baseline must not autoscale or add surge GPU nodes."
  }
  assert {
    condition     = google_container_cluster.lab.private_cluster_config[0].enable_private_nodes
    error_message = "Baseline nodes must remain private."
  }
}

run "reject_gpu_scaling" {
  command = plan
  variables { gpu_node_count = 2 }
  expect_failures = [var.gpu_node_count]
}

run "reject_public_access" {
  command = plan
  variables { master_authorized_cidrs = ["0.0.0.0/0"] }
  expect_failures = [var.master_authorized_cidrs]
}

run "network_baseline" {
  command = plan
  module { source = "./modules/network" }
  variables { name = "inference-lab-development" }
  assert {
    condition     = !google_compute_network.lab.auto_create_subnetworks && google_compute_subnetwork.lab.private_ip_google_access && length(google_compute_subnetwork.lab.secondary_ip_range) == 2 && length(google_compute_router_nat.lab) == 1
    error_message = "Use a dedicated VPC, private Google access, pod/service ranges, and NAT."
  }
}
run "network_without_nat" {
  command = plan
  module { source = "./modules/network" }
  variables {
    name             = "inference-lab-development"
    enable_cloud_nat = false
  }
  assert {
    condition     = length(google_compute_router.lab) == 0 && length(google_compute_router_nat.lab) == 0
    error_message = "Disabling NAT must omit both the router and NAT."
  }
}
run "reject_gpu_surge" {
  command = plan
  variables { gpu_max_surge = 1 }
  expect_failures = [var.gpu_max_surge]
}
run "reject_gpu_unavailable" {
  command = plan
  variables { gpu_max_unavailable = 0 }
  expect_failures = [var.gpu_max_unavailable]
}

run "root_wiring" {
  command = plan
  assert {
    condition     = output.cluster_name == "${replace("${var.project_name}_${var.environment}", "_", "-")}-gke" && output.cpu_node_selector["cloud.google.com/gke-nodepool"] == "cpu" && output.gpu_node_selector["cloud.google.com/gke-nodepool"] == "gpu"
    error_message = "The root must preserve cluster naming and node selector outputs."
  }
  assert {
    condition     = output.get_credentials_command == "gcloud container clusters get-credentials ${output.cluster_name} --zone ${var.zone} --project ${var.project_id}"
    error_message = "The credentials command must target the selected project and zone."
  }
}

run "dashboard_before_workload" {
  command = plan
  assert {
    condition     = length(google_monitoring_dashboard.inference) == 1 && length(jsondecode(google_monitoring_dashboard.inference[0].dashboard_json).gridLayout.widgets) == 12
    error_message = "Provision the dashboard and all panels without Kubernetes resources."
  }
  assert {
    condition = alltrue([for widget in jsondecode(google_monitoring_dashboard.inference[0].dashboard_json).gridLayout.widgets : alltrue([
      for dataset in try(widget.xyChart.dataSets, []) :
      strcontains(try(dataset.timeSeriesQuery.prometheusQuery, dataset.timeSeriesQuery.timeSeriesFilter.filter), var.project_id) &&
      strcontains(try(dataset.timeSeriesQuery.prometheusQuery, dataset.timeSeriesQuery.timeSeriesFilter.filter), "inference-lab-development-gke") &&
      strcontains(try(dataset.timeSeriesQuery.prometheusQuery, dataset.timeSeriesQuery.timeSeriesFilter.filter), var.zone)
    ])])
    error_message = "Every chart query must be scoped to the lab project, cluster and location."
  }
}

run "dashboard_disabled" {
  command = plan
  variables { enable_dashboards = false }
  assert {
    condition     = length(google_monitoring_dashboard.inference) == 0 && output.dashboard_id == null
    error_message = "Disabling dashboards must omit the resource and its ID."
  }
}

run "legacy_cache_metric" {
  command = plan
  variables { dashboard_kv_cache_metric = "vllm:gpu_cache_usage_perc" }
  assert {
    condition     = strcontains(jsondecode(google_monitoring_dashboard.inference[0].dashboard_json).gridLayout.widgets[6].xyChart.dataSets[0].timeSeriesQuery.prometheusQuery, "vllm:gpu_cache_usage_perc{")
    error_message = "The dashboard must support the pinned release's legacy cache metric."
  }
}
