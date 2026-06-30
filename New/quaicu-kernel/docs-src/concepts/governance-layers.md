# Governance Layers

The QUAICU Kernel is built from 14 governance layers. All 14 are built; K·01–K·08 are production-ready.

---

## Core layers (K·01–K·08) · Production

### K·01: Policy Engine

**Purpose:** Evaluate CEL-based rules against every proposed action.

Every action is evaluated against all active policies before execution. If multiple policies match, `deny` beats `require_approval` beats `allow`. Any CEL evaluation error → automatic **DENY** (fail-closed).

**Failure mode:** CEL error or missing variable → DENY.

### K·02: TrustLedger

**Purpose:** Cryptographic, tamper-proof audit record of every sealed action.

Every executed action is written to an RFC-6962 Merkle transparency log. Each entry is signed by the deployment's HSM (OpenBao Ed25519 or Cloud KMS ECDSA P-256). The ledger is append-only, no entry can be modified or deleted.

**Failure mode:** Seal failure → HALTED. The action is not considered complete until it is sealed.

### K·03: HITL Gate

**Purpose:** Human-in-the-loop enforcement before execution.

When a policy returns `require_approval`, the action is held until a named approver accepts or rejects it. Timeout → **REJECTED** (never auto-approved). The HITL gate cannot be bypassed by any actor, including privileged users or the kernel itself.

**Failure mode:** Timeout → REJECTED. Approver rejection → DENIED.

### K·04: DPDP Consent

**Purpose:** Purpose-bound consent verification at evaluation time.

Before any action that touches personal data, the consent engine verifies that the data subject has given valid, purpose-specific consent. Invalid or missing consent → DENY.

**Failure mode:** Missing or expired consent → DENY.

### K·05: AI Gateway

**Purpose:** Controlled interface to AI models, routing, PII masking, prompt logging, token budgets.

Every model call goes through the AI Gateway. PII is detected and masked before transmission. Every prompt is logged (an unlogged call is a denied call). Model routing enforces the allowlist from K·08. Token budgets prevent cost overruns.

**Failure mode:** PII masking failure → DENY. Prompt log failure → DENY. Budget exceeded → DENY.

### K·06: Process Engine

**Purpose:** Durable, replay-safe workflow orchestration.

Multi-step actions are executed via a durable state machine (Postgres state-machine or Temporal). Steps are idempotent. The engine can resume from any intermediate state after a crash.

**Failure mode:** Workflow failure → HALT.

### K·07: Event Bus

**Purpose:** Structured events emitted after every sealed action.

Events are published only after a successful seal (K·02). This guarantees that consumers only see events for actions that are cryptographically sealed. Emit failures are logged but do not roll back a completed seal.

**Failure mode:** Emit failure → logged. Seal is not rolled back.

### K·08: Model Registry

**Purpose:** Per-tenant allowlist of approved AI models.

The kernel refuses to route calls to models not in the registry. Any model invocation bypasses the registry only if explicitly opted out in config (not available in production profiles).

**Failure mode:** Model not in registry → DENY.

---

## Extended layers (K·09–K·14) · Built, awaiting pilot

### K·09: Fairness

Async background sweeps detecting demographic disparity across governed decisions.

### K·10: Drift Monitor

Detects semantic drift in model behavior by comparing output embeddings against a registered baseline.

### K·11: Explainability

Reconstructs why any past decision was made, which policies fired, which actor triggered them, what the payload contained at decision time.

### K·12: Incident Engine

Post-breach rollback orchestration. Reversal actions are themselves governed (they pass through the full lifecycle).

### K·13: Sandbox

Safe "what if" replay environment. Test policy changes against historical actions without affecting live traffic.

### K·14: Regulatory Mapping

Maps activated policies to specific regulatory requirements (RBI FREE-AI, DPDP, GDPR, EU AI Act). Generates signed evidence packs for auditors.
