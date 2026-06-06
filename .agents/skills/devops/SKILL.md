---
name: devops
description: Deploy to Cloudflare (Workers, R2, D1), Docker, GCP (Cloud Run, GKE), Kubernetes (kubectl, Helm). Use for serverless, containers, CI/CD, GitOps, security audit. QUAICU kernel — CI runs the architecture gates first (domain/import/eval bans) then the full test matrix, mypy --strict, cosign-signed releases with SBOM, OpenTofu + OpenBao, Helm on k3s, migrations gate deploy. Triggers — QUAICU, CI gates, cosign, SBOM, OpenTofu, Helm, coverage floor, release pipeline.
license: MIT
version: 2.0.0
---

# DevOps Skill

## ⚡ QUAICU Decision Contract — READ THIS FIRST (when used for the QUAICU kernel)

> Makes the QUAICU-specific delivery choices mechanical so a small/low-token model matches a top model at max effort.
> **For QUAICU work, this block overrides the general guidance below.**

### Invariants — never violated
- IaC is OpenTofu; secrets are OpenBao. NEVER Terraform or HashiCorp Vault (BSL).
- CI MUST run and BLOCK on the architecture gates before tests: domain-term grep in core/, import-boundary check (no adapters/SDK imports in core/), eval/exec/Rego ban. A gate failure is a build failure, not a warning.
- CI order is fixed: arch gates → lint → typecheck (mypy --strict) → unit → conformance → property → integration → contract → chaos → performance. Coverage floors enforced (ledger 95%, others 90%).
- Releases are signed (cosign) with an SBOM (syft). No unsigned release is promoted.
- Migrations gate deploy: a new image is not "ready" until every tenant schema is migrated.

### Decision table
| Stage | Tool / gate |
|---|---|
| Architecture enforcement | grep gates (domain / import / eval) — fail-closed |
| Type safety | mypy --strict |
| Supply chain | cosign sign + syft SBOM |
| Sovereign deploy | Helm chart on k3s; OpenTofu for cloud infra |
| Secrets | OpenBao injection in pipeline + runtime |

### Tie-break rules
- Skip a flaky arch gate to unblock a merge? → never; the gate is the product's guarantee.
- Terraform/Vault available and easier? → use OpenTofu/OpenBao anyway (licensing).

### Self-check
- [ ] Arch gates run first and block merge.
- [ ] Full test matrix wired in order; coverage floors enforced.
- [ ] Releases signed + SBOM.
- [ ] OpenTofu/OpenBao only.

---

Deploy and manage cloud infrastructure across Cloudflare, Docker, Google Cloud, and Kubernetes.

## When to Use

- Deploy serverless apps to Cloudflare Workers/Pages
- Containerize apps with Docker, Docker Compose
- Manage GCP with gcloud CLI (Cloud Run, GKE, Cloud SQL)
- Kubernetes cluster management (kubectl, Helm)
- GitOps workflows (Argo CD, Flux)
- CI/CD pipelines, multi-region deployments
- Security audits, RBAC, network policies

## Platform Selection

| Need | Choose |
|------|--------|
| Sub-50ms latency globally | Cloudflare Workers |
| Large file storage (zero egress) | Cloudflare R2 |
| SQL database (global reads) | Cloudflare D1 |
| Containerized workloads | Docker + Cloud Run/GKE |
| Enterprise Kubernetes | GKE |
| Managed relational DB | Cloud SQL |
| Static site + API | Cloudflare Pages |
| Container orchestration | Kubernetes |
| Package management for K8s | Helm |

## Quick Start

```bash
# Cloudflare Worker
wrangler init my-worker && cd my-worker && wrangler deploy

# Docker
docker build -t myapp . && docker run -p 3000:3000 myapp

# GCP Cloud Run
gcloud run deploy my-service --image gcr.io/project/image --region us-central1

# Kubernetes
kubectl apply -f manifests/ && kubectl get pods
```

## Reference Navigation

### Cloudflare Platform
- `cloudflare-platform.md` - Edge computing overview
- `cloudflare-workers-basics.md` - Handler types, patterns
- `cloudflare-workers-advanced.md` - Performance, optimization
- `cloudflare-workers-apis.md` - Runtime APIs, bindings
- `cloudflare-r2-storage.md` - Object storage, S3 compatibility
- `cloudflare-d1-kv.md` - D1 SQLite, KV store
- `browser-rendering.md` - Puppeteer automation

### Docker
- `docker-basics.md` - Dockerfile, images, containers
- `docker-compose.md` - Multi-container apps

### Google Cloud
- `gcloud-platform.md` - gcloud CLI, authentication
- `gcloud-services.md` - Compute Engine, GKE, Cloud Run

