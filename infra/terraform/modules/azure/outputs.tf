output "resource_group_name" {
  value = azurerm_resource_group.alis.name
}

output "aks_cluster_name" {
  value = azurerm_kubernetes_cluster.alis.name
}

output "aks_kube_config" {
  value     = azurerm_kubernetes_cluster.alis.kube_config_raw
  sensitive = true
}

output "pg_fqdn" {
  value = azurerm_postgresql_flexible_server.alis.fqdn
}

output "redis_hostname" {
  value = azurerm_redis_cache.alis.hostname
}

output "redis_primary_key" {
  value     = azurerm_redis_cache.alis.primary_access_key
  sensitive = true
}

output "storage_account_name" {
  value = azurerm_storage_account.alis.name
}

output "database_url" {
  value     = "postgresql://${var.pg_admin_username}:${var.pg_admin_password}@${azurerm_postgresql_flexible_server.alis.fqdn}:5432/alis_control?sslmode=require"
  sensitive = true
}
