# Wave 4 — Operational readiness tracker

> The "ready to run a regulated SaaS" items from `ACTION_TRACKER.md`. Unlike Waves 2–3, several have a
> code/CI half (landed this pass) plus an ops/human half (runbook written, external setup pending).

_Last updated: 2026-06-23 · Source of truth for status: update here as items move._

## Status
| Item | ID | Type | Status | Next concrete action | Artifact |
|------|----|------|--------|----------------------|----------|
| **Observability / alerting / uptime** | W4-1 | code+ops | **Code done** (`/health` + `/readyz`); ops pending | Wire log-based metrics + alerts + uptime check (Cloud Monitoring) | `OBSERVABILITY_ONCALL_STATUS.md` |
| **Status page** | W4-2 | ops | Runbook done; page not stood up | Stand up `status.quaicu.org`; wire uptime check | `OBSERVABILITY_ONCALL_STATUS.md` §3 |
| **DR/BCP + tested restore** | W4-3 | ops | Runbook done; **restore untested** | Run the DR drill (§5); record real RTO/RPO | `DR_BCP_RUNBOOK.md` |
| **24×7 on-call + support tiers** | W4-4 | human | Model documented | Staff the rotation; wire the pager | `OBSERVABILITY_ONCALL_STATUS.md` §4 |
| **Retention + WORM + key rotation** | W4-5 | code+ops | Policy done; WORM storage pending | Stand up a retention-locked GCS bucket for ledger/log archive | `RETENTION_WORM_KEYROTATION.md` |
| **Trust center / SECURITY.md** | W4-6 | human+code | **`SECURITY.md` done** (resolves prior dangling refs) | Publish a trust-center page; link certs as they land | `../../SECURITY.md` |
| **CAIQ / SIG pre-answers** | W4-7 | human | **Drafted** | Keep current as controls/certs change; reuse per RFP | `../compliance/CAIQ_SIG_ANSWERS.md` |
| **Incident response + breach notice** | W4-8 | human | **Runbook done** | Tabletop exercise; fill `[contacts]` | `INCIDENT_RESPONSE.md` |
| **Vuln management + CI scanning** | W4-9 | code+ops | **CI scanning + policy done (report mode)** | Clear backlog → graduate Trivy/pip-audit to blocking | `VULN_MANAGEMENT.md`, `../../cloudbuild.yaml` |

## What landed in code this pass
- `/health` (liveness) + `/readyz` (readiness, gated on startup hydration) — `delivery/api/app.py`;
  Helm readiness probe repointed to `/readyz`; `/readyz` added to the rate-limit exempt set.
- `cloudbuild.yaml`: blocking **lint + unit-test gate** before build; **pip-audit** + **Trivy** scans +
  **CycloneDX SBOM** artifact in **report mode**.

## What stays human/ops
- External SaaS setup (Cloud Monitoring alerts, uptime checks, status page, pager rotation).
- The **DR restore test** (the one true gap behind any RTO/RPO claim).
- Graduating CI scans report→blocking once the backlog is within SLA.
