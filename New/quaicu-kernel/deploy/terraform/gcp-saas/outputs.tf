output "service_url" {
  value       = google_cloud_run_v2_service.kernel.uri
  description = "The SaaS-plane kernel's HTTPS URL (point the Cloudflare Worker origin here)."
}

output "service_name" {
  value       = google_cloud_run_v2_service.kernel.name
  description = "Cloud Run service name."
}

output "region" {
  value       = var.region
  description = "Residency zone this stack was applied to."
}

output "sql_connection_name" {
  value       = google_sql_database_instance.pg.connection_name
  description = "Cloud SQL connection name (PROJECT:REGION:INSTANCE) for the DSN connector socket."
}

output "runtime_service_account" {
  value       = google_service_account.kernel.email
  description = "The kernel's runtime service account (keyless / ADC)."
}

output "private_egress_enabled" {
  value       = var.enable_private_egress
  description = "Whether Cloud Run egress is routed through the VPC connector (W5-3)."
}
