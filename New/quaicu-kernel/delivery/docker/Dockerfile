# QUAICU Governance Kernel — multi-stage Docker image
#
# Build context: quaicu-kernel/ (the git repo root)
#
# From the quaicu-kernel/ directory:
#   docker build -f delivery/docker/Dockerfile -t quaicu-kernel:dev .
#
# Or via docker-compose (from delivery/docker/):
#   docker-compose up --build
#
# The image exposes port 7000 and reads its adapter config from the file
# pointed to by KERNEL_CONFIG (default: /etc/quaicu/kernel.toml).
# Mount a ConfigMap or volume at that path in Kubernetes / docker-compose.

# ── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Reproducible install: the pinned + hashed lockfile (generated from pyproject.toml via
# `uv pip compile --generate-hashes`) is the single source of truth for runtime deps. Copy only the
# manifest first so the dependency layer caches unless the lock changes.
COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --require-hashes -r requirements.lock

# Copy source and install the package itself (console scripts quaicu-kernel / quaicu-kernel-saas +
# importable core/adapters/delivery). --no-deps: deps are already pinned from the lock above.
COPY . .
RUN pip install --no-cache-dir --no-deps .

# The shared SaaS plane's BUSINESS tier signs its K·02 ledger with Cloud KMS
# (adapters/ledger/gcp_kms → GcpKmsTreeSigner). google-cloud-kms is an optional [gcp] extra not in the
# hash-locked base, so install it explicitly. It layers on top of the reproducible locked base; pin it
# into requirements.lock for a fully hash-reproducible production build.
RUN pip install --no-cache-dir google-cloud-kms

# ── Stage 2: runtime (non-root, minimal) ─────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN groupadd -r kernel && useradd -r -g kernel kernel

WORKDIR /app

# Copy installed packages and uvicorn binary from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages \
                    /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Copy kernel source
COPY --from=builder /build .

# Bake the shared SaaS-plane configs to the path the plane descriptor references. The SaaS entrypoint
# reads KERNEL_CONFIG_SAAS=/etc/quaicu/kernel.saas.toml, whose [plane] points at the per-tier configs
# below. These files carry NO secrets — DSNs/keys are ${ENV} placeholders injected at runtime — so
# baking them is safe. (The single-kernel default path, KERNEL_CONFIG=/etc/quaicu/kernel.toml, is
# unaffected; mount that one when running delivery.entrypoint:app.)
RUN mkdir -p /etc/quaicu \
 && cp delivery/docker/kernel.saas.toml \
       delivery/docker/kernel.starter.toml \
       delivery/docker/kernel.business.toml /etc/quaicu/

USER kernel

EXPOSE 7000

ENV KERNEL_CONFIG=/etc/quaicu/kernel.toml \
    KERNEL_HOST=0.0.0.0 \
    KERNEL_PORT=7000 \
    KERNEL_WORKERS=1 \
    KERNEL_APP=delivery.entrypoint:app

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c \
    "import os,urllib.request; urllib.request.urlopen('http://localhost:'+os.environ.get('PORT',os.environ.get('KERNEL_PORT','7000'))+'/health')"

# Worker count is configurable via KERNEL_WORKERS (default 1). The default in-memory config keeps in-
# process state (action repo / ledger), so leave it at 1. With an all-durable profile
# (kernel.prod.toml / kernel.gcp.toml) there is no correctness-critical in-process state, so
# KERNEL_WORKERS > 1 (and multiple replicas) is safe.
#
# KERNEL_APP selects the ASGI app: `delivery.entrypoint:app` (single-kernel, default) or
# `delivery.entrypoint_saas:app` (shared SaaS plane). The port honors Cloud Run's injected $PORT,
# falling back to $KERNEL_PORT for local/compose/k8s. Shell form so the vars expand at runtime.
CMD uvicorn "$KERNEL_APP" --host 0.0.0.0 --port "${PORT:-$KERNEL_PORT}" --workers "$KERNEL_WORKERS"
