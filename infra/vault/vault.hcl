# HashiCorp Vault — Production Configuration
# Uses Raft integrated storage (durable, survives restarts).
# Do NOT use this in dev mode (no -dev flag).
#
# First-time setup:
#   docker exec alis_vault vault operator init -key-shares=5 -key-threshold=3
#   → save the 5 unseal keys + initial root token to a secure location (KMS / password manager)
#   → set VAULT_TOKEN=<root_token> in .env
#   docker exec alis_vault vault operator unseal <key1>
#   docker exec alis_vault vault operator unseal <key2>
#   docker exec alis_vault vault operator unseal <key3>
#
# After any restart, Vault is sealed and must be unsealed with 3 of 5 keys.
# For automated unsealing in on-prem deploy, use vault-autostart.sh.

storage "raft" {
  path    = "/vault/data"
  node_id = "alis-vault-01"
}

listener "tcp" {
  address       = "0.0.0.0:8200"
  tls_disable   = true   # TLS terminated at Nginx; set tls_cert_file/tls_key_file for direct TLS
}

api_addr     = "http://127.0.0.1:8200"
cluster_addr = "https://127.0.0.1:8201"

ui = true

# Audit log — every Vault operation is recorded (required for DPDP/ISO 27001)
# Enabled via: vault audit enable file file_path=/vault/logs/audit.log
