# =============================================================================
# ALIS SaaS — Azure Module
#
# Provisions:
#   - Resource Group
#   - AKS Cluster (managed node pools)
#   - Azure Database for PostgreSQL Flexible Server
#   - Azure Cache for Redis
#   - Azure Blob Storage (system-level)
#   - Azure DNS Zone + wildcard
#   - Azure Key Vault (for ALIS_MASTER_KEY, DB passwords)
# =============================================================================

terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

# ---------------------------------------------------------------------------
# Resource Group
# ---------------------------------------------------------------------------

resource "azurerm_resource_group" "alis" {
  name     = "${var.project}-${var.environment}-rg"
  location = var.location
  tags     = local.tags
}

# ---------------------------------------------------------------------------
# AKS Cluster
# ---------------------------------------------------------------------------

resource "azurerm_kubernetes_cluster" "alis" {
  name                = "${var.project}-${var.environment}-aks"
  location            = azurerm_resource_group.alis.location
  resource_group_name = azurerm_resource_group.alis.name
  dns_prefix          = "${var.project}-${var.environment}"

  kubernetes_version = var.aks_version

  default_node_pool {
    name                = "app"
    vm_size             = var.aks_app_vm_size
    min_count           = var.aks_app_min_count
    max_count           = var.aks_app_max_count
    enable_auto_scaling = true
    vnet_subnet_id      = azurerm_subnet.aks.id

    node_labels = {
      role = "app"
    }
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin    = "azure"
    network_policy    = "calico"
    load_balancer_sku = "standard"
  }

  tags = local.tags
}

resource "azurerm_kubernetes_cluster_node_pool" "worker" {
  name                  = "worker"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.alis.id
  vm_size               = var.aks_worker_vm_size
  min_count             = var.aks_worker_min_count
  max_count             = var.aks_worker_max_count
  enable_auto_scaling   = true
  vnet_subnet_id        = azurerm_subnet.aks.id

  node_labels = {
    role = "worker"
  }

  node_taints = ["workload=celery:NoSchedule"]

  tags = local.tags
}

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

resource "azurerm_virtual_network" "alis" {
  name                = "${var.project}-${var.environment}-vnet"
  address_space       = [var.vnet_address_space]
  location            = azurerm_resource_group.alis.location
  resource_group_name = azurerm_resource_group.alis.name
  tags                = local.tags
}

resource "azurerm_subnet" "aks" {
  name                 = "aks-subnet"
  resource_group_name  = azurerm_resource_group.alis.name
  virtual_network_name = azurerm_virtual_network.alis.name
  address_prefixes     = [var.aks_subnet_cidr]
}

resource "azurerm_subnet" "db" {
  name                 = "db-subnet"
  resource_group_name  = azurerm_resource_group.alis.name
  virtual_network_name = azurerm_virtual_network.alis.name
  address_prefixes     = [var.db_subnet_cidr]

  delegation {
    name = "pg-delegation"
    service_delegation {
      name = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action",
      ]
    }
  }
}

resource "azurerm_subnet" "redis" {
  name                 = "redis-subnet"
  resource_group_name  = azurerm_resource_group.alis.name
  virtual_network_name = azurerm_virtual_network.alis.name
  address_prefixes     = [var.redis_subnet_cidr]
}

# ---------------------------------------------------------------------------
# PostgreSQL Flexible Server
# ---------------------------------------------------------------------------

resource "azurerm_private_dns_zone" "pg" {
  name                = "${var.project}-${var.environment}.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.alis.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "pg" {
  name                  = "pg-vnet-link"
  private_dns_zone_name = azurerm_private_dns_zone.pg.name
  resource_group_name   = azurerm_resource_group.alis.name
  virtual_network_id    = azurerm_virtual_network.alis.id
}

resource "azurerm_postgresql_flexible_server" "alis" {
  name                   = "${var.project}-${var.environment}-pg"
  resource_group_name    = azurerm_resource_group.alis.name
  location               = azurerm_resource_group.alis.location
  version                = "15"
  administrator_login    = var.pg_admin_username
  administrator_password = var.pg_admin_password

  delegated_subnet_id = azurerm_subnet.db.id
  private_dns_zone_id = azurerm_private_dns_zone.pg.id

  sku_name   = var.pg_sku_name
  storage_mb = var.pg_storage_mb

  backup_retention_days        = var.environment == "prod" ? 35 : 7
  geo_redundant_backup_enabled = var.environment == "prod"

  high_availability {
    mode = var.environment == "prod" ? "ZoneRedundant" : "Disabled"
  }

  tags = local.tags

  depends_on = [azurerm_private_dns_zone_virtual_network_link.pg]
}

resource "azurerm_postgresql_flexible_server_database" "control" {
  name      = "alis_control"
  server_id = azurerm_postgresql_flexible_server.alis.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# ---------------------------------------------------------------------------
# Azure Cache for Redis
# ---------------------------------------------------------------------------

resource "azurerm_redis_cache" "alis" {
  name                = "${var.project}-${var.environment}-redis"
  resource_group_name = azurerm_resource_group.alis.name
  location            = azurerm_resource_group.alis.location

  capacity            = var.redis_capacity
  family              = var.redis_family
  sku_name            = var.redis_sku
  enable_non_ssl_port = false
  minimum_tls_version = "1.2"

  subnet_id = azurerm_subnet.redis.id

  redis_configuration {
    maxmemory_policy = "allkeys-lru"
  }

  tags = local.tags
}

# ---------------------------------------------------------------------------
# Azure Blob Storage
# ---------------------------------------------------------------------------

resource "azurerm_storage_account" "alis" {
  name                     = "${var.project}${var.environment}sa"
  resource_group_name      = azurerm_resource_group.alis.name
  location                 = azurerm_resource_group.alis.location
  account_tier             = "Standard"
  account_replication_type = var.environment == "prod" ? "GRS" : "LRS"
  min_tls_version          = "TLS1_2"

  blob_properties {
    versioning_enabled = true
  }

  tags = local.tags
}

resource "azurerm_storage_container" "system" {
  name                  = "system"
  storage_account_name  = azurerm_storage_account.alis.name
  container_access_type = "private"
}

# ---------------------------------------------------------------------------
# Locals
# ---------------------------------------------------------------------------

locals {
  tags = merge(var.extra_tags, {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}
