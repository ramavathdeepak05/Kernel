# Deploy Sovereign (On-Premise / Air-Gapped)

The Sovereign tier runs entirely on customer hardware with no egress. The kernel image is the same as every other tier — deployment mode is set by `kernel.toml`.

## Prerequisites

- Docker + Docker Compose v2, or Kubernetes with Helm
- PostgreSQL 16+ (managed or self-hosted)
- OpenBao instance for Ed25519 signing (or bring your own HSM)
- TLS at the load balancer

## Step 1 — Pull the image

```bash
docker pull ghcr.io/ramavathdeepak05/kernel:latest
```

Images are cosign-signed. Verify before deploying:

```bash
cosign verify ghcr.io/ramavathdeepak05/kernel:latest
```

## Step 2 — Configure `kernel.toml`

```toml
[kernel]
tier = "sovereign"
tenant = "your-org-id"

[storage]
adapter = "postgres"
dsn = "postgresql://kernel:password@db:5432/quaicu"

[ledger]
signing_adapter = "openbao"
openbao_addr = "https://vault.internal:8200"
openbao_key_path = "transit/kernel/sign"

[policy]
default_decision = "deny"

[hitl]
adapter = "email"
smtp_host = "smtp.internal"
smtp_from = "kernel@your-org.com"
```

## Step 3 — Run migrations

```bash
docker run --rm \
  -e KERNEL_CONFIG=/etc/quaicu/kernel.toml \
  -v ./kernel.toml:/etc/quaicu/kernel.toml \
  ghcr.io/ramavathdeepak05/kernel:latest \
  python -m alembic upgrade head
```

## Step 4 — Start the kernel

```bash
docker compose -f delivery/docker/docker-compose.prod.yml up -d
```

Verify:

```bash
curl https://kernel.your-org.com/health
```

## Production checklist

- [ ] `QUAICU_API_KEY_PEPPER` set (random 32-byte hex, not guessable)
- [ ] TLS at the load balancer — kernel never terminates TLS itself
- [ ] `X-Real-Client-IP` / `X-Edge-Auth` configured for the rate limiter (see CLAUDE.md open thread)
- [ ] PostgreSQL with connection pooling (PgBouncer recommended at scale)
- [ ] OpenBao unsealed and `transit/kernel/sign` key created
- [ ] Backup strategy for PostgreSQL (kernel data is append-only but must be durable)
- [ ] `alembic upgrade head` run after every kernel upgrade

!!! warning "Trusted forwarded-for"
    Behind a load balancer, the rate limiter's IP fallback collapses to the proxy IP. Configure `X-Real-Client-IP` with an HMAC-verified edge secret so the rate limiter sees real client IPs. See the open thread in `Kernel/CLAUDE.md`.
