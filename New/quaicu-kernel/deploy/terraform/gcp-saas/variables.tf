# QUAICU Kernel — SHARED SaaS plane (Model A, GCP) — input variables.
# See README.md. Codifies the hand-deployed `quaicu-kernel` service (docs/operations/DEPLOY_CLOUD_RUN.md).
# This is a reviewable module; harden (VPC-SC, private IP, CMEK, WAF) with your platform team before
# treating it as the sole source of truth in production.

variable "project_id" {
  type        = string
  description = "GCP project hosting the SaaS plane."
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "Region for Cloud Run + Cloud SQL. Pick per residency zone (see regions/*.tfvars)."
}

variable "service_name" {
  type        = string
  default     = "quaicu-kernel"
  description = "Cloud Run service name (matches the live shared-plane service)."
}

variable "image" {
  type        = string
  description = "Kernel container image (Artifact Registry ref) baked with /etc/quaicu/kernel.saas.toml + per-tier configs."
}

variable "kernel_workers" {
  type        = number
  default     = 4
  description = "Uvicorn workers per instance (KERNEL_WORKERS)."
}

variable "min_instances" {
  type        = number
  default     = 0
  description = "Cloud Run min instances. 0 = scale-to-zero (cheapest free tier); 1 avoids cold starts."
}

variable "max_instances" {
  type        = number
  default     = 10
  description = "Cloud Run max instances."
}

# ── Secrets (values are written into Secret Manager; never commit real values) ──
variable "api_key_pepper" {
  type        = string
  sensitive   = true
  description = "QUAICU_API_KEY_PEPPER — HMAC pepper for API-key hashing. High-entropy; rotating it invalidates all issued keys."
}

variable "jwt_secret" {
  type        = string
  sensitive   = true
  description = "KERNEL_JWT_SECRET — session/JWT signing secret."
}

variable "entitlements_dsn" {
  type        = string
  sensitive   = true
  description = "ENTITLEMENTS_DSN — Cloud SQL DSN (connector-socket form) for the durable entitlements store."
}

variable "account_dsn" {
  type        = string
  sensitive   = true
  description = "ACCOUNT_DSN — Cloud SQL DSN (connector-socket form) for durable accounts (signups survive restart/scale-out)."
}

variable "edge_secret" {
  type        = string
  sensitive   = true
  description = "QUAICU_EDGE_SECRET — shared secret authenticating the Cloudflare Worker's forwarded real client IP (W1-1)."
}

variable "razorpay_key_id" {
  type        = string
  sensitive   = true
  default     = ""
  description = "RAZORPAY_KEY_ID — signup-fee/consultation checkout. Empty disables the fee gate."
}

variable "razorpay_key_secret" {
  type        = string
  sensitive   = true
  default     = ""
  description = "RAZORPAY_KEY_SECRET — payment-signature verification for the signup fee."
}

# ── Cloud SQL (BUSINESS tier durable stores; STARTER is in-memory) ──
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

# ── Zero-egress / sovereignty (W5-3) — OPT-IN, default OFF so a plain apply is unchanged ──
variable "enable_private_egress" {
  type        = bool
  default     = false
  description = "When true, route Cloud Run egress through a Serverless VPC Access connector (private path). Requires `vpc_connector`. See ZERO_EGRESS_VALIDATION.md; the VPC-SC perimeter itself is org-level."
}

variable "vpc_connector" {
  type        = string
  default     = ""
  description = "Serverless VPC Access connector resource id (projects/.../connectors/...). Required when enable_private_egress = true."
}

variable "allow_unauthenticated" {
  type        = bool
  default     = true
  description = "Grant allUsers run.invoker (the plane is internet-facing behind the Cloudflare Worker). Set false for a private-ingress deployment."
}
