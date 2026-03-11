#!/usr/bin/env bash
# =============================================================================
# P0-S01 — Install Ollama + pull ALIS AI models (Ubuntu)
#
# Run on the Ubuntu production server (NOT in Docker — Ollama runs on the host
# and is accessed by the app container via host.docker.internal / bridge IP).
#
# Usage:
#   chmod +x scripts/install_ollama.sh
#   sudo bash scripts/install_ollama.sh
# =============================================================================

set -euo pipefail

OLLAMA_LLM_MODEL="qwen2.5:1.5b-instruct-q8_0"
OLLAMA_EMBED_MODEL="nomic-embed-text"

echo "==> Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

echo "==> Creating systemd service override (listen on all interfaces)..."
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf <<'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
# Limit to 2 GB RAM to leave headroom for the rest of the stack.
# Remove or raise this if you have more RAM to spare.
Environment="OLLAMA_MAX_LOADED_MODELS=1"
EOF

echo "==> Reloading systemd and starting Ollama service..."
systemctl daemon-reload
systemctl enable ollama
systemctl restart ollama

echo "==> Waiting for Ollama to be ready..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:11434/ > /dev/null 2>&1; then
        echo "    Ollama is up."
        break
    fi
    echo "    Attempt $i/30 — waiting 2s..."
    sleep 2
done

echo "==> Pulling LLM model: ${OLLAMA_LLM_MODEL}"
ollama pull "${OLLAMA_LLM_MODEL}"

echo "==> Pulling embedding model: ${OLLAMA_EMBED_MODEL}"
ollama pull "${OLLAMA_EMBED_MODEL}"

echo "==> Verifying models are loaded..."
ollama list

echo ""
echo "==> Done. Ollama is running at http://localhost:11434"
echo "    The ALIS Docker Compose stack accesses it via the host network."
echo "    Make sure OLLAMA_BASE_URL=http://<host-ip>:11434 is set in your .env"
