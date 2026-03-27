#!/bin/sh
# vault-autostart.sh — Start Vault (Raft mode) and auto-unseal on boot.
#
# vault status exit codes: 0=unsealed, 1=error/unreachable, 2=sealed
# This script waits until vault responds (exit 0 or 2), then unseals.
#
# On first boot (Initialized=false), operator must run:
#   docker exec alis_vault vault operator init -key-shares=5 -key-threshold=3
#   → set VAULT_TOKEN and VAULT_UNSEAL_KEY_1..3 in .env

VAULT_ADDR_LOCAL="http://127.0.0.1:8200"

# Start Vault server
vault server -config=/vault/config/vault.hcl &
VAULT_PID=$!

# Wait until vault responds (exit 0 = unsealed, 2 = sealed — both mean running)
echo "vault-autostart: waiting for Vault..."
i=0
while [ $i -lt 60 ]; do
  vault status -address="$VAULT_ADDR_LOCAL" > /dev/null 2>&1
  code=$?
  if [ "$code" -eq 0 ] || [ "$code" -eq 2 ]; then
    echo "vault-autostart: Vault is up (status=$code)"
    break
  fi
  sleep 1
  i=$((i + 1))
done

# Auto-unseal using keys from environment
for key_var in VAULT_UNSEAL_KEY_1 VAULT_UNSEAL_KEY_2 VAULT_UNSEAL_KEY_3; do
  eval key="\$$key_var"
  if [ -n "$key" ]; then
    vault operator unseal -address="$VAULT_ADDR_LOCAL" "$key" > /dev/null 2>&1 || true
    echo "vault-autostart: applied unseal key $key_var"
  fi
done

# Log final seal status
vault status -address="$VAULT_ADDR_LOCAL" 2>/dev/null | grep "^Sealed" | while read line; do
  echo "vault-autostart: $line"
done

# Wait for vault to exit
wait $VAULT_PID
