output "gke_cluster_name" {
  value = google_container_cluster.alis.name
}

output "gke_cluster_endpoint" {
  value     = google_container_cluster.alis.endpoint
  sensitive = true
}

output "sql_connection_name" {
  value = google_sql_database_instance.alis.connection_name
}

output "sql_private_ip" {
  value = google_sql_database_instance.alis.private_ip_address
}

output "redis_host" {
  value = google_redis_instance.alis.host
}

output "redis_port" {
  value = google_redis_instance.alis.port
}

output "gcs_system_bucket" {
  value = google_storage_bucket.system.name
}

output "kms_key_id" {
  value = google_kms_crypto_key.alis.id
}

output "database_url" {
  value     = "postgresql://${var.sql_admin_username}:${var.sql_admin_password}@${google_sql_database_instance.alis.private_ip_address}:5432/alis_control"
  sensitive = true
}
