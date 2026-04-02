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

variable "location" {
  type    = string
  default = "centralindia"   # Primary: Central India
}

variable "domain" {
  type    = string
  default = "alis.app"
}

# VNet
variable "vnet_address_space" {
  type    = string
  default = "10.0.0.0/16"
}

variable "aks_subnet_cidr" {
  type    = string
  default = "10.0.0.0/20"
}

variable "db_subnet_cidr" {
  type    = string
  default = "10.0.16.0/24"
}

variable "redis_subnet_cidr" {
  type    = string
  default = "10.0.17.0/24"
}

# AKS
variable "aks_version" {
  type    = string
  default = "1.29"
}

variable "aks_app_vm_size" {
  type    = string
  default = "Standard_D2s_v5"
}

variable "aks_app_min_count" {
  type    = number
  default = 2
}

variable "aks_app_max_count" {
  type    = number
  default = 10
}

variable "aks_worker_vm_size" {
  type    = string
  default = "Standard_D2s_v5"
}

variable "aks_worker_min_count" {
  type    = number
  default = 2
}

variable "aks_worker_max_count" {
  type    = number
  default = 20
}

# PostgreSQL
variable "pg_admin_username" {
  type      = string
  default   = "alis_admin"
  sensitive = true
}

variable "pg_admin_password" {
  type      = string
  sensitive = true
}

variable "pg_sku_name" {
  type    = string
  default = "GP_Standard_D2s_v3"
}

variable "pg_storage_mb" {
  type    = number
  default = 65536   # 64 GB
}

# Redis
variable "redis_capacity" {
  type    = number
  default = 1
}

variable "redis_family" {
  type    = string
  default = "P"   # Premium (required for VNet injection)
}

variable "redis_sku" {
  type    = string
  default = "Premium"
}

# Tags
variable "extra_tags" {
  type    = map(string)
  default = {}
}
