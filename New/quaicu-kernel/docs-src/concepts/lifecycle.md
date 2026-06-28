# Action Lifecycle

Every AI action in the QUAICU Kernel follows one non-bypassable sequence. There are no shortcuts, no bypass codes, and no privileged paths.

```
PROPOSE → EVALUATE → GATE → EXECUTE → SEAL → EMIT
```

---

## Phase breakdown

### 1. PROPOSE

The action enters the kernel with an idempotency key. If the same key is submitted twice, the second call returns the result of the first — the action is never executed twice.

**Input:** `action_type`, `payload`, `actor`, `idempotency_key`  
**Output:** `action_id`

### 2. EVALUATE

The action is evaluated against:

- All activated policies (K·01 — CEL evaluation)
- DPDP consent for any data subjects in the payload (K·04)
- The model registry if the action involves model invocation (K·08)

**Decision options:**

| Decision | Next phase |
|----------|-----------|
| `ALLOW` | GATE (if policy requires approval) or EXECUTE |
| `DENY` | Terminal — action blocked, ledger not written |
| `REQUIRE_APPROVAL` | GATE |

**Any evaluation error → DENY.** No exceptions.

### 3. GATE (conditional)

If any policy returned `require_approval`, the action is held. A notification is sent to the designated approver(s) via the HITL adapter (K·03).

- **Approved:** proceed to EXECUTE
- **Rejected:** terminal — DENIED
- **Timeout:** terminal — REJECTED (never auto-approved)

If no policy required approval, this phase is skipped.

### 4. EXECUTE

The action's state change is carried out via the Process Engine (K·06). Execution is durable — if the process crashes mid-execution, it resumes from the last checkpoint on restart.

**Failure → HALT.** The action enters a halted state and is not sealed.

### 5. SEAL

The result is written to the RFC-6962 Merkle transparency log (K·02) and signed by the deployment's HSM. The seal contains:

- `ledger_seq` — monotonically increasing position in the log
- `leaf_hash` — SHA-256 of the canonical action record
- `inclusion_proof` — Merkle path to the current tree root
- `signed_tree_head` — Ed25519 or ECDSA signature over the root

**Seal failure → HALTED.** An action is not considered complete until it is sealed.

### 6. EMIT

Structured events are published to the event bus (K·07) after the seal succeeds. This ordering guarantee means consumers only ever see events for sealed, proven actions.

Emit failures are logged. The seal is never rolled back due to an emit failure.

---

## Fail-closed guarantee

Any failure, timeout, or error at any phase → **DENY or HALT**. There is no fallback to "allow on error." The kernel never fails open.

---

## Idempotency

Submit the same `idempotency_key` twice → you receive the original result. The action is not executed again. This makes retries safe.
