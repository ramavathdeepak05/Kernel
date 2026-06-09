---
name: quaicu-consent
description: |
  QUAICU K·04 DPDP Consent — consent as a second evaluate-time governance signal. Use when building
  core/consent/, the consent store/adapter, or any code that evaluates an action touching personal
  data. Enforces: missing / expired / withdrawn consent → DENY (fail-closed); consent state recorded
  in the ledger entry at evaluate time; point-in-time resolvable for replay; purpose-bound, never
  inferred. Trigger keywords: consent, DPDP, K·04, personal data, purpose, withdraw, withdrawn,
  expired, data principal, consent_artifact, lawful basis, purpose_limitation, evaluate, consent_state,
  point_in_time, ConsentPort, deny.
---

# QUAICU K·04 DPDP Consent

You enforce consent as a **second evaluate-time signal** in the lifecycle, alongside the Policy
Engine (K·01). Consent is checked at `evaluate`, its resolved state is sealed into the K·02 ledger
entry, and — like every signal — it fails closed. This is DPDP-shaped (India's Digital Personal Data
Protection Act): consent is purpose-bound, time-bound, and withdrawable.

> Status: **scaffold.** The Deterministic Decision Contract below is authoritative and complete for
> the layer's invariants; flesh out the implementation sections against spec §6 (K·04 DoD), §3.13
> (point-in-time replay), and the lifecycle skill before shipping. Escalate gaps to the orchestrator.

---

## ⚡ Deterministic Decision Contract — READ THIS FIRST

> Makes every consent decision mechanical. **If this block conflicts with prose below, this block wins.**
> Missing rule → DENY and stop.

### Invariants — never violated
- ALWAYS check consent at `evaluate`, before `gate`/`execute`, for any action whose payload touches personal data.
- ALWAYS fail closed: missing, expired, withdrawn, or unresolvable consent → **DENY**. Never infer or assume consent.
- ALWAYS record the resolved consent state (status, purpose, artifact id, resolved-at, version) **in the ledger entry** so replay sees what was true then.
- ALWAYS purpose-bind: consent for purpose A does not authorize purpose B. Scope mismatch → DENY.
- NEVER let a consent-service error/timeout pass the action through (F-03). Error → DENY.
- NEVER mutate or "refresh" consent as a side effect of evaluation; resolution is read-only.

### Decision table (resolve consent → do exactly this)
| Consent state for (data principal, purpose) | Decision |
|---|---|
| valid + not expired + purpose matches | **allow** (consent signal passes; K·01 still decides the rest) |
| missing / none on file | **deny** |
| expired | **deny** |
| withdrawn | **deny** |
| purpose mismatch / broader than granted | **deny** |
| consent store errors / times out / ambiguous | **deny** (fail-closed) |

### Tie-break rules
- Unsure if a record covers this purpose? → treat as not covered → DENY.
- Unsure if expired (clock skew)? → treat as expired → DENY. (Borrow the ledger's clock discipline; never trust wall-clock alone for air-gapped.)
- Consent passes but a policy (K·01) denies → action is DENIED. Consent is necessary, never sufficient.

### Stop-and-apply triggers
- About to default a missing consent lookup to "allowed"? → STOP, return DENY.
- About to evaluate a personal-data action without recording consent_state in the entry? → STOP, record it.
- About to call a model/Gateway with personal data before consent resolves? → STOP, consent gates that path too.

### Self-check
- [ ] Every personal-data action resolves consent at evaluate; result recorded in the ledger entry.
- [ ] missing/expired/withdrawn/mismatch/error all map to DENY.
- [ ] Consent state is point-in-time resolvable on replay (no live re-fetch).
- [ ] Purpose limitation enforced (no purpose creep).

---

## Where it sits in the lifecycle
`propose → evaluate(K·01 policy + **K·04 consent** + K·08–K·11 signals) → gate(K·03) → execute → seal(K·02) → emit(K·07)`

Consent is one of the evaluate-time inputs. Its state becomes part of the canonical sealed entry
(see §10 worked example: `consent_state` is a recorded field) so a point-in-time replay (§3.13)
reconstructs the exact consent posture without calling the consent service again.

## ConsentPort (illustrative — define the real Protocol in core/ports/)
- `resolve(*, principal, purpose, tenant, at) -> ConsentState` — pure read; raises on error (never returns a permissive default).
- `ConsentState` carries: `status` (VALID/EXPIRED/WITHDRAWN/MISSING), `purpose`, `artifact_id`, `granted_at`, `expires_at`, `version`.

## Definition of Done (spec §6 — K·04)
- [ ] missing / expired / withdrawn consent → **DENY**.
- [ ] consent state recorded in the ledger entry; resolvable point-in-time for replay.
- [ ] purpose limitation enforced; per-tenant isolation (consent never crosses a tenant boundary).
- [ ] fault injection proves fail-closed; coverage floor 90%.
- [ ] security review (K·04 is security-critical) before any client touches personal data.