### Kubernetes
- `kubernetes-basics.md` - Core concepts, architecture, workloads
- `kubernetes-kubectl.md` - Essential commands, debugging workflow
- `kubernetes-helm.md` / `kubernetes-helm-advanced.md` - Helm charts, templates
- `kubernetes-security.md` / `kubernetes-security-advanced.md` - RBAC, secrets
- `kubernetes-workflows.md` / `kubernetes-workflows-advanced.md` - GitOps, CI/CD
- `kubernetes-troubleshooting.md` / `kubernetes-troubleshooting-advanced.md` - Debug

### Scripts
- `scripts/cloudflare-deploy.py` - Automate Worker deployments
- `scripts/docker-optimize.py` - Analyze Dockerfiles

## Best Practices

**Security:** Non-root containers, RBAC, secrets in env vars, image scanning
**Performance:** Multi-stage builds, edge caching, resource limits
**Cost:** R2 for large egress, caching, right-size resources
**Development:** Docker Compose local dev, wrangler dev, version control IaC

## Resources

- Cloudflare: https://developers.cloudflare.com
- Docker: https://docs.docker.com
- GCP: https://cloud.google.com/docs
- Kubernetes: https://kubernetes.io/docs
- Helm: https://helm.sh/docs

---

## QUAICU-Specific Application

### CI/CD Pipeline — GitHub Actions

The QUAICU pipeline enforces the spec's Definition of Done at the CI level. Every PR must pass the full sequence before merge. No stage is skippable — fail-closed applies to the pipeline too (a flaky conformance test is not a merge blocker exemption; fix the test or fix the code).

Stage order: `lint` → `type-check` → `unit` → `conformance` → `property` → `integration` → `chaos` → `build` → `push`

```yaml
# .github/workflows/quaicu-ci.yml
name: QUAICU Kernel CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}/quaicu-kernel

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with: { version: "0.5" }
      - run: uv run ruff check .
      - run: uv run ruff format --check .

  type-check:
    name: Type Check
    runs-on: ubuntu-24.04
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv run mypy core/ adapters/ delivery/ --strict

  unit:
    name: Unit Tests
    runs-on: ubuntu-24.04
    needs: type-check
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv run pytest tests/unit/ -m "not conformance and not property and not integration and not chaos" --tb=short -q

  conformance:
    name: Conformance Suite
    runs-on: ubuntu-24.04
    needs: unit
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: quaicu_test
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
    env:
      DATABASE_URL: postgresql://postgres:test@localhost:5432/quaicu_test
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv run alembic upgrade head
      - run: uv run pytest tests/conformance/ -m conformance --tb=short -v

  property:
    name: Property-Based Tests
    runs-on: ubuntu-24.04
    needs: unit
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: quaicu_test
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-retries 10
    env:
      DATABASE_URL: postgresql://postgres:test@localhost:5432/quaicu_test
      HYPOTHESIS_MAX_EXAMPLES: 200
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv run alembic upgrade head
      - run: uv run pytest tests/property/ -m property --tb=short -v

  integration:
    name: Integration Tests
    runs-on: ubuntu-24.04
    needs: [conformance, property]
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: quaicu_test
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-retries 10
    env:
      DATABASE_URL: postgresql://postgres:test@localhost:5432/quaicu_test
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv run alembic upgrade head
      - run: uv run pytest tests/integration/ -m integration --tb=short -v

  chaos:
    name: Chaos / Fault-Injection Tests
    runs-on: ubuntu-24.04
    needs: integration
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: quaicu_test
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-retries 10
    env:
      DATABASE_URL: postgresql://postgres:test@localhost:5432/quaicu_test
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv run alembic upgrade head
      - name: Fault-injection — verify fail-closed
        # Each test injects a specific fault (policy service down, ledger timeout, etc.)
        # and asserts the action was DENIED or HALTED, never allowed through.
        run: uv run pytest tests/chaos/ -m chaos --tb=short -v

  build:
    name: Build Container Image
    runs-on: ubuntu-24.04
    needs: chaos
    outputs:
      digest: ${{ steps.build.outputs.digest }}
      image-ref: ${{ steps.build.outputs.image-ref }}
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Docker meta
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=sha-
            type=ref,event=branch
            type=semver,pattern={{version}}
      - name: Build and push
        id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          file: delivery/docker/Dockerfile
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          sbom: true    # generate SBOM via buildkit
          provenance: mode=max

  push:
    name: Sign Image + Attach SBOM
    runs-on: ubuntu-24.04
    needs: build
    permissions:
      id-token: write   # required for cosign keyless signing
      packages: write
    steps:
      - uses: sigstore/cosign-installer@v3
      - uses: anchore/syft-action@v1
        with:
          image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build.outputs.digest }}
          output-file: sbom.spdx.json
          format: spdx-json
      - name: Sign image with cosign (keyless / OIDC)
        run: |
          cosign sign --yes \
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build.outputs.digest }}
      - name: Attach SBOM to image
        run: |
          cosign attest --yes \
            --predicate sbom.spdx.json \
            --type spdxjson \
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build.outputs.digest }}
```

