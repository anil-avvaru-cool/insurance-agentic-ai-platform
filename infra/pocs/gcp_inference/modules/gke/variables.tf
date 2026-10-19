variable "name" {
  type = string
}
variable "labels" {
  type = map(string)
}
variable "network_id" {
  type = string
}
variable "subnetwork_id" {
  type = string
}
variable "project_id" {
  type = string
  validation {
    condition     = var.project_id != "YOUR_PROJECT_ID" && can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Supply your existing GCP project ID."
  }
}
variable "region" {
  type = string
}
variable "zone" {
  type = string
}
variable "release_channel" {
  type = string
}
variable "node_image_type" {
  type = string
}
variable "cpu_machine_type" {
  type = string
}
variable "cpu_disk_type" {
  type = string
}
variable "gpu_machine_type" {
  type = string
  validation {
    condition     = var.gpu_machine_type == "g2-standard-4"
    error_message = "The baseline uses g2-standard-4."
  }
}
variable "gpu_type" {
  type = string
  validation {
    condition     = var.gpu_type == "nvidia-l4"
    error_message = "The baseline uses NVIDIA L4."
  }
}
variable "gpu_disk_type" {
  type = string
}
variable "gpu_driver_version" {
  type = string
}
variable "cpu_node_count" {
  type = number
  validation {
    condition     = var.cpu_node_count >= 1 && floor(var.cpu_node_count) == var.cpu_node_count
    error_message = "Supply a positive integer CPU node count."
  }
}
variable "cpu_disk_size_gb" {
  type = number
}
variable "gpu_count_per_node" {
  type = number
  validation {
    condition     = var.gpu_count_per_node == 1
    error_message = "The baseline requires one GPU per node."
  }
}
variable "gpu_node_count" {
  type = number
  validation {
    condition     = var.gpu_node_count == 1
    error_message = "The baseline requires exactly one GPU node."
  }
}
variable "gpu_disk_size_gb" {
  type = number
}
variable "gpu_max_surge" {
  type = number
  validation {
    condition     = var.gpu_max_surge == 0
    error_message = "The baseline requires gpu_max_surge = 0."
  }
}
variable "gpu_max_unavailable" {
  type = number
  validation {
    condition     = var.gpu_max_unavailable == 1
    error_message = "The baseline requires gpu_max_unavailable = 1."
  }
}
variable "gpu_autoscaling" {
  type = bool
  validation {
    condition     = !var.gpu_autoscaling
    error_message = "GPU autoscaling must remain disabled for the baseline."
  }
}
variable "enable_private_nodes" {
  type = bool
}
variable "enable_cloud_nat" {
  type = bool
}
variable "deletion_protection" {
  type = bool
}
variable "master_authorized_cidrs" {
  type = list(string)
  validation {
    condition     = length(var.master_authorized_cidrs) > 0 && alltrue([for c in var.master_authorized_cidrs : can(cidrnetmask(c)) && !contains(["0.0.0.0/0", "192.0.2.1/32"], c)])
    error_message = "Replace the example address with your restricted operator IPv4 CIDR."
  }
}
