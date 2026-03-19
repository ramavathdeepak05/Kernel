---
name: alis-data-encryption
description: |
  ALIS data encryption and protection patterns. Use when implementing at-rest encryption, tenant key
  management, key rotation, field-level encryption, JWT security, password hashing, or reviewing
  cryptographic practices. Covers TenantKeyManager, Fernet/AES-GCM, ALIS_MASTER_KEY environment variable,
  tenant key generation and rotation, encrypt_data/decrypt_data, no-cloud constraint, encryption
  requirements for CONFIDENTIAL and REGULATED data. Trigger keywords: encryption, encrypt, decrypt,
  TenantKeyManager, key rotation, master key, ALIS_MASTER_KEY, Fernet, AES, cryptography, at-rest,
  at rest, password hash, bcrypt, JWT, token, secret, key management, data protection, TenantKeyEntry.
---

# ALIS Data Encryption & Protection

You are the ALIS Cryptography Expert. ALIS is an air-gapped, no-cloud system — all cryptographic
operations use local keys only. No AWS KMS, no Azure KeyVault, no external key services.

## What Requires Encryption

```python
from server.core.data_classification import encryption_required, SensitivityLevel

# CONFIDENTIAL and REGULATED fields MUST be encrypted at rest
encryption_required(SensitivityLevel.CONFIDENTIAL)  # True
encryption_required(SensitivityLevel.REGULATED)     # True
encryption_required(SensitivityLevel.INTERNAL)      # False
encryption_required(SensitivityLevel.PUBLIC)        # False
```

Encrypt: names, emails, financial amounts, biometric data, transcripts, documents.
Do not encrypt: UUIDs, status flags, timestamps, org_id references.

## Tenant Key Manager

Each tenant has its own 256-bit symmetric key. Keys are isolated — one tenant cannot decrypt another's data.

```python
from server.core.tenant_crypto import TenantKeyManager

# Generate key for a new tenant (called at tenant onboarding)
entry = TenantKeyManager.generate_tenant_key(
    tenant_id=org_id,
    actor_id=actor_id,  # Audit logged
)
# entry.key_hash — SHA-256 of key (for verification, not the key itself)
# entry.version  — starts at 1, increments on rotation

# Check if tenant has an active key
has_key = TenantKeyManager.has_key(tenant_id=org_id)

# Retrieve active key bytes (internal use only)
key_bytes = TenantKeyManager.get_tenant_key(tenant_id=org_id)
# Returns None if no key configured (encryption optional per E00-S03)
```

## Encrypting and Decrypting Data

```python
from server.core.tenant_crypto import TenantKeyManager

# Encrypt before storing in DB
plaintext = b"student@university.edu"
ciphertext = TenantKeyManager.encrypt_data(
    tenant_id=org_id,
    plaintext=plaintext,
)
# If no tenant key configured, returns plaintext unchanged (graceful)

# Decrypt when reading from DB
recovered = TenantKeyManager.decrypt_data(
    tenant_id=org_id,
    ciphertext=ciphertext,
)
```

The encryption algorithm is **Fernet (AES-128-CBC + HMAC-SHA256)**. If the `cryptography` library is
not installed, data is stored unencrypted with a warning (development only).

## Key Rotation

Key rotation generates a new key version. The old key is retained (marked inactive) so existing
encrypted records can still be decrypted during the re-encryption migration.

```python
new_entry = TenantKeyManager.rotate_key(
    tenant_id=org_id,
    actor_id=actor_id,  # Must be SUPER_ADMIN or SYSTEM
)
# new_entry.version — old version + 1
# new_entry.rotated_at — UTC timestamp
# Old key marked inactive but retained for decryption
# Audit logged automatically
```

Rotation schedule: at minimum annually, or immediately after a suspected key compromise.

## Master Key (Production Deployment)

The master key protects all tenant keys at rest. Set via environment variable:

```bash
# Generate a 256-bit master key
python -c "import secrets; print(secrets.token_hex(32))"

# Set in environment (never commit to git)
ALIS_MASTER_KEY=<64-hex-char-string>
```

If `ALIS_MASTER_KEY` is not set, an ephemeral in-memory key is used — **this is ONLY for development**.
Production deployments must always set `ALIS_MASTER_KEY`.

Production hardening options:
- Store master key in OS keyring (DPAPI on Windows, Keychain on macOS/Linux)
- Back with a local HSM if available
- Never store in `.env` files committed to version control

## JWT & Session Security

