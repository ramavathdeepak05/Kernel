# Control Plane — Production Dockerfile
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Runtime stage ---
FROM python:3.11-slim

RUN groupadd -r alis && useradd -r -g alis -d /app -s /sbin/nologin alis

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

WORKDIR /app
COPY . .

RUN chown -R alis:alis /app

USER alis

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8001/health || exit 1

CMD ["uvicorn", "control_plane.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
