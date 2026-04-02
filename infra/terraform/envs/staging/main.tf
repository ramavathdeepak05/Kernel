# =============================================================================
# ALIS SaaS — Staging Environment (Azure)
#
# Staging uses Azure to validate multi-cloud portability.
# =============================================================================

terraform {
  required_version = ">= 1.5"

  backend "azurerm" {
    resource_group_name  = "alis-terraform-rg"
    storage_account_name = "alisterraformstate"
    container_name       = "tfstate"
    key                  = "staging/terraform.tfstate"
  }
}

provider "azurerm" {
  features {}
}

module "azure" {
  source = "../../modules/azure"

  project     = "alis"
  environment = "staging"
  location    = var.azure_location

  # Mid-size for staging
  aks_app_vm_size    = "Standard_D2s_v5"
  aks_app_min_count  = 2
  aks_app_max_count  = 5
  aks_worker_vm_size = "Standard_D2s_v5"
  aks_worker_min_count = 1
  aks_worker_max_count = 8

  pg_sku_name      = "GP_Standard_D2s_v3"
  pg_storage_mb    = 65536
  pg_admin_password = var.pg_admin_password

  redis_capacity = 1
  redis_family   = "P"
  redis_sku      = "Premium"
}

variable "azure_location" {
  type    = string
  default = "centralindia"
}

variable "pg_admin_password" {
  type      = string
  sensitive = true
}

output "aks_cluster_name" {
  value = module.azure.aks_cluster_name
}

output "pg_fqdn" {
  value = module.azure.pg_fqdn
}
