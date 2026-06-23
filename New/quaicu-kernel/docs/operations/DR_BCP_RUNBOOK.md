# Disaster Recovery & Business Continuity runbook

> Operational runbook for restoring the QUAICU SaaS plane after data loss / region failure. RTO/RPO
> numbers are **bracketed `[N]` placeholders** until the restore test (§5) validates achievable times.

_Owner: [ops] · Tracks ACTION_TRACKER **W4-3** · Last updated: 2026-06-23_

## 1. Scope & current posture
- **Plane:** shared SaaS (Model A) — Cloud Run (us-central1) + Cloud SQL Postgres + Secret Manager,
  fronted by the Cloudflare Worker. **Single-region today** — multi-region failover is W5-2.
- **State that matters:** the Cloud SQL database (tenants, policies, entitlements, accounts, the K·02
  ledger). The Cloud Run service + Worker are stateless and redeployable from `cloudbuild.yaml` +
  `wrangler deploy`.
- **Backups:** Cloud SQL automated backups + **point-in-time recovery (PITR)** are enabled. ⚠ The
  restore has **never been tested** — see §5; an untested restore cannot back an RTO claim.

## 2. Targets (to be confirmed by the restore test)
| Metric | Target | Meaning |
|--------|--------|---------|
| **RPO** (max data loss) | `[N]` (e.g. ≤ 5 min, PITR granularity) | how far back a restore lands |
| **RTO** (max downtime) | `[N]` (e.g. ≤ 2 h) | time to restored service |

## 3. Scenarios → response
| Scenario | Response |
|----------|----------|
| **Accidental data mutation / deletion** | Cloud SQL **PITR** to a timestamp just before the event (§4). |
| **DB instance failure** | Restore latest automated backup to a new instance; repoint Cloud Run `DATABASE_URL`. |
| **Region outage (us-central1)** | Until W5-2: restore backup into another region, redeploy Cloud Run + repoint the Worker origin. Document expected extended RTO. |
| **Secret loss / compromise** | Recreate from Secret Manager versions; rotate (see `RETENTION_WORM_KEYROTATION.md`). ⚠ Never rotate `QUAICU_API_KEY_PEPPER` casually — it invalidates all issued API keys. |
| **Bad deploy** | Roll back Cloud Run to the prior revision; redeploy the Worker's prior version. |

## 4. Cloud SQL PITR — procedure (fill instance names)
```bash
# 1. Identify the target recovery timestamp (UTC), just before the incident.
# 2. Clone to a new instance at that point in time (does NOT overwrite the source):
gcloud sql instances clone [SOURCE_INSTANCE] [RECOVERED_INSTANCE] \
  --point-in-time '[YYYY-MM-DDTHH:MM:SSZ]'
# 3. Verify data on [RECOVERED_INSTANCE] (row counts, latest ledger entries, a tenant spot-check).
# 4. Repoint the service at the recovered instance (Secret Manager DSN + redeploy):
gcloud run services update quaicu-kernel --region us-central1 \
  --update-secrets DATABASE_URL=[DSN_SECRET]:latest
# 5. Smoke-test: /health, /readyz, a signed login, one governed action sealing to the ledger.
```

## 5. Restore test (REQUIRED — currently the gap) ⚠
Schedule and run a **DR drill** at least `[quarterly]`:
- [ ] Clone prod to a scratch instance via PITR (§4 steps 1–3).
- [ ] Bring up a kernel against it; verify `/readyz` and a governed action + ledger seal.
- [ ] Record the **actual** RPO (data-loss window) and RTO (wall-clock to service) → set §2 targets.
- [ ] Tear down the scratch instance. File results; update this runbook + the SLA (`SLA_STARTER.md`).
- [ ] Confirm backup retention matches `RETENTION_WORM_KEYROTATION.md`.

## 6. Roles & comms
- **Incident commander / ops on-call:** see `OBSERVABILITY_ONCALL_STATUS.md`.
- Customer comms via the status page; if personal data is affected, trigger the breach-notification
  playbook in `INCIDENT_RESPONSE.md` (GDPR 72h / DPDP).
