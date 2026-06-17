# QUAICU Kernel — ENTERPRISE customer-hosted (GCP) — input variables.
# See README.md. This is a reviewable STARTER module; harden (VPC-SC, private IP, IAM least-priv,
# backups, CMEK on all stores) with your platform team before production.

variable "project_id" {
  type        = string
  description = "The customer's GCP project that will host the kernel (data never leaves it)."
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "Region for Cloud Run, Cloud SQL, and the KMS key ring."
}

variable "image" {
  type        = string
  description = "Kernel container image (e.g. ghcr.io/<owner>/kernel:vX.Y.Z or an Artifact Registry ref)."
}

variable "kernel_tenant_id" {
  type        = string
  description = "The single ENTERPRISE tenant id this dedicated deployment serves."
}

variable "license_token" {
  type        = string
  sensitive   = true
  description = "Offline ENTERPRISE license token issued by QUAICU (gates kernel boot)."
}

variable "db_tier" {
  type        = string
  default     = "db-custom-2-7680"
  description = "Cloud SQL machine tier."
}

variable "db_password" {
  type        = string
  sensitive   = true
  description = "Password for the kernel's Cloud SQL user."
}

variable "api_key_pepper" {
  type        = string
  sensitive   = true
  description = "Server-side pepper for API-key hashing (QUAICU_API_KEY_PEPPER)."
}

variable "min_instances" {
  type        = number
  default     = 1
  description = "Cloud Run min instances (1 avoids cold starts for a dedicated deployment)."
}