```python
from server.core.security import create_access_token, verify_token

# Default: HS256, signed with jwt_secret_key from settings
# RS256 migration path available — see below
# Expiry: 60 minutes (access), 7 days (refresh)
# Tenant context embedded in token payload: org_id, role, user_id
```

Token claims:
```json
{
  "sub": "<user_id>",
  "role": "<role>",
  "org_id": "<tenant_id>",
  "exp": <unix_timestamp>,
  "iat": <unix_timestamp>
}
```

Never store sensitive data in JWT payload — only IDs and roles.
Never return tokens in URL parameters — always in response body or `Authorization: Bearer` header.

### RS256 Migration Path (recommended for multi-tenant production)

HS256 uses a single symmetric key — if it leaks, all sessions across all tenants are compromised.
RS256 uses an asymmetric key pair: the private key signs tokens, the public key verifies.
This allows zero-downtime key rotation via JWKS.

```bash
# Generate RS256 key pair
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem
```

```bash
# Set in environment (never commit key files)
JWT_ALGORITHM=RS256
JWT_RSA_PRIVATE_KEY="$(cat private.pem)"
JWT_RSA_PUBLIC_KEY="$(cat public.pem)"
```

Settings validation blocks startup in production if `jwt_algorithm=RS256` without both keys set.
To migrate from HS256 → RS256: set the new env vars and restart — no DB migration needed.
Old tokens (HS256-signed) will be invalid after restart and users will need to re-login.

## Password Hashing

```python
# bcrypt with work factor 12 (minimum)
# Handled via passlib in server/core/security.py
from server.core.security import hash_password, verify_password

hashed = hash_password(plain_text_password)
is_valid = verify_password(plain_text_password, hashed)
```

Never store plain-text passwords. Never use MD5 or SHA-1 for passwords.

## TLS & Transport Security

- All external traffic through Nginx with TLS termination (`nginx/nginx.conf`)
- Internal service-to-service: within Docker network (trusted)
- API responses never include raw key material or master key references
- CORS: configured via `Settings.CORS_ORIGINS` — never `*` in production

## Data at Rest — Storage Rules

| Data Type | Storage | Encryption |
|---|---|---|
| PII fields (email, name, phone) | PostgreSQL CONFIDENTIAL column | Fernet via TenantKeyManager |
| Financial records | PostgreSQL REGULATED column | Fernet via TenantKeyManager |
| Biometric data | PostgreSQL REGULATED column | Fernet via TenantKeyManager |
| Documents / transcripts | MinIO (object storage) | MinIO server-side encryption |
| Embeddings | PostgreSQL pgvector | Not encrypted (non-PII vectors) |
| Audit ledger | PostgreSQL | Not encrypted (but append-only + hash-chained) |
| JWT secrets | Environment variable | OS-level protection |
| Tenant keys | In-memory (dev) / HSM (prod) | Master key encrypted |

## MinIO File Encryption

Documents uploaded via `fs_service.py` are stored in MinIO. Enable server-side encryption:

```python
# In fs_service.py upload calls, pass SSE headers
# MinIO SSE-S3 (server-managed) or SSE-C (client-provided key)
# Use SSE-S3 for simplicity, SSE-C for tenant-specific control
```

## Security Anti-Patterns — Never Do These

- Storing `ALIS_MASTER_KEY` in `.env` files checked into git
- Using `secrets.token_bytes` results as persistent keys without storage
- Logging raw key material — only log `key_hash`
- Using `hashlib.md5()` or `hashlib.sha1()` for security purposes
- Returning decrypted PII in API responses without field-level masking
- Skipping audit logs on key generation or rotation
- Using `os.urandom` directly instead of `secrets.token_bytes`

## Encryption Compliance Checklist

- [ ] Tenant key generated at org onboarding (`TenantKeyManager.generate_tenant_key`)
- [ ] `ALIS_MASTER_KEY` set in production environment (not `.env` file)
- [ ] All CONFIDENTIAL/REGULATED fields encrypted before `execute_transaction`
- [ ] Decrypted data masked before AI context injection (`DataMasker.mask_for_ai_context`)
- [ ] Key rotation logged to `AuditLedger` (automatic via `TenantKeyManager.rotate_key`)
- [ ] No plaintext PII in application logs (`DataMasker.mask_for_log`)
- [ ] MinIO SSE configured for document storage
- [ ] JWT `SECRET_KEY` is ≥ 256 bits, set via environment variable
- [ ] bcrypt work factor ≥ 12 for password hashing
