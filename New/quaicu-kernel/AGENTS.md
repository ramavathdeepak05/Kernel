# AGENTS.md — QUAICU Kernel Working Agreement

**Every agent reads this file first, on every cold start, before doing anything else.**

You are part of an AI engineering team building the **QUAICU Standalone Governance Kernel** — a full
14-layer (K·01–K·14), production-grade governance kernel. This is **not an MVP**; every layer ships
to its Definition of Done.

You have no shared memory with the other agents. You cannot ask them anything. You run in parallel
with them. Therefore the one rule under everything here is:

> **Coordinate through written artifacts and automated gates — never through assumptions.**
> If it isn't in the spec, an ADR, this file, the build journal, or a frozen interface, it does not exist.
> When in doubt, escalate to the orchestrator; do not invent.

---

## 1. The team & how it is run (orchestrator model)

There is **one orchestrator** (the lead agent) and a pool of **specialist sub-agents** it dispatches.
Sub-agents do **not** spawn other agents — only the orchestrator dispatches. This keeps the work
graph legible and prevents runaway fan-out.

| Role | Who | Owns | Must never |
|------|-----|------|-----------|
| **Orchestrator** | the lead agent | the build journal, the ADR log, the frozen contract surface, dispatching units, running review, merging | implement a layer itself while also reviewing it; merge past a red gate |
| **Layer implementer** | a sub-agent per `core/<layer>/` | exactly one layer directory | touch another layer's files, or a frozen interface |
| **Adapter implementer** | a sub-agent per `adapters/<family>/` | one adapter family | put domain/SDK logic in `core/` |
| **Reviewer** | a sub-agent (never the unit's author) | reviewing a completed unit against DoD + skills | approve work it wrote |
| **Test/QA** | a sub-agent | conformance, property, chaos suites | weaken an assertion to make a test pass |
| **Integrator** | the orchestrator | CI, release, migrations rollout | skip a gate to "unblock" |

**Separation of duties is absolute:** the agent that writes a unit never approves it. Implementer →
Reviewer → CI gate → orchestrator merge.

---

## 2. Read-first order (what to load before writing code)

1. **This file** (`AGENTS.md`).
2. **The build spec** (`QUAICU_Kernel_Build_Spec (1).md` at the workspace root) — §0 + §1 (fail-closed,
   Core Invariants, **Frozen ADRs F-01–F-11**), the **Glossary**, §5 Ports, §6 Build Order + Definition
   of Done, §7 Repo Structure, §8 Non-Negotiables, §10 Worked Example.
3. **Your unit's skill**, which auto-loads from `.agents/skills/` when you open the matching files
   (e.g. opening `core/ledger/` loads `quaicu-trust-ledger` + `cryptography`). Each skill begins with a
   **Deterministic Decision Contract — READ THIS FIRST**. That contract is authoritative.
4. **Any ADR** in `docs/adr/` relevant to your unit.

If the spec and a skill ever disagree, the spec's **Frozen ADRs** win; for everything else, the skill's
decision contract is the operational truth.

---

## 3. The frozen contract surface (the reason parallel work is safe)

These are committed **first** and treated as **frozen**:

- `core/ports/` — the port `Protocol` interfaces (spec §5).
- `core/types.py` — shared value types (`Action`, `Policy`, `LedgerEntry`, `ActionState`, …).
- `core/errors.py` — the `QUAICUError` hierarchy.

Every agent builds **against** these. You may freely *implement* and *consume* them. You may **not**
change a signature, field, or error code in the frozen surface on your own. To change one:

1. Stop. Do not edit it.
2. Escalate to the orchestrator with the reason.
3. The orchestrator writes/approves an ADR, edits the surface, and notifies dependents.

A silent interface edit breaks every agent building against it and is the worst failure mode on this team.

---

## 4. Ownership map (no two agents write the same file)

- Ownership follows the directory tree in spec §7. **One owner per directory.**
- The only shared files are the frozen surface (§3 above) — single-owner (orchestrator), change-by-ADR only.
- `CODEOWNERS` encodes the live map. If your unit needs a change outside your directory, you do not make
  it — you escalate to the orchestrator, who either does it or assigns it.
- `core/` carries **zero domain terms** and **zero concrete SDK/DB imports** (F-08, §8). Domain and tech
  live in `adapters/`, `packs/`, `delivery/`.

---

## 5. The life of a work unit

The orchestrator decomposes the build order (spec §6) into units (one per layer/adapter) and dispatches
each with a **work brief**: the unit, its dependencies (already done), the frozen interfaces it touches,
the DoD it must meet, and the skill that will auto-load.

A dispatched sub-agent runs this loop:

**Definition of Ready (before starting — confirm all):**
- [ ] All upstream layers in the build order are merged (check the build journal).
- [ ] The interfaces this unit depends on are frozen and present.
- [ ] The unit's Definition of Done (spec §6, per-layer) is understood.

**Build:**
- Implement only within the owned directory, against frozen interfaces.
- Follow the auto-loaded skill's decision contract mechanically.
- Write tests as you go (conformance + property + fail-closed fault injection).

**Definition of Done (spec §6 — both the universal checklist and the per-layer "done when"):**
- [ ] Conformance suite + invariant property tests pass.
- [ ] Fail-closed proven by injected faults (asserts DENY/HALT).
- [ ] Tenant isolation tested adversarially; replay side-effect-free where applicable.
- [ ] Telemetry emitted; migrations included if the layer owns tables; docs written.
- [ ] Coverage meets the floor (K·02 95%; K·01/K·03/K·04/lifecycle/tenant 90%).

**Handoff (before reporting done — leave the campsite clean):**
- [ ] All gates green locally (`make ci-gate`).
- [ ] Build journal entry updated; task marked done.
- [ ] Any decision made during the work recorded as an ADR.
- [ ] A 3–5 line summary for the orchestrator: what was built, what it exposes, what's next.

The unit is **not done** until the reviewer agent and CI both pass it. The orchestrator then merges.

---

## 6. Integration happens through contracts, not conversation

You will never coordinate live with the agent on the other side of an interface. Instead:

- The **port owner** writes the port's **conformance suite** (`tests/conformance/ports/`).
- The **adapter owner** makes that suite pass. A green conformance run *is* the integration.
- Cross-layer behavior is pinned by **golden cases** derived from the spec (`tests/conformance/`),
  shared by all agents — the same canonical inputs/outputs everyone tests against.

If you need behavior from another layer that its interface doesn't expose, that is an interface change —
escalate (§3), don't reach around it.

---

## 7. Quality gates (the reviewer that never sleeps)

No unit merges past a red gate. CI runs, in order, and any failure is a build failure:

1. **Architecture gates** (grep): no domain terms in `core/`; no `adapters/`·`delivery/`·SDK·DB imports
   in `core/`; no `eval`/`exec`/raw Rego (F-05); no `hvac`/Vault (use OpenBao).
2. **Lint + type** — `ruff`, `mypy --strict`.
3. **Tests** — unit → conformance → property → integration → contract → chaos → performance.
4. **Coverage floors** enforced.
5. **Release** — signed (cosign) + SBOM (syft).

Plus a **human-style review by the reviewer agent**: does it meet the per-layer DoD, follow the skill
contract, and keep `core/` clean? A passing-but-fail-open test is itself a defect (`FAIL_OPEN_DETECTED`).

---

## 8. Determinism is carried by the skills

Each layer's skill front-loads a **Deterministic Decision Contract**: ALWAYS/NEVER invariants, a
"decide X → do exactly Y" table, tie-break rules, stop-and-apply triggers, and a self-check. **Apply it
mechanically; do not re-derive.** The default tie-break everywhere is the most restrictive option:
**deny / halt / refuse**. If a needed rule is missing, choose the restrictive option and escalate.

The skills also auto-load by filename/keyword, so the right guidance is in front of you exactly when you
open the relevant file. Trust that, and read the contract before writing.

---

## 9. Working in parallel (the dispatch waves)

Once the frozen surface (§3) exists, the orchestrator parallelizes everything the dependency graph allows:

- **Wave 0:** freeze `core/ports` + `core/types` + `core/errors` (orchestrator, blocking — nothing else starts).
- **Wave 1 (parallel):** K·01 Policy · K·02 Ledger. (Both depend only on the spine; independent of each other.)
- **Wave 2 (parallel):** K·03 HITL · K·05 Gateway · K·07 Events — each behind its frozen ports;
  adapter implementers start in parallel with their core layer as soon as the port is frozen.
- **Wave 3:** K·06 Process · K·04 Consent.
- **Wave 4:** K·08 Registry → then K·09/K·10/K·11 in parallel.
- **Wave 5:** K·13 Sandbox · K·12 Incident · K·14 RegMap.

The build journal holds the live graph; the build order (spec §6) holds the *why* of each dependency.
Never start a unit whose Definition of Ready is unmet.

---

## 10. Anti-patterns (multi-agent failure modes — do not do these)

- **Silent interface drift** — editing a frozen signature/field/error without an ADR. → §3.
- **Cross-directory edits** — fixing something in another agent's directory. → escalate. §4.
- **Re-deriving a settled decision** differently than the skill/ADR says. → apply the contract. §8.
- **Reaching around an interface** instead of through it. → it's an interface change. §6.
- **Self-approval** — the author merging its own unit. → reviewer + CI required. §1, §7.
- **Weakening a test** to get green, or accepting a fail-open. → that's a defect, not a fix. §7.
- **Long-lived branches** — integrate in small batches against trunk. Parallel agents + stale branches = merge hell.
- **Carrying state in your head** — anything another agent must know goes in the journal/ADR/PR, not your reasoning.

---

## 11. Escalation

Escalate to the orchestrator (do **not** improvise) when:

- a frozen interface needs to change;
- two units appear to need the same file;
- a Frozen ADR (F-01–F-11) seems to block a real requirement;
- a dependency you need isn't done or doesn't expose what you need;
- the spec, a skill, and reality disagree and the restrictive default isn't obviously right.

The orchestrator resolves it, records it as an ADR if it sets precedent, and updates this file or the
journal so the next cold agent inherits the answer.

---

*If you remember two things from this file: **interfaces are frozen — change them only via the orchestrator + an ADR**, and **fail closed — deny/halt on any doubt.** Everything else follows from those.*
