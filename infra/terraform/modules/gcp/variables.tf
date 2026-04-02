variable "project" {
  type    = string
  default = "alis"
}

variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "gcp_project_id" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type    = string
  default = "asia-south1"   # Mumbai
}

# VPC
variable "subnet_cidr" {
  type    = string
  default = "10.0.0.0/20"
}

variable "pods_cidr" {
  type    = string
  default = "10.4.0.0/14"
}

variable "services_cidr" {
  type    = string
  default = "10.8.0.0/20"
}

variable "gke_master_cidr" {
  type    = string
  default = "172.16.0.0/28"
}

# Cloud SQL
variable "sql_tier" {
  type    = string
  default = "db-custom-2-8192"   # 2 vCPUs, 8 GB RAM
}

variable "sql_disk_size_gb" {
  type    = number
  default = 50
}

variable "sql_admin_username" {
  type      = string
  default   = "alis_admin"
  sensitive = true
}

variable "sql_admin_password" {
  type      = string
  sensitive = true
}

# Redis
variable "redis_memory_gb" {
  type    = number
  default = 2
}

# Labels
variable "extra_labels" {
  type    = map(string)
  default = {}
}
