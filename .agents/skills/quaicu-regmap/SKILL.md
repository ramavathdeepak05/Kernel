---
name: quaicu-regmap
description: |
  QUAICU K·14 Regulatory Mapping — regulation catalog + point-in-time signed evidence packs. Use when
  building core/regmap/, the regulation catalog, evidence-pack generation, or policy↔regulation linkage.
  Enforces: evidence is point-in-time correct (policies/regulations as they were in the queried window,
  via replay); the signed evidence pack (human-readable doc + machine-readable manifest + K·02 proof
  refs) verifies via K·02 verify; a regulation change flags affected mappings review_required and NEVER
  auto-mutates a policy. Trigger keywords: regmap, K·14, regulatory mapping, regulation catalog,
  evidence pack, regulatory_refs, point_in_time, review_required, RBI, EU AI Act, DPDP, NAAC, signed
  evidence, manifest, inclusion proof, verify.
---

# QUAICU K·14 Regulatory Mapping

You turn the ledger into **evidence a regulator can verify**. A regulation maps to the policies that
implement it; an evidence pack proves, for a point in time, what was enforced — and verifies against
the K·02 ledger. This is engineering, not narrative (spec §3.11).

> Status: **scaffold.** The Decision Contract is authoritative; flesh out the catalog schema and the
> pack format against spec §6 (K·14 DoD), §3.11, and the policy envelope's `regulatory_refs` field
> before shipping.

---

## ⚡ Deterministic Decision Contract — READ THIS FIRST

> **If this block conflicts with prose below, this block wins.** Missing rule → mark `review_required`
> and stop (never auto-mutate policy, never emit unverifiable evidence).

### Invariants — never violated
- ALWAYS build evidence **point-in-time**: use the policy versions and regulation text in effect **in the queried window**, reconstructed via replay (§3.13) — never "now".
- ALWAYS make the signed evidence pack **verifiable via K·02 `verify`**: it references inclusion proofs + STH, so a third party can re-check it without trusting us.
- ALWAYS, on a regulation change, flag affected mappings **`review_required`**. NEVER auto-mutate, auto-activate, or auto-deprecate a policy from a regulation change — a human reviews and re-activates through K·01.
- ALWAYS link policy→regulation via the policy envelope's `regulatory_refs` (e.g. `rbi.ifrs9.staging`); the mapping is data, not code.
- NEVER let an evidence pack claim something the ledger proofs don't support.

### Evidence pack = three parts (all required)
| Part | Content |
|---|---|
| human-readable document | the narrative a regulator reads |
| machine-readable manifest | structured claims: regulation refs, policy versions, time window, action set |
| ledger proof references | K·02 inclusion proofs + signed tree head, so the pack **verifies** |

### Decision table
| Situation | Do exactly this |
|---|---|
| build evidence for window [t0,t1] | replay policies/regulations as of that window; assemble the 3-part pack; sign it |
| regulation text changes | flag mapped policies `review_required`; notify; do NOT change policy automatically |
| a claim has no ledger proof | omit it and flag the gap; never assert unverifiable evidence |
| pack requested for a tenant | scope strictly to that tenant's ledger; never cross tenants |

### Tie-break rules
- Unsure which policy version applied at time t? → resolve it by replay, not by current state.
- Unsure whether to update a policy after a reg change? → don't; flag `review_required` and route to a human via K·01.

### Stop-and-apply triggers
- About to read the *current* policy to describe a *past* window? → STOP, replay the point-in-time version.
- About to ship an evidence pack without K·02 proof references? → STOP, it isn't verifiable.
- About to auto-edit a policy because a regulation changed? → STOP, flag `review_required`.

### Self-check
- [ ] Evidence uses point-in-time policy/regulation versions (via replay), not current state.
- [ ] Pack has all three parts and verifies through K·02 `verify`.
- [ ] Regulation change → `review_required`, never an automatic policy mutation.
- [ ] Mappings use `regulatory_refs`; per-tenant scoping enforced.

---

## Relationships
- **K·01 Policy** envelopes carry `regulatory_refs`; a reg change flags those policies for human review.
- **K·02 Ledger** supplies the inclusion proofs + STH the pack references and verifies against.
- **Replay (§3.13)** supplies point-in-time correctness.

## Definition of Done (spec §6 — K·14)
- [ ] evidence is point-in-time correct (policies/regulations as they were then).
- [ ] the signed evidence pack verifies via K·02 `verify`.
- [ ] a regulation change flags mappings `review_required` and never auto-mutates policy.
- [ ] per-tenant isolation; catalog covers the target regimes (RBI FREE-AI, EU AI Act, DPDP, NAAC).
