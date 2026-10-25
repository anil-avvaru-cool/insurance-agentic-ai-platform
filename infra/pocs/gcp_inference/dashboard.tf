resource "google_monitoring_dashboard" "inference" {
  count   = var.enable_dashboards ? 1 : 0
  project = var.project_id
  dashboard_json = templatefile("${path.module}/dashboards/inference.json.tftpl", {
    display_name    = "${var.project_name}_${var.environment}_inference"
    project_id      = var.project_id
    cluster_name    = "${local.name}-gke"
    location        = var.zone
    namespace       = "inference-lab"
    kv_cache_metric = var.dashboard_kv_cache_metric
  })
  depends_on = [google_project_service.required]
}
