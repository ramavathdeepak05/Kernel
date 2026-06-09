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

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir \
        "fastapi>=0.111" \
        "uvicorn[standard]>=0.29" \
        "pydantic>=2.0" \
        "httpx>=0.27" \
        "PyJWT>=2.8" \
        "cel-python>=0.4.0" \
        "pyyaml>=6.0" \
        "cryptography>=42.0" \
        "asyncpg>=0.29" \
        "alembic>=1.13" \
        "sqlalchemy>=2.0" \
        "psycopg2-binary>=2.9"

# Copy source after installing deps (layer cache: dep install cached unless pip args change)
COPY . .

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

USER kernel

EXPOSE 7000

ENV KERNEL_CONFIG=/etc/quaicu/kernel.toml \
    KERNEL_HOST=0.0.0.0 \
    KERNEL_PORT=7000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:7000/health')"

# Single worker: _InMemoryActionRepository is in-process.
# For horizontal scale, replace with postgres_ledger + shared store and set --workers > 1.
CMD ["uvicorn", "delivery.entrypoint:app", \
     "--host", "0.0.0.0", "--port", "7000", "--workers", "1"]
