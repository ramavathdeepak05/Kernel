# =============================================================================
# ALIS SaaS — Shared Module: HashiCorp Vault
#
# Configures Vault for multi-tenant secret management:
#   - KV v2 mount at "secret"
#   - AppRole auth for data plane and control plane
#   - Per-tenant ACL policy template
# =============================================================================

terraform {
  required_version = ">= 1.5"
  required_providers {
    vault = {
      source  = "hashicorp/vault"
      version = "~> 3.0"
    }
  }
}

# ---------------------------------------------------------------------------
# KV v2 Secret Engine
# ---------------------------------------------------------------------------

resource "vault_mount" "secret" {
  path        = "secret"
  type        = "kv"
  description = "ALIS KV v2 secrets"
  options = {
    version = "2"
  }
}

# ---------------------------------------------------------------------------
# AppRole Auth
# ---------------------------------------------------------------------------

resource "vault_auth_backend" "approle" {
  type = "approle"
}

# Data plane role — can read tenant secrets, write usage events
resource "vault_approle_auth_backend_role" "data_plane" {
  backend   = vault_auth_backend.approle.path
  role_name = "alis-data-plane"

  token_policies = ["alis-data-plane"]
  token_ttl      = 3600    # 1 hour
  token_max_ttl  = 28800   # 8 hours
}

# Control plane role — can read/write all tenant secrets
resource "vault_approle_auth_backend_role" "control_plane" {
  backend   = vault_auth_backend.approle.path
  role_name = "alis-control-plane"

  token_policies = ["alis-control-plane"]
  token_ttl      = 3600
  token_max_ttl  = 28800
}

# ---------------------------------------------------------------------------
# ACL Policies
# ---------------------------------------------------------------------------

resource "vault_policy" "data_plane" {
  name = "alis-data-plane"

  policy = <<-EOT
    # Read tenant secrets for any tenant in any region
    path "secret/data/alis/*/tenant/*/db" {
      capabilities = ["read"]
    }
    path "secret/data/alis/*/tenant/*/s3" {
      capabilities = ["read"]
    }
    path "secret/data/alis/*/tenant/*/custom/*" {
      capabilities = ["read"]
    }

    # System-level secrets (read only)
    path "secret/data/alis/system/*" {
      capabilities = ["read"]
    }
  EOT
}

resource "vault_policy" "control_plane" {
  name = "alis-control-plane"

  policy = <<-EOT
    # Full CRUD on all tenant secrets
    path "secret/data/alis/*/tenant/*" {
      capabilities = ["create", "read", "update", "delete", "list"]
    }
    path "secret/metadata/alis/*/tenant/*" {
      capabilities = ["list", "read", "delete"]
    }

    # System-level secrets
    path "secret/data/alis/system/*" {
      capabilities = ["create", "read", "update"]
    }
  EOT
}

# ---------------------------------------------------------------------------
# System-level seed secrets
# ---------------------------------------------------------------------------

resource "vault_kv_secret_v2" "master_key" {
  mount = vault_mount.secret.path
  name  = "alis/system/master_key"
  data_json = jsonencode({
    key = var.alis_master_key
  })
}
