output "service_url" {
  value       = google_cloud_run_v2_service.kernel.uri
  description = "The kernel's HTTPS URL."
}

output "kms_key" {
  value       = google_kms_crypto_key.ledger.id
  description = "The Cloud KMS ECDSA-P256 STH signing key (matches kernel.gcp.toml [ledger])."
}

output "sql_connection_name" {
  value       = google_sql_database_instance.pg.connection_name
  description = "Cloud SQL connection name (PROJECT:REGION:INSTANCE)."
}

output "runtime_service_account" {
  value       = google_service_account.kernel.email
  description = "The kernel's runtime service account (keyless / ADC)."
}
