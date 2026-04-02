# =============================================================================
# ALIS SaaS — GCP Module
#
# Provisions:
#   - GKE Autopilot Cluster
#   - Cloud SQL for PostgreSQL (HA)
#   - Memorystore for Redis
#   - GCS Bucket (system-level)
#   - Cloud DNS Zone
#   - Cloud KMS Key
# =============================================================================

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# ---------------------------------------------------------------------------
# GKE Autopilot
# ---------------------------------------------------------------------------

resource "google_container_cluster" "alis" {
  name     = "${var.project}-${var.environment}"
  location = var.region
  project  = var.gcp_project_id

  enable_autopilot = true

  network    = google_compute_network.alis.id
  subnetwork = google_compute_subnetwork.alis.id

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = var.environment == "prod"
    master_ipv4_cidr_block  = var.gke_master_cidr
  }

  release_channel {
    channel = var.environment == "prod" ? "STABLE" : "REGULAR"
  }

  resource_labels = local.labels
}

# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------

resource "google_compute_network" "alis" {
  name                    = "${var.project}-${var.environment}-vpc"
  project                 = var.gcp_project_id
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "alis" {
  name          = "${var.project}-${var.environment}-subnet"
  project       = var.gcp_project_id
  ip_cidr_range = var.subnet_cidr
  region        = var.region
  network       = google_compute_network.alis.id

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_cidr
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_cidr
  }

  private_ip_google_access = true
}

# ---------------------------------------------------------------------------
# Cloud SQL for PostgreSQL
# ---------------------------------------------------------------------------

resource "google_sql_database_instance" "alis" {
  name             = "${var.project}-${var.environment}-pg"
  project          = var.gcp_project_id
  region           = var.region
  database_version = "POSTGRES_15"

  deletion_protection = var.environment == "prod"

  settings {
    tier              = var.sql_tier
    availability_type = var.environment == "prod" ? "REGIONAL" : "ZONAL"

    disk_autoresize = true
    disk_size       = var.sql_disk_size_gb
    disk_type       = "PD_SSD"

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = var.environment == "prod"
      backup_retention_settings {
        retained_backups = var.environment == "prod" ? 30 : 7
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.alis.id
    }

    database_flags {
      name  = "max_connections"
      value = "200"
    }

    user_labels = local.labels
  }
}

resource "google_sql_database" "control" {
  name     = "alis_control"
  instance = google_sql_database_instance.alis.name
  project  = var.gcp_project_id
}

resource "google_sql_user" "admin" {
  name     = var.sql_admin_username
  instance = google_sql_database_instance.alis.name
  password = var.sql_admin_password
  project  = var.gcp_project_id
}

# ---------------------------------------------------------------------------
# Memorystore for Redis
# ---------------------------------------------------------------------------

resource "google_redis_instance" "alis" {
  name               = "${var.project}-${var.environment}-redis"
  project            = var.gcp_project_id
  region             = var.region
  tier               = var.environment == "prod" ? "STANDARD_HA" : "BASIC"
  memory_size_gb     = var.redis_memory_gb
  redis_version      = "REDIS_7_0"
  authorized_network = google_compute_network.alis.id

  transit_encryption_mode = "SERVER_AUTHENTICATION"

  labels = local.labels
}

# ---------------------------------------------------------------------------
# GCS — System bucket
# ---------------------------------------------------------------------------

resource "google_storage_bucket" "system" {
  name          = "${var.project}-${var.environment}-system"
  project       = var.gcp_project_id
  location      = var.region
  storage_class = "STANDARD"

  versioning {
    enabled = true
  }

  uniform_bucket_level_access = true

  labels = local.labels
}

# ---------------------------------------------------------------------------
# Cloud KMS
# ---------------------------------------------------------------------------

resource "google_kms_key_ring" "alis" {
  name     = "${var.project}-${var.environment}"
  project  = var.gcp_project_id
  location = var.region
}

resource "google_kms_crypto_key" "alis" {
  name     = "alis-master"
  key_ring = google_kms_key_ring.alis.id

  rotation_period = "7776000s"   # 90 days

  lifecycle {
    prevent_destroy = true
  }
}

# ---------------------------------------------------------------------------
# Locals
# ---------------------------------------------------------------------------

locals {
  labels = merge(var.extra_labels, {
    project     = var.project
    environment = var.environment
    managed-by  = "terraform"
  })
}
