# SKILLS.md — Directory → Skill routing map (READ-FIRST protocol)

> **Why this file exists.** `AGENTS.md` used to say skills "auto-load from `.agents/skills/`
> when you open the matching files." **They do not.** No harness here injects on-disk skills into
> the coding agent's context, and `SKILL.md` triggers are prose, not machine-readable globs — so
> nothing routes a directory to its skill. This file is that router. It is mechanical, not magic:
> **you read the skill yourself.**
>
> The library has been **curated to 26 project skills** (the `quaicu-*` layer skills + the stack
> skills this build actually uses). The generic community catalogue and **all `alis-*` domain
> skills** were removed: `core/` carries **zero domain terms** (F-08, §8), so ALIS-product skills
> have no place here. The same 26 are registered in `.claude/skills/` for Claude Code's Skill tool.

## The protocol (harness-agnostic — works in Antigravity *or* Claude Code)

Before writing **any** code in a directory below, you **MUST** open and read the mapped
`SKILL.md` in full with your Read tool. Each `quaicu-*` skill begins with a **Deterministic
Decision Contract** — apply it mechanically; do not re-derive.

- **Orchestrator:** every work brief must paste the exact skill path from this table and state
  "Read this before writing code." A unit's Definition of Ready is **not met** until its skill is read.
- **Implementer:** if your brief named no skill, find your directory here and read it. If your
  directory isn't listed, read `quaicu-kernel-arch/SKILL.md` and escalate.
- **Reviewer:** reject any unit whose code contradicts its mapped skill's contract.

All paths are relative to `.agents/skills/`.

## Core kernel — the 14 layers + spine

| When you build / touch… | Layer | Read FIRST |
|---|---|---|
| `core/ports/`, `core/types.py`, `core/errors.py`, the hexagonal boundary, anything cross-cutting | architecture (all) | `quaicu-kernel-arch/SKILL.md` |
| `core/lifecycle/` — the `ActionState` machine, propose→evaluate→**gate (K·03 HITL)**→execute→seal→emit; the SDK `@governed` decorator | spine **+ K·03** | `quaicu-governed-lifecycle/SKILL.md` |
| `core/policy/` — CEL evaluation, conflict resolution, simulation→activation gate | **K·01** | `quaicu-policy-engine/SKILL.md` |
| `core/ledger/` — Merkle tree, inclusion/consistency proofs, signed tree heads, seal | **K·02** | `quaicu-trust-ledger/SKILL.md` **+** `cryptography/SKILL.md` |
| `core/consent/` — DPDP consent as a second evaluate-time signal | **K·04** | `quaicu-consent/SKILL.md` |
| `core/gateway/` — the AI / inference gateway | **K·05** | `quaicu-ai-gateway/SKILL.md` |
| `core/process/` — the durable process / workflow engine | **K·06** | `quaicu-process-engine/SKILL.md` |
| `core/events/` — event bus, emit-after-seal, at-least-once delivery | **K·07** | `quaicu-event-bus/SKILL.md` |
| `core/registry/` — per-tenant model allowlist | **K·08** | `quaicu-model-registry/SKILL.md` |
| `core/fairness/`, `core/drift/`, `core/explain/` — assurance sweeps | **K·09 · K·10 · K·11** | `quaicu-assurance/SKILL.md` |
| `core/incident/` — rollback as a governed action | **K·12** | `quaicu-replayability/SKILL.md` **+** `quaicu-process-engine/SKILL.md` |
| `core/sandbox/` — counterfactual replay (F-10 backtest) | **K·13** | `quaicu-replayability/SKILL.md` |
| `core/regmap/` — regulation catalog + point-in-time signed evidence packs | **K·14** | `quaicu-regmap/SKILL.md` |

## Cross-cutting

| When you build / touch… | Read FIRST |
|---|---|
| replay fidelity, side-effect-free re-derivation, event-sourced shape (F-09) | `quaicu-replayability/SKILL.md` |
| `core/control_plane/`, anything crossing a tenant boundary (F-07) | `quaicu-tenant-isolation/SKILL.md` |
| any tests, conformance/property/chaos suites, CI, coverage floors | `quaicu-testing/SKILL.md` |

## Adapters · delivery · deployment (outside `core/` — no domain rules, stack skills apply)

| When you build / touch… | Read FIRST |
|---|---|
| `adapters/storage/` — Postgres, schema-per-tenant, RLS | `sqlalchemy-postgres/SKILL.md`, `postgres-best-practices/SKILL.md`, `quaicu-tenant-isolation/SKILL.md` |
| `migrations/` — Alembic (per-schema, per-tenant rollout) | `sqlalchemy-alembic-expert-best-practices-code-review/SKILL.md`, `quaicu-tenant-isolation/SKILL.md` |
| `adapters/inference/` — local backend (Ollama) | `quaicu-ai-gateway/SKILL.md` (port + governance) **+** `ollama/SKILL.md` (backend) |
| `adapters/workflow/` — Postgres state-machine / Temporal | `quaicu-process-engine/SKILL.md` |
| `delivery/api/` — FastAPI REST | `fastapi-python/SKILL.md` |
| `delivery/docker/` — Dockerfile, compose, Helm, k3s/K8s | `k8s-helm/SKILL.md` |
| Admin console — React 19 + TypeScript | `react-vite-best-practices/SKILL.md`, `shadcn-ui-builder/SKILL.md`, `fullstack-developer/SKILL.md` |
| any pgvector / vector-search work | `pgvector-semantic-search/SKILL.md` |
| multi-tenant scaling design (background; `quaicu-tenant-isolation` is authoritative) | `multi-tenant-saas-architecture/SKILL.md` |

## Notes

- **K·12 Incident** has no single dedicated skill: it is rollback executed as a governed action, so
  read `quaicu-process-engine` (durable rollback workflow) **+** `quaicu-replayability` (reconstruct
  pre-incident state) together, against the spec's §6 K·12 DoD.
- The five `quaicu-{consent,event-bus,model-registry,assurance,regmap}` skills are **scaffolds**:
  their Decision Contracts are authoritative, but the implementation sections are to be fleshed out
  from the spec's per-layer DoD. Treat the contract as binding; escalate gaps to the orchestrator.

## Precedence (unchanged from AGENTS.md §2)

Build spec **Frozen ADRs (F-01–F-11)** > the mapped skill's Decision Contract > everything else.
On any conflict or missing rule, choose the most restrictive option (**deny / halt / refuse**) and escalate.
