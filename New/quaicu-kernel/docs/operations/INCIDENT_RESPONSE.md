# Incident Response & Breach Notification runbook

> How QUAICU detects, triages, contains, and communicates a security/operational incident — including
> the regulator-facing **breach-notification** clocks (GDPR Art.33 72-hour, DPDP).

_Owner: [security + ops] · Tracks ACTION_TRACKER **W4-8** · Last updated: 2026-06-23_

> **Note:** This is the *operational* IR process. It is distinct from the kernel's K·12 **governance
> incident** (`core/incident/`), which is the in-product rollback of a governed action. This runbook
> borrows that module's severity vocabulary for consistency.

## 1. Severity (reuses `core/incident/model.py` `IncidentSeverity`)
| Severity | Example | First-response target |
|----------|---------|-----------------------|
| **CRITICAL** | Confirmed data breach; cross-tenant data exposure; full outage | immediate / `[15 min]` |
| **HIGH** | Suspected breach; auth bypass; partial outage; key compromise | `[1 h]` |
| **MEDIUM** | Single-tenant degradation; non-exploited high-sev vuln | `[1 business day]` |
| **LOW** | Cosmetic / no data or availability impact | best-effort |

## 2. Lifecycle
1. **Detect** — alert (see `OBSERVABILITY_ONCALL_STATUS.md`), customer report, or `security@quaicu.org`.
2. **Declare & assign** — on-call becomes **Incident Commander (IC)**; open an incident record; set
   severity; start a timeline (every action timestamped — this feeds the regulator notification).
3. **Contain** — stop the bleeding: revoke/rotate compromised credentials, block an abusive source at
   the edge, roll back a bad deploy, isolate an instance. Preserve evidence (logs, ledger entries).
4. **Eradicate & recover** — fix root cause; restore service (DR runbook if data is affected); verify
   via `/readyz` + a governed-action smoke test.
5. **Notify** — see §3 (this is time-critical and runs *in parallel* with containment).
6. **Post-incident review** — blameless post-mortem within `[5]` business days: timeline, root cause,
   corrective actions with owners. Feed fixes back into policy/code/runbooks.

## 3. Breach notification (personal-data incidents)
> Trigger the moment a personal-data breach is **reasonably suspected** — the clock does not wait for
> certainty. QUAICU is typically a **processor**; the controller (customer) owns the regulator/data-
> subject notification, and our job is to inform and assist them **without undue delay**.

| Regime | Who we notify | Clock |
|--------|---------------|-------|
| **GDPR (Art.33/34)** | the **controller** (customer) — they have **72 h** to notify their DPA | notify the controller **without undue delay** so their 72h is preserved |
| **India DPDP** | the customer + cooperate on Data Protection Board notification | per DPDP timelines |
| **Contractual** | per the DPA (`docs/legal/DPA_ART28_STARTER.md` clause (f)) + any SLA terms | as contracted |

**Notification content (prepare for the controller):** nature of the breach, categories/approx. number
of data subjects + records, likely consequences, measures taken/proposed, and our contact point.

## 4. Comms templates (fill + send)
- **Customer (processor→controller):** "We detected `[event]` at `[UTC time]` affecting `[scope]`.
  Containment: `[done]`. Personal data involved: `[yes/no — categories]`. We are assisting your Art.33
  assessment; next update by `[time]`."
- **Status page:** short, factual, no blame; update on a fixed cadence until resolved.

## 5. Roles & contacts
Incident Commander, Comms lead, Eng lead — staffed from the on-call rotation in
`OBSERVABILITY_ONCALL_STATUS.md`. External: legal/DPO `[contact]`, the affected customer's DPA contact.
