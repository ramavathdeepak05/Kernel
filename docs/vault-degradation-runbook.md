# Vault Degradation Runbook

**Module**: Platform Core — Secrets Management  
**File**: `ALIS/server/core/vault_client.py`  
**Error class**: `VaultUnavailableError`

---

## Degradation Tiers

```
alis/exam/*        → CRITICAL  (exam paper Transit keys)
alis/mfa/*         → CRITICAL  (MFA TOTP secrets)
alis/tenant_key/*  → CRITICAL  (per-tenant data-at-rest keys)

alis/razorpay_webhook → NON-CRITICAL  (env var fallback: RAZORPAY_WEBHOOK_SECRET)
alis/msg91_key        → NON-CRITICAL  (env var fallback: MSG91_API_KEY)
alis/smtp_password    → NON-CRITICAL  (env var fallback: SMTP_PASSWORD)
```

---

## What Happens During Vault Downtime

| Scenario | System Behaviour |
|---|---|
| Vault down < 5 min | Non-critical secrets served from TTL cache. **No user impact.** |
| Vault down > 5 min (cache expired) | Non-critical: env var fallback if set. If not set → `VaultUnavailableError` → HTTP 503 for that feature only. |
| Vault down, any request for CRITICAL secret | `VaultUnavailableError` immediately → HTTP 503. **No cached fallback.** |
| Vault down in production | `/ready` probe returns `503` → load balancer stops routing traffic. |
| Vault down in non-production | `/ready` probe returns `warn` (not `error`) — system keeps running. |

---

## Most-Affected Features During Vault Outage

| Feature | Affected? | Reason |
|---|---|---|
| Exam paper upload / view | **Yes — hard stop** | Requires live Transit key |
| TOTP MFA login | **Yes — hard stop** | Requires live MFA secret |
| Student login (no MFA) | No | JWT-only, no Vault dependency |
| Payments (Razorpay) | Partial — env fallback | Webhook secret falls back to env |
| Email / SMS notifications | Partial — env fallback | SMTP / MSG91 key falls back to env |
| All OLTP reads/writes | No | Database not Vault-dependent |
| AI inference | No | Ollama is not Vault-dependent |

---

## Incident Response Steps

### 1. Confirm Vault is down
```bash
curl http://localhost:8200/v1/sys/health
# Expected when healthy: {"initialized":true,"sealed":false,...}
# Any error or timeout = Vault unreachable
```

### 2. Check `/ready` probe
```bash
curl http://localhost:8000/ready | jq .checks.vault
# "error: ..." = production Vault check failing and returning 503
```

### 3. What can continue running
- Student portal reads (login, grades, schedule) — **continue**
- Payment webhooks — **continue** (env fallback active)
- Email/SMS notifications — **continue** (env fallback active)

### 4. What must stop
- Exam paper creation / viewing — **halt until Vault restored**
- MFA login for admin roles — **halt until Vault restored**

### 5. Restore Vault
```bash
# Unseal Vault (requires 3/5 unseal keys per init)
vault operator unseal <unseal_key_1>
vault operator unseal <unseal_key_2>
vault operator unseal <unseal_key_3>

# Verify
vault status
```

### 6. After Vault restored
- `/ready` automatically returns 200 on next poll (within 30 s)
- Load balancer resumes routing traffic automatically
- Secret cache self-heals on next request — no app restart required

---

## Monitoring

| Alert | Condition | Severity |
|---|---|---|
| `alis_vault_down` | `/ready` → `checks.vault` contains `"error"` | CRITICAL |
| `alis_vault_cache_nearing_expiry` | Vault unavailable for > 4 min | WARNING |
| `VaultUnavailableError` in logs | Any critical secret miss | CRITICAL |

---

## Adding New Secrets

When adding a new Vault secret:

1. Classify it: **CRITICAL** or **NON-CRITICAL**?
2. If NON-CRITICAL: add an env var fallback to `_NON_CRITICAL_FALLBACK_ENV` in `vault_client.py`
3. If CRITICAL: add the path prefix to `_CRITICAL_SECRET_PREFIXES` in `vault_client.py`
4. Update this runbook table above with the new secret and its impact

---

*Last updated: April 2026 — Phase 2 Architectural Hardening*
