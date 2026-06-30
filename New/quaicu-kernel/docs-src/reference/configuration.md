# Configuration Reference (`kernel.toml`)

The kernel is configured via a TOML file. Set the path with the `KERNEL_CONFIG` environment variable (default: `/etc/quaicu/kernel.toml`).

!!! info "Coming soon"
    The full key-by-key reference is being written. See the example configs in `delivery/docker/` for working templates: `kernel.starter.toml`, `kernel.saas.toml`, `kernel.business.toml`.

## Minimal starter config

```toml
[kernel]
tier = "starter"
tenant = "my-org"

[storage]
adapter = "postgres"
dsn = "postgresql://kernel:password@localhost:5432/quaicu"

[policy]
default_decision = "deny"

[hitl]
adapter = "memory"       # dev only - use "email" or "slack" in production

[ledger]
signing_adapter = "openbao"
openbao_addr = "https://vault.internal:8200"
openbao_key_path = "transit/kernel/sign"
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `KERNEL_CONFIG` | Path to `kernel.toml` |
| `QUAICU_API_KEY_PEPPER` | HMAC pepper for API key hashing (required in production) |
| `EDGE_SECRET` | Secret for `X-Edge-Auth` trusted IP forwarding |
| `KERNEL_PORT` | Port to listen on (default: `7000`) |