### Helm Chart Structure — `quaicu-kernel`

The kernel ships as a single Helm chart that works for both k3s (sovereign/small) and full K8s (dedicated/cloud). The chart image is identical across tiers — only orchestration resources differ.

```
charts/quaicu-kernel/
├── Chart.yaml
├── values.yaml                  # defaults — adapter selection, resource limits
├── values-sovereign.yaml        # k3s overrides: single replica, local storage
├── values-cloud.yaml            # K8s overrides: HPA, external DB, Temporal
├── templates/
│   ├── _helpers.tpl
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── configmap.yaml           # kernel.toml rendered from values
│   ├── secret-store.yaml        # OpenBao CSI SecretProviderClass
│   ├── hpa.yaml                 # only rendered when autoscaling.enabled=true
│   ├── pdb.yaml                 # PodDisruptionBudget for zero-downtime migrations
│   ├── migration-job.yaml       # pre-upgrade hook: alembic upgrade head
│   └── NOTES.txt
```

#### `values.yaml` (key sections)

```yaml
# charts/quaicu-kernel/values.yaml

image:
  repository: ghcr.io/your-org/quaicu-kernel
  pullPolicy: IfNotPresent
  # Tag is overridden by --set image.tag=sha-abc123 in CI
  tag: ""

# ── Adapter selection (mirrors kernel.toml) ──────────────────────────────────
adapters:
  inference: "ollama"             # ollama | vllm | openai | anthropic | bedrock
  hitl: "webhook"                 # webhook | email | slack | inapp
  identity: "oidc"                # oidc | jwt | host_provided
  storage: "postgres"
  workflow: "postgres_statemachine"  # postgres_statemachine | temporal

# ── Deployment tier ──────────────────────────────────────────────────────────
deployment:
  tier: "sovereign"               # sovereign | private_cloud | cloud

# ── Secrets via OpenBao CSI driver ───────────────────────────────────────────
# Never put secrets in values.yaml. All sensitive values are injected from OpenBao.
secrets:
  provider: openbao               # only supported provider; Vault is excluded (BSL)
  vaultAddress: "http://openbao.openbao.svc.cluster.local:8200"
  # SecretProviderClass will mount these paths as files or env vars
  paths:
    dbCredentials: "secret/data/quaicu/db"
    inferenceApiKey: "secret/data/quaicu/inference"
    ledgerSigningKey: "secret/data/quaicu/ledger-signing"

# ── PostgreSQL (external, managed by customer) ───────────────────────────────
postgresql:
  host: "postgres.default.svc.cluster.local"
  port: 5432
  database: "quaicu"
  # Credentials injected from OpenBao; not here.

# ── Resources ────────────────────────────────────────────────────────────────
resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "1Gi"
    cpu: "1000m"

# ── Autoscaling (cloud tier only; disabled for sovereign) ────────────────────
autoscaling:
  enabled: false
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70

# ── Rolling update strategy ──────────────────────────────────────────────────
updateStrategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0    # zero-downtime: never take a pod down before a new one is ready

# ── Schema migration hook ─────────────────────────────────────────────────────
migration:
  enabled: true
  # Runs as a pre-upgrade Helm hook: alembic upgrade head
  # The migration job must complete successfully before the new Deployment rolls out.
  hookWeight: "-5"
```

#### OpenBao CSI SecretProviderClass template

```yaml
# templates/secret-store.yaml
{{- if eq .Values.secrets.provider "openbao" }}
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: {{ include "quaicu-kernel.fullname" . }}-secrets
  namespace: {{ .Release.Namespace }}
spec:
  provider: vault    # OpenBao uses the same CSI provider binary as Vault (API-compatible)
  parameters:
    vaultAddress: {{ .Values.secrets.vaultAddress | quote }}
    roleName: "quaicu-kernel"
    objects: |
      - objectName: "db-password"
        secretPath: {{ .Values.secrets.paths.dbCredentials | quote }}
        secretKey: "password"
      - objectName: "inference-api-key"
        secretPath: {{ .Values.secrets.paths.inferenceApiKey | quote }}
        secretKey: "api_key"
      - objectName: "ledger-signing-key"
        secretPath: {{ .Values.secrets.paths.ledgerSigningKey | quote }}
        secretKey: "private_key"
  secretObjects:
    - data:
        - key: db-password
          objectName: db-password
        - key: inference-api-key
          objectName: inference-api-key
        - key: ledger-signing-key
          objectName: ledger-signing-key
      secretName: {{ include "quaicu-kernel.fullname" . }}-secrets
      type: Opaque
{{- end }}
```

