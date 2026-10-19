variable "name" {
  type = string
}
variable "subnet_cidr" {
  type = string
}
variable "pods_cidr" {
  type = string
}
variable "services_cidr" {
  type = string
}
variable "enable_cloud_nat" {
  type = bool
}
