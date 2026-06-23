# Observability, On-call & Status Page runbook

> How the SaaS plane is monitored, who responds, and how customers see status. Covers W4-1
> (observability/alerting), W4-2 (status page), and W4-4 (on-call/support model). External SaaS
> account setup is an ops task; this is the wiring runbook.

_Owner: [ops] · Tracks ACTION_TRACKER **W4-1 / W4-2 / W4-4** · Last updated: 2026-06-23_

## 1. What exists today
- **Structured access logs + correlation IDs** — `delivery/api/observability.py` emits one structured
  record per request (method, path, status, duration, tenant, `X-Request-ID`) to Cloud Logging.
- **Health/readiness probes** — `GET /health` (liveness) and `GET /readyz` (readiness) on the kernel
  (W4-1); the Helm chart probes them. These are the uptime-monitor + load-balancer signals.
- **Gap:** no external metrics/alerting/uptime-monitor/status-page wired yet. This runbook is the plan.

## 2. Observability wiring (W4-1)
1. **Log-based metrics + alerts (GCP):** build log-based metrics on the access log (5xx rate, p95
   latency, request volume) and **Cloud Monitoring alert policies** that page on-call. No new
   dependency required — it reads the logs already emitted.
2. **Uptime checks:** Cloud Monitoring (or an external monitor — e.g. a third-party uptime service)
   polling `/readyz` from multiple regions; alert on failure.
3. **Error tracking (optional):** add a Sentry/error-tracker integration gated on a `SENTRY_DSN` env
   var (no-op when unset) — deferred; the structured logs cover the baseline.
4. **Routing:** alerts → on-call (§4) via `[PagerDuty/Opsgenie/email]`.

## 3. Status page (W4-2)
- Stand up a public status page (`[Statuspage/Instatus/self-hosted]`) at `status.quaicu.org`.
- Components: API, Console, Payments, Email. Drive incident posts from `INCIDENT_RESPONSE.md` §4.
- Wire the uptime check (§2.2) to auto-reflect API availability; publish maintenance windows here
  (so SLA "scheduled maintenance" exclusions are provable — see `docs/legal/SLA_STARTER.md`).

## 4. On-call & support model (W4-4)
- **Rotation:** `[N]`-person on-call, `[weekly]` rotation, primary + secondary; escalation to eng lead.
- **Coverage:** `[business-hours IST today → 24×7 when staffing allows]`. Enterprise 24×7 commitments
  in `docs/legal/ORDER_FORM_AND_PRICING.md` depend on this rotation existing — don't sell what isn't
  staffed.
- **Severity → response:** mirror `INCIDENT_RESPONSE.md` §1; support-tier response targets live in the
  order-form/support-tiers doc (single source of truth).
- **Escalation:** on-call → eng lead → incident commander; legal/DPO loop-in for any personal-data
  incident (breach clock — `INCIDENT_RESPONSE.md` §3).

## 5. Setup checklist
- [ ] Log-based metrics (5xx, latency, volume) + alert policies in Cloud Monitoring.
- [ ] Uptime check on `/readyz` (multi-region) → pager.
- [ ] Public status page live at `status.quaicu.org`; components + maintenance-window publishing.
- [ ] On-call rotation + escalation defined in the pager tool.
- [ ] Confirm SLA targets (`SLA_STARTER.md`) are measurable from the above before publishing numbers.
