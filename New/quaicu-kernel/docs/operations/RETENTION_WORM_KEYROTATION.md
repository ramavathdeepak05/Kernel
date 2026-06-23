# Data retention, WORM & key-rotation policy

> Audit-log/ledger retention schedule, write-once-read-many (WORM) enforcement, and the cryptographic
> key-rotation/custody schedule. Bracketed `[N]` values are for the business/ops to set per regime.

_Owner: [ops + security] · Tracks ACTION_TRACKER **W4-5** · Last updated: 2026-06-23_

## 1. Retention schedule
| Data class | Retention | Notes |
|------------|-----------|-------|
| **K·02 transparency ledger** (governance audit trail) | `[7 years]` (regulated-default) | The compliance record of who-did-what; align to the strictest regime served (RBI/SEBI, SOX-like). |
| **Access logs** (structured request logs) | `[1 year]` hot, `[+N]` cold | Correlation-id access records from `observability.py`. |
| **Customer personal data** | per the DPA — delete/return at end of provision | Crypto-shred erasure path (`core/erasure/`); see DPA clause (g). |
| **Backups** (Cloud SQL automated + PITR) | `[35 days]` PITR window + `[N]` retained backups | Must cover the DR scenarios in `DR_BCP_RUNBOOK.md`. |

## 2. WORM (write-once-read-many) / immutability
The audit trail must be tamper-evident **and** tamper-resistant:
- **Application layer:** the K·02 ledger is an **append-only RFC-6962 Merkle log** — entries are
  immutable and any modification is cryptographically detectable. Policy versions are immutable
  evidence artifacts (`core/policy/store.py` rejects re-registering a deprecated version).
- **Storage layer (to enforce — currently a gap):** back the durable ledger/exports with WORM storage:
  - **GCS bucket retention-lock** (locked retention policy) for ledger exports / log archives — once
    locked, objects cannot be deleted or overwritten until the retention period elapses.
  - **Cloud SQL:** automated backups + PITR; restrict delete IAM; consider exporting sealed ledger
    snapshots to a retention-locked bucket on a schedule.
- **Action:** [ ] stand up a retention-locked GCS bucket for ledger/audit-log archive; [ ] document the
  export cadence; [ ] restrict who can alter retention (separation of duties).

## 3. Key custody & rotation
| Key / secret | Custody | Rotation | ⚠ Notes |
|--------------|---------|----------|---------|
| `QUAICU_API_KEY_PEPPER` | Secret Manager | `[only with re-issue]` | Rotating **invalidates every issued API key** — maintenance-window only, re-issue keys. Do **not** strip its stored trailing newline. |
| `QUAICU_EDGE_SECRET` / Worker `EDGE_SECRET` | Secret Manager + Wrangler | `[90 days]` | Rotate both sides together (shared secret) to avoid a window where real-IP forwarding breaks. |
| Razorpay / Resend keys | Secret Manager | `[on staff change / suspected leak]` | Rotate at the provider, add a new SM version, redeploy, **destroy** the old version. |
| `RAZORPAY_WEBHOOK_SECRET` | Secret Manager | provision **before** enabling `[billing.razorpay]` (W6-8) | Absent today (the webhook engine is disabled). |
| **K·02 ledger signing key** (OpenBao / KMS where wired) | OpenBao / Cloud KMS / HSM | `[per HSM policy]` | HSM-backed custody for dedicated tiers; ties to the W6-4 `GcpKmsShredKeyring`. |
| Cloud SQL / DSN | Secret Manager | `[180 days]` | Rotate with a brief dual-credential window. |

## 4. Process
- All secrets live in **Secret Manager** referenced by `:latest`; never in committed config (the
  `[billing]`/`[signup_fee]` TOML uses `${ENV}` references, now fail-loud on an unset var).
- Rotation: add new version → redeploy/restart → verify → **destroy** the superseded version.
- Record each rotation (date, who, key) for the audit trail; surface the schedule in the trust center.
