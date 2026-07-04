# QUAICU Kernel — SHARED SaaS plane (Model A, GCP). Codifies the hand-deployed `quaicu-kernel` Cloud
# Run service (docs/operations/DEPLOY_CLOUD_RUN.md): the multi-tenant shared plane (STARTER free +
# BUSINESS paid), its Cloud SQL durable stores, and its Secret Manager env. Region-parameterized so the
# same module stands up an EU / India / Gulf residency zone (see regions/*.tfvars). Mirrors the proven
# gcp-enterprise module's patterns.

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
    "run.googleapis.com", "sqladmin.googleapis.com",
    "secretmanager.googleapis.com", "artifactregistry.googleapis.com",
  ]

  # Secret env vars → Cloud Run. Razorpay keys are included only when supplied (fee gate optional).
  secret_env = merge(
    {
      QUAICU_API_KEY_PEPPER = google_secret_manager_secret.pepper.secret_id
      KERNEL_JWT_SECRET     = google_secret_manager_secret.jwt.secret_id
      ENTITLEMENTS_DSN      = google_secret_manager_secret.entitlements_dsn.secret_id
      ACCOUNT_DSN           = google_secret_manager_secret.account_dsn.secret_id
      QUAICU_EDGE_SECRET    = google_secret_manager_secret.edge.secret_id
    },
    var.razorpay_key_id != "" ? {
      RAZORPAY_KEY_ID     = google_secret_manager_secret.razorpay_key_id[0].secret_id
      RAZORPAY_KEY_SECRET = google_secret_manager_secret.razorpay_key_secret[0].secret_id
    } : {}
  )
}

resource "google_project_service" "apis" {
  for_each           = toset(local.required_apis)
  service            = each.value
  disable_on_destroy = false
}

# ── Runtime service account (least-privilege; keyless / Workload Identity) ─────
resource "google_service_account" "kernel" {
  account_id   = "quaicu-saas-kernel"
  display_name = "QUAICU SaaS-plane kernel runtime"
}

resource "google_project_iam_member" "roles" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/secretmanager.secretAccessor",
    "roles/logging.logWriter",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.kernel.email}"
}