### k3s Deployment for Sovereign Tier

The sovereign tier is a single-node k3s install, air-gapped, with no external image pulls. All images must be pre-loaded via `k3s ctr images import` or bundled into the node image. The Helm chart's `values-sovereign.yaml` enforces this.

```yaml
# values-sovereign.yaml — overrides for sovereign / air-gapped / single-node k3s

image:
  pullPolicy: Never   # NEVER pull from external registry; image must be pre-loaded

deployment:
  tier: "sovereign"

adapters:
  inference: "ollama"                  # local inference only; no cloud API
  workflow: "postgres_statemachine"    # no Temporal server needed

autoscaling:
  enabled: false    # single-node; no autoscaling

replicaCount: 1

# Disable PodDisruptionBudget on single-node — would block node maintenance
pdb:
  enabled: false

resources:
  requests:
    memory: "128Mi"
    cpu: "50m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

#### Air-gapped image loading script

```bash
#!/usr/bin/env bash
# scripts/load-sovereign-images.sh
# Run on the sovereign node before helm install.
# All images are provided as tar archives in the release bundle.
set -euo pipefail

BUNDLE_DIR="${1:?Usage: $0 <bundle-dir>}"

for tar_file in "$BUNDLE_DIR"/*.tar; do
  echo "Loading $tar_file ..."
  k3s ctr images import "$tar_file"
done

echo "Loaded images:"
k3s ctr images list | grep quaicu
```

### Zero-Downtime Schema Migrations

Schema migrations (Alembic) run as a Helm pre-upgrade hook. The `maxUnavailable: 0` rolling update strategy ensures new pods are Ready before old pods are terminated. Each migration must be backward-compatible with the previous application version (additive changes only; destructive changes in a follow-up version after all pods have updated).

```yaml
# templates/migration-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ include "quaicu-kernel.fullname" . }}-migration-{{ .Release.Revision }}
  annotations:
    "helm.sh/hook": pre-upgrade,pre-install
    "helm.sh/hook-weight": {{ .Values.migration.hookWeight | quote }}
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
spec:
  backoffLimit: 3
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: migration
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          command: ["alembic", "upgrade", "head"]
          envFrom:
            - secretRef:
                name: {{ include "quaicu-kernel.fullname" . }}-secrets
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: {{ include "quaicu-kernel.fullname" . }}-secrets
                  key: db-url
```

### Signed Release Pipeline

Every production image is signed with cosign (keyless, OIDC-based) and has an SBOM generated by syft and attached as a cosign attestation. This satisfies the spec's §8 supply-chain requirement and is a prerequisite for bank deployments.

```bash
# Verify a release image before deploying to sovereign node
cosign verify \
  --certificate-identity-regexp "https://github.com/your-org/quaicu-kernel" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  ghcr.io/your-org/quaicu-kernel/quaicu-kernel:sha-abc123

# Download and inspect the SBOM attestation
cosign download attestation \
  ghcr.io/your-org/quaicu-kernel/quaicu-kernel:sha-abc123 \
  | jq -r '.payload' | base64 -d | jq '.predicate'
```

### IaC with OpenTofu

Use OpenTofu (not Terraform — BSL exclusion per spec §3.7). OpenTofu is HCL-compatible; existing Terraform modules are usable. Provision the k3s sovereign node and the K8s cloud infrastructure from the same module set.

```hcl
# tofu/modules/quaicu-node/main.tf
terraform {
  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.13"
    }
  }
}

resource "helm_release" "quaicu_kernel" {
  name       = "quaicu-kernel"
  chart      = "${path.module}/../../../charts/quaicu-kernel"
  namespace  = var.namespace
  values     = [
    file("${path.module}/values-${var.tier}.yaml"),
    yamlencode({ image = { tag = var.image_tag } }),
  ]
  atomic          = true   # roll back on failure
  cleanup_on_fail = true
  wait            = true
  timeout         = 300
}
```

### Non-negotiables for QUAICU pipelines

- **No Vault dependency anywhere in CI, Helm, or IaC.** OpenBao only (§3.1 / BSL).
- **CI must pass the full stage sequence.** No merging with skipped chaos or conformance stages.
- **Sovereign images must be pre-loaded; `imagePullPolicy: Never` in sovereign values.** A pull failure on an air-gapped node must not fall through to an external registry.
- **Migration jobs must complete before the new Deployment rolls out.** The pre-upgrade hook weight and `atomic: true` enforce this.
- **Every release image must be cosign-signed before sovereign deployment.** Bank environments will verify the signature as part of their intake process.
- **OpenTofu, not Terraform.** BSL applies to embedded/shipped IaC the same way it applies to the kernel.
