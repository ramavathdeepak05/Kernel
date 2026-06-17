# QUAICU Kernel — ENTERPRISE customer-hosted (GCP). Stands up the kernel in the CUSTOMER's project
# on the all-durable kernel.gcp.toml profile: their Cloud KMS (FIPS 140-2 L3 STH signing), their
# Cloud SQL (durable ledger/policy/storage/entitlements), Vertex inference reachable privately. The
# vendor never touches customer data; QUAICU only issues the offline license token.

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = { source = "hashicorp/google", version = ">= 5.0" }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  required_apis = [
    "run.googleapis.com", "sqladmin.googleapis.com", "cloudkms.googleapis.com",
    "secretmanager.googleapis.com", "aiplatform.googleapis.com", "artifactregistry.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each           = toset(local.required_apis)
  service            = each.value
  disable_on_destroy = false
}

# ── Runtime service account (least-privilege; keyless / Workload Identity) ─────
resource "google_service_account" "kernel" {
  account_id   = "quaicu-kernel"
  display_name = "QUAICU Kernel runtime"
}

# Sign/verify with the ledger KMS key; read/write Cloud SQL; call Vertex; read secrets.
resource "google_kms_crypto_key_iam_member" "signer" {
  crypto_key_id = google_kms_crypto_key.ledger.id
  role          = "roles/cloudkms.signerVerifier"
  member        = "serviceAccount:${google_service_account.kernel.email}"
}

resource "google_project_iam_member" "roles" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/aiplatform.user",
    "roles/secretmanager.secretAccessor",
    "roles/logging.logWriter",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.kernel.email}"
}

# ── Cloud KMS — Ed25519 has no GCP support, so ECDSA P-256 (matches gcp_kms_ledger / ADR-0012) ──
resource "google_kms_key_ring" "ring" {
  name       = "quaicu-ledger"
  location   = var.region
  depends_on = [google_project_service.apis]
}

resource "google_kms_crypto_key" "ledger" {
  name     = "sth-signer"
  key_ring = google_kms_key_ring.ring.id
  purpose  = "ASYMMETRIC_SIGN"
  version_template {
    algorithm        = "EC_SIGN_P256_SHA256"
    protection_level = "HSM" # FIPS 140-2 Level 3
  }
  # The signing key must never be destroyed casually — STHs become unverifiable. Block on destroy.
  lifecycle { prevent_destroy = true }
}

# ── Cloud SQL (Postgres) — durable ledger / policy / storage / entitlements / accounts ─────
resource "google_sql_database_instance" "pg" {
  name             = "quaicu-pg"
  database_version = "POSTGRES_16"
  region           = var.region
  depends_on       = [google_project_service.apis]
  settings {
    tier              = var.db_tier
    availability_type = "REGIONAL" # multi-AZ failover
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
  }
  deletion_protection = true
}

resource "google_sql_database" "db" {
  name     = "quaicu"
  instance = google_sql_database_instance.pg.name
}

resource "google_sql_user" "kernel" {
  name     = "quaicu"
  instance = google_sql_database_instance.pg.name
  password = var.db_password
}

# ── Secrets (env → Cloud Run) ──────────────────────────────────────────────────
resource "google_secret_manager_secret" "pepper" {
  secret_id = "QUAICU_API_KEY_PEPPER"
  replication { auto {} }
}
resource "google_secret_manager_secret_version" "pepper" {
  secret      = google_secret_manager_secret.pepper.id
  secret_data = var.api_key_pepper
}

resource "google_secret_manager_secret" "license" {
  secret_id = "KERNEL_LICENSE_TOKEN"
  replication { auto {} }
}
resource "google_secret_manager_secret_version" "license" {
  secret      = google_secret_manager_secret.license.id
  secret_data = var.license_token
}

locals {
  # Cloud Run → Cloud SQL via the built-in connector socket.
  dsn = "postgresql://quaicu:${var.db_password}@/quaicu?host=/cloudsql/${google_sql_database_instance.pg.connection_name}"
}

resource "google_secret_manager_secret" "dsn" {
  secret_id = "KERNEL_DSN"
  replication { auto {} }
}
resource "google_secret_manager_secret_version" "dsn" {
  secret      = google_secret_manager_secret.dsn.id
  secret_data = local.dsn
}

# ── Cloud Run service (single-kernel, license-gated, all-durable kernel.gcp.toml) ──
resource "google_cloud_run_v2_service" "kernel" {
  name     = "quaicu-kernel"
  location = var.region
  template {
    service_account = google_service_account.kernel.email
    scaling { min_instance_count = var.min_instances }
    volumes {
      name = "cloudsql"
      cloud_sql_instance { instances = [google_sql_database_instance.pg.connection_name] }
    }
    containers {
      image = var.image
      ports { container_port = 8080 }
      # kernel.gcp.toml must be present in the image at /etc/quaicu/ (bake it, or mount via a Secret).
      env { name = "KERNEL_CONFIG"     value = "/etc/quaicu/kernel.gcp.toml" }
      env { name = "KERNEL_TENANT_ID"  value = var.kernel_tenant_id }
      env { name = "GCP_PROJECT"       value = var.project_id }
      env { name = "GCP_LOCATION"      value = var.region }
      env { name = "KERNEL_WORKERS"    value = "4" }
      env {
        name = "KERNEL_DSN"
        value_source { secret_key_ref { secret = google_secret_manager_secret.dsn.secret_id      version = "latest" } }
      }
      env {
        name = "QUAICU_API_KEY_PEPPER"
        value_source { secret_key_ref { secret = google_secret_manager_secret.pepper.secret_id   version = "latest" } }
      }
      env {
        name = "KERNEL_LICENSE_TOKEN"
        value_source { secret_key_ref { secret = google_secret_manager_secret.license.secret_id  version = "latest" } }
      }
      volume_mounts { name = "cloudsql" mount_path = "/cloudsql" }
    }
  }
  depends_on = [google_project_iam_member.roles]
}
