# QUAICU Kernel — Hosting (SDK / FastAPI / Docker)

Three ways to consume the kernel. For the commercial delivery models see
[DEPLOYMENT_MODELS](DEPLOYMENT_MODELS.md); for the full SaaS launch checklist (payments, console,
DNS/TLS) see [GO_LIVE_SETUP](GO_LIVE_SETUP.md).

Key paths: SDK `delivery/sdk/`, FastAPI app `delivery/api/app.py`, runnable apps
`delivery/entrypoint.py` (`:app`) + `delivery/entrypoint_saas.py` (`:app`), Docker
`delivery/docker/`. Config profiles: `delivery/docker/kernel.{dev,prod,gcp,saas,starter,business}.toml`.

## 1. As an SDK (embed in a Python app — no server)
```python
from delivery.sdk import Kernel
kernel = Kernel.from_config("kernel.toml")

@kernel.governed(policy="ciro.ifrs9.stage_transition")
async def reclassify_loan(loan_id, from_stage, to_stage, *, actor): ...
```
Distribute the package (`quaicu-kernel`): `cd New/quaicu-kernel && python -m build` → publish the wheel
to PyPI / a private index, then consumers `pip install quaicu-kernel` (cloud extras: `[gcp]` / `[aws]`).
**Note:** no middleware in pure-SDK mode → metering/limits are not automatic; either front with the API
or self-enforce with `EntitlementEngine` + `UsageMeter` around your calls.

## 2. As a FastAPI service
```bash
pip install .
export KERNEL_CONFIG=delivery/docker/kernel.dev.toml
uvicorn delivery.entrypoint:app --host 0.0.0.0 --port 7000
```
Interactive docs at `/docs`, health at `/health`, governed routes under `/v1/...`. Console scripts:
`quaicu-kernel` (single-tenant) and `quaicu-kernel-saas` (multi-tenant plane). Use a durable profile
for `--workers >1`.

## 3. As Docker (recommended for hosting)
```bash
# local, with Postgres:
cd delivery/docker && docker-compose up --build      # http://localhost:7000

# build/run directly:
docker build -f delivery/docker/Dockerfile -t quaicu-kernel:dev .
docker run -p 7000:7000 \
  -v $(pwd)/delivery/docker/kernel.prod.toml:/etc/quaicu/kernel.toml:ro \
  -e KERNEL_CONFIG=/etc/quaicu/kernel.toml -e KERNEL_WORKERS=4 \
  -e QUAICU_API_KEY_PEPPER=<secret> quaicu-kernel:dev
```
Image: port **7000**, non-root, `/health` healthcheck, config via `KERNEL_CONFIG`. CI publishes a
cosign-signed `ghcr.io/<owner>/kernel:<tag>` on git tag. Production: Helm chart at
`delivery/docker/helm/` + managed Postgres + a durable profile.

## Which to offer
| Goal | Use |
|---|---|
| Embed governance in a Python app | SDK (publish the wheel) |
| Callable governance API, fast | FastAPI (`quaicu-kernel` + `kernel.dev.toml`) |
| Host reliably / sell it | Docker (compose for dev; Helm + GHCR image for prod) |
| Multi-tenant SaaS | `quaicu-kernel-saas` + `kernel.saas.toml` |

## Production must-dos
Durable profile · `alembic upgrade head` · set `QUAICU_API_KEY_PEPPER` + enable auth · TLS at the LB
with a trusted forwarded-for handler · managed Postgres + Cloud KMS signing.
