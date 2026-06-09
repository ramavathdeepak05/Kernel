---
name: quaicu-assurance
description: |
  QUAICU assurance layers K·09 Fairness · K·10 Drift · K·11 Explainability. Use when building
  core/fairness/, core/drift/, core/explain/, or any async assurance sweep. Enforces: all three run
  as lean async sweeps (ARQ/Dramatiq), NEVER in the hot path; computed over registered models (K·08)
  and recorded inputs/results (K·02) only — deterministic, no model re-calls; fairness delta feeds the
  K·01 impact report; drift breaches raise K·12 incidents; explanations are point-in-time derivable and
  attached to audit replay. Trigger keywords: fairness, drift, explainability, K·09, K·10, K·11,
  assurance, fairness_delta, baseline, drift_breach, explanation, async sweep, ARQ, Dramatiq,
  impact_report, point_in_time, recorded_inputs.
---

# QUAICU Assurance — K·09 Fairness · K·10 Drift · K·11 Explainability

You build the three **assurance** layers. They never sit in the governed-action hot path: they read
what the ledger already recorded and the models the registry already knows, then produce signals.
Because they only read recorded inputs/results, they are deterministic and replayable.

> Status: **scaffold.** One skill covers all three (they share substrate: K·08 registry + K·02 recorded
> inputs + async sweeps). The Decision Contract is authoritative; flesh out per-layer math against spec
> §6 (K·09/K·10/K·11 DoD), §3.3, §3.13 before shipping.

---

## ⚡ Deterministic Decision Contract — READ THIS FIRST

> **If this block conflicts with prose below, this block wins.** Missing rule → withhold the signal
> (never fabricate one) and stop.

### Invariants — never violated (all three layers)
- ALWAYS run as **async sweeps** (ARQ/Dramatiq), NEVER in the propose→seal hot path.
- ALWAYS compute from **recorded** inputs/results (K·02) + **registered** models (K·08). NEVER re-call a model — replay is side-effect-free (F-09).
- ALWAYS be deterministic: same recorded inputs → same assurance output.
- ALWAYS write outputs as new records/signals; NEVER mutate a sealed ledger entry.
- NEVER block or deny a live action from an assurance layer; they inform (impact reports, incidents), they don't gate.

### Per-layer contract
| Layer | Reads | Produces | Routes to |
|---|---|---|---|
| **K·09 Fairness** | recorded decisions/outcomes over a registered model | fairness metrics + **fairness delta** | the **K·01 impact report** (signed before activation, F-10) |
| **K·10 Drift** | recorded inputs vs a **recorded baseline** | drift measure; breach when over threshold | raises a **K·12 incident** on breach |
| **K·11 Explainability** | recorded inputs/results for one governed action | a point-in-time **explanation** (no model re-call) | attached to **audit replay** |

### Tie-break rules
- Missing recorded data to compute a signal? → withhold the signal + flag "insufficient data"; NEVER re-run the model to fill the gap.
- Drift near the threshold? → use the recorded baseline + fixed threshold deterministically; no wall-clock or live-data tie-break.
- Unsure if an explanation is point-in-time correct? → it must use only what the entry recorded; if it can't, it's not derivable — say so, don't approximate with a fresh call.

### Stop-and-apply triggers
- About to call `InferencePort.generate` inside fairness/drift/explain? → STOP, that breaks replay-safety; read the recorded output.
- About to run an assurance computation inline in the lifecycle? → STOP, move it to an async sweep.
- About to let a drift breach silently pass? → STOP, raise a K·12 incident.

### Self-check
- [ ] No model re-calls anywhere in K·09/K·10/K·11 (read recorded results only).
- [ ] All three run off the hot path as async sweeps.
- [ ] Fairness delta reaches the K·01 impact report; drift breach raises a K·12 incident; explanation attaches to replay.
- [ ] Deterministic given recorded inputs; outputs never mutate sealed entries.

---

## Definition of Done (spec §6 — K·09/K·10/K·11)
- [ ] **K·09:** fairness metrics over registered models; delta feeds the K·01 impact report; async, not hot path.
- [ ] **K·10:** drift measured vs a recorded baseline; breaches raise K·12 incidents; deterministic given recorded inputs.
- [ ] **K·11:** explanation derivable from recorded inputs/results for any governed action (point-in-time, no model re-call); attached to audit replay.
- [ ] per-tenant isolation; replay side-effect-free; coverage per the testing strategy.