# ── Cloud SQL (Postgres) — durable BUSINESS-tier entitlements + accounts ─────
resource "google_sql_database_instance" "pg" {
  name             = "quaicu-saas-pg"
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
    # Private IP path is only wired when zero-egress is enabled (W5-3); public IP otherwise (the
    # Cloud SQL connector socket still encrypts in transit). Tighten with your platform team.
    dynamic "ip_configuration" {
      for_each = var.enable_private_egress ? [1] : []
      content {
        ipv4_enabled = false
        # private_network must be set to your VPC when enabling private IP — see ZERO_EGRESS_VALIDATION.md.
      }
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

# ── Secrets (env → Cloud Run). Values come from sensitive vars; never committed. ──
resource "google_secret_manager_secret" "pepper" {
  secret_id = "QUAICU_API_KEY_PEPPER"
  replication { auto {} }
}
resource "google_secret_manager_secret_version" "pepper" {
  secret      = google_secret_manager_secret.pepper.id
  secret_data = var.api_key_pepper
}

resource "google_secret_manager_secret" "jwt" {
  secret_id = "KERNEL_JWT_SECRET"
  replication { auto {} }
}
resource "google_secret_manager_secret_version" "jwt" {
  secret      = google_secret_manager_secret.jwt.id
  secret_data = var.jwt_secret
}

resource "google_secret_manager_secret" "entitlements_dsn" {
  secret_id = "ENTITLEMENTS_DSN"
  replication { auto {} }
}
resource "google_secret_manager_secret_version" "entitlements_dsn" {
  secret      = google_secret_manager_secret.entitlements_dsn.id
  secret_data = var.entitlements_dsn
}

resource "google_secret_manager_secret" "account_dsn" {
  secret_id = "ACCOUNT_DSN"
  replication { auto {} }
}
resource "google_secret_manager_secret_version" "account_dsn" {
  secret      = google_secret_manager_secret.account_dsn.id
  secret_data = var.account_dsn
}

resource "google_secret_manager_secret" "edge" {
  secret_id = "QUAICU_EDGE_SECRET"
  replication { auto {} }
}
resource "google_secret_manager_secret_version" "edge" {
  secret      = google_secret_manager_secret.edge.id
  secret_data = var.edge_secret
}

# Razorpay keys: created only when supplied (the signup-fee gate is optional).
resource "google_secret_manager_secret" "razorpay_key_id" {
  count     = var.razorpay_key_id != "" ? 1 : 0
  secret_id = "RAZORPAY_KEY_ID"
  replication { auto {} }
}
resource "google_secret_manager_secret_version" "razorpay_key_id" {
  count       = var.razorpay_key_id != "" ? 1 : 0
  secret      = google_secret_manager_secret.razorpay_key_id[0].id
  secret_data = var.razorpay_key_id
}
resource "google_secret_manager_secret" "razorpay_key_secret" {
  count     = var.razorpay_key_secret != "" ? 1 : 0
  secret_id = "RAZORPAY_KEY_SECRET"
  replication { auto {} }
}
resource "google_secret_manager_secret_version" "razorpay_key_secret" {
  count       = var.razorpay_key_secret != "" ? 1 : 0
  secret      = google_secret_manager_secret.razorpay_key_secret[0].id
  secret_data = var.razorpay_key_secret
}

# ── Optional Memorystore Redis: exact cross-worker usage metering (D4-1) ──
# Without it the usage meter is per-process (daily quotas approximate at workers/instances > 1).
# Memorystore is VPC-internal, so this requires the private-egress connector.
resource "google_redis_instance" "metering" {
  count          = var.enable_redis_metering ? 1 : 0
  name           = "${var.service_name}-metering"
  region         = var.region
  tier           = var.redis_tier
  memory_size_gb = var.redis_memory_gb

  lifecycle {
    precondition {
      condition     = var.enable_private_egress && var.vpc_connector != ""
      error_message = "enable_redis_metering requires enable_private_egress = true and a vpc_connector (Memorystore is only reachable inside the VPC)."
    }
  }
}

# ── Cloud Run service (shared SaaS plane: STARTER free + BUSINESS paid) ──
resource "google_cloud_run_v2_service" "kernel" {
  name     = var.service_name
  location = var.region
  template {
    service_account = google_service_account.kernel.email
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }
    # Per-instance request concurrency: pairs with KERNEL_WORKERS (uvicorn workers inside the
    # container). Autoscaling adds instances when concurrent requests exceed this per instance.
    max_instance_request_concurrency = var.concurrency
    timeout                          = "${var.request_timeout_seconds}s"

    # Opt-in private egress (W5-3): route all outbound traffic via the VPC connector. Default off.
    dynamic "vpc_access" {
      for_each = var.enable_private_egress ? [1] : []
      content {
        connector = var.vpc_connector
        egress    = "ALL_TRAFFIC"
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance { instances = [google_sql_database_instance.pg.connection_name] }
    }
    containers {
      image = var.image
      ports { container_port = 8080 }

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        # Full CPU during container start: hydration (policies + ledger trees + accounts) is
        # CPU-bound; without the boost a throttled cold start delays readiness.
        startup_cpu_boost = true
      }

      # Rolling deploys gate on readiness: a new revision receives traffic only after /readyz
      # returns 200 (lifespan hydration done), and a draining instance flips /readyz to 503
      # while /health (liveness) keeps passing — so rollouts and scale-in are zero-downtime.
      startup_probe {
        http_get { path = "/readyz" }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 24 # up to ~2min of hydration before the revision is marked failed
        timeout_seconds       = 3
      }
      liveness_probe {
        http_get { path = "/health" }
        period_seconds    = 30
        failure_threshold = 3
        timeout_seconds   = 3
      }

      env { name = "KERNEL_APP"          value = "delivery.entrypoint_saas:app" }
      env { name = "KERNEL_CONFIG_SAAS"  value = "/etc/quaicu/kernel.saas.toml" }
      env { name = "KERNEL_WORKERS"      value = tostring(var.kernel_workers) }
      env { name = "GCP_PROJECT"         value = var.project_id }
      env { name = "GCP_LOCATION"        value = var.region }

      # Exact cross-worker metering: build_usage_meter switches to RedisUsageMeter when set.
      dynamic "env" {
        for_each = var.enable_redis_metering ? [1] : []
        content {
          name  = "REDIS_URL"
          value = "redis://${google_redis_instance.metering[0].host}:${google_redis_instance.metering[0].port}"
        }
      }

      dynamic "env" {
        for_each = local.secret_env
        content {
          name = env.key
          value_source { secret_key_ref { secret = env.value  version = "latest" } }
        }
      }

      volume_mounts { name = "cloudsql" mount_path = "/cloudsql" }
    }
  }
  depends_on = [google_project_iam_member.roles]
}

# Public invoker — the plane is internet-facing behind the Cloudflare Worker. Set
# allow_unauthenticated = false for a private-ingress deployment.
resource "google_cloud_run_v2_service_iam_member" "public" {
  count    = var.allow_unauthenticated ? 1 : 0
  name     = google_cloud_run_v2_service.kernel.name
  location = google_cloud_run_v2_service.kernel.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
