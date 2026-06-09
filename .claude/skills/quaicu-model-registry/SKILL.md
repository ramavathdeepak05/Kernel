---
name: quaicu-model-registry
description: |
  QUAICU K·08 Model Registry — the per-tenant model allowlist the AI Gateway (K·05) enforces and the
  assurance layers (K·09–K·11) read. Use when building core/registry/, the model registry store, or
  model-approval flows. Enforces: per-tenant allowlist (a model absent from a tenant's allowlist →
  Gateway DENY, no fallback); model id + version recorded on every governed action's ledger entry;
  registry consulted before K·09–K·11; registering/activating a model is itself a governed action.
  Trigger keywords: model registry, K·08, ModelRef, allowlist, model_version, approved model, registry,
  register_model, per_tenant, model_card, deprecate, assurance, gateway enforcement, K·05.
---

# QUAICU K·08 Model Registry

You hold the source of truth for **which models a tenant may use**. The Gateway (K·05) enforces your
allowlist on every inference call, and the assurance layers (K·09–K·11) key their metrics off the
registered model + version. Nothing about a model is implicit.

> Status: **scaffold.** The Deterministic Decision Contract is authoritative; flesh out the store and
> the governed registration flow against spec §6 (K·08 DoD), §3.5, §3.12 before shipping.

---

## ⚡ Deterministic Decision Contract — READ THIS FIRST

> **If this block conflicts with prose below, this block wins.** Missing rule → DENY/withhold and stop.

### Invariants — never violated
- ALWAYS scope the allowlist **per tenant**. A model approved for tenant A is not approved for tenant B.
- ALWAYS resolve `(tenant, model_ref)` to an explicit registry entry before any inference. Not on the allowlist → **DENY** (the Gateway enforces this; no fallback to an unapproved model — F-03/K·05).
- ALWAYS record the exact **model id + version** used on the governed action's ledger entry (needed for replay and K·09–K·11).
- ALWAYS treat registering, activating, deprecating, or changing a model's status as a **governed action** through the full lifecycle (no out-of-band edits — F-04).
- NEVER let K·09/K·10/K·11 run against a model the registry doesn't know; the registry is consulted first.

### Decision table
| Situation | Do exactly this |
|---|---|
| Gateway asks: may tenant T use model M? | M on T's allowlist + status ACTIVE → **yes**; else **DENY** |
| model not registered for the tenant | **DENY**, no fallback, no implicit default |
| model deprecated/retired | **DENY** for new actions; existing ledger entries keep their recorded version |
| sealing a governed action that called a model | record `model_id` + `version` in the entry |
| assurance layer needs the model | read it from the registry (which must already exist) |

### Tie-break rules
- Two versions both "active"? → the allowlist entry names the exact version; ambiguity → DENY, escalate.
- Unsure whether an admin edit needs the lifecycle? → it does; route it as a governed action.

### Stop-and-apply triggers
- About to let the Gateway fall back to a different model when the requested one isn't approved? → STOP, DENY.
- About to seal an action without the model version? → STOP, the entry is not replayable.
- About to mutate registry state directly in the DB? → STOP, register it as a governed action.

### Self-check
- [ ] Allowlist is per-tenant; cross-tenant approval is impossible.
- [ ] Unapproved model → DENY at the Gateway, no fallback.
- [ ] model id + version recorded on every model-using action's entry.
- [ ] Registry mutations go through the lifecycle and are sealed.

---

## Relationships
- **K·05 Gateway** enforces the allowlist on every `InferencePort.generate`.
- **K·02 Ledger** records the model + version per action (replay needs it).
- **K·09–K·11** read registered models to compute assurance signals.

## Definition of Done (spec §6 — K·08)
- [ ] per-tenant model allowlist enforced by the Gateway.
- [ ] model + version recorded with each governed action.
- [ ] consulted before K·09–K·11.
- [ ] registration/activation is a governed, sealed action; per-tenant isolation tested.
