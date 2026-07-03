# Python SDK Reference

Covers `Kernel.from_config()`, `@kernel.governed` / `@kernel.governed_tool`, `kernel.guard` /
`kernel.wrap`, `kernel.generate()`, `kernel.for_agent()`, the exception surface, the async-approval
helpers, and `GovernanceProfile` presets. Everything below imports from `delivery.sdk`.

## Quick reference

```python
from delivery.sdk import Kernel, GovernanceProfile

# Initialize from config file
kernel = Kernel.from_config("kernel.toml")

# Decorate any async function - signature unchanged
@kernel.governed(policy="credit.approve")
async def approve_credit(loan_id: str, amount: float) -> dict:
    return {"status": "approved", "loan_id": loan_id, "amount": amount}

# Use it normally - governance is transparent
result = await approve_credit("L-9821", 75000.0)

# Or use a GovernanceProfile preset
@kernel.governed(policy="credit.approve", profile=GovernanceProfile.FULL)
async def approve_credit_full_audit(loan_id: str, amount: float) -> dict:
    ...
```

## Exceptions & error semantics

Everything is importable from `delivery.sdk`. There are two kinds of exception:

**Governance outcomes** — a decision the kernel made about your action. Catch these to react.

| Exception | Code | Raised when | How to handle |
|-----------|------|-------------|---------------|
| `LifecycleDeniedError` | `LIFECYCLE_DENIED` | Policy denied the action (at evaluate or gate). | Terminal — do **not** retry. Surface as a 403-style refusal. |
| `LifecycleHaltedError` | `LIFECYCLE_HALTED` | An internal fault (e.g. the ledger seal failed) — fail-closed. | The action did **not** take effect. Retry only if the cause is transient. |
| `LifecyclePendingApprovalError` | `LIFECYCLE_PENDING_APPROVAL` | A `require_approval` policy suspended the action durably. **Not a failure.** | A human must decide — see [Async approval](#async-approval). `exc.detail` carries `action_id` and `handle_id`. |

**SDK misuse** — a programmer error in how the SDK was called. Fix the call site.

| Exception | Code | Raised when |
|-----------|------|-------------|
| `SdkUsageError` | `SDK_USAGE_ERROR` | No actor in scope for `guard`/`wrap`/`governed`/`governed_tool`/`proxy`, or `kernel.generate` with no inference adapter configured. |

All of the above subclass `QUAICUError` (also re-exported), so `except QUAICUError:` is a valid
catch-all. Every instance carries a stable `.code` string and a `.detail` dict.

```python
from delivery.sdk import LifecycleDeniedError, LifecyclePendingApprovalError

try:
    async with kernel.actor_context(user):
        await approve_credit("L-9821", 75000.0)
except LifecycleDeniedError:
    ...                                   # policy said no — terminal
except LifecyclePendingApprovalError as exc:
    handle_id = exc.detail["handle_id"]   # route a human to decide
```

## Async approval

A `require_approval` action **suspends durably** and raises `LifecyclePendingApprovalError` instead
of blocking or timing out. Resume it from the `handle_id` on the caught exception:

```python
try:
    async with kernel.actor_context(maker):
        await transfer(amount=50_000, to="ACC-2")
except LifecyclePendingApprovalError as exc:
    # A *different* authorized approver decides (self-approval is blocked by the kernel):
    await kernel.approve(exc.detail["handle_id"], actor=checker)   # execute → seal → COMPLETED
    # ...or
    await kernel.reject(exc.detail["handle_id"], actor=checker)    # → DENIED
```

`approve` / `reject` are ergonomic wrappers over `kernel.decide_approval(handle_id,
decision=..., actor=...)`. Approvals also resolve out-of-band via `/v1/approvals`, a signed email/
Teams link, or the in-browser member console — the same durable record. Runnable end-to-end:
[`examples/sdk-approval-demo/`](https://github.com/quaicu/kernel/tree/main/examples/sdk-approval-demo).

## GovernanceProfile presets

| Preset | HITL | Ledger | Explainability | Use case |
|--------|------|--------|---------------|----------|
| `LITE` | Policy-driven | Hash only | Off | High-volume, low-risk |
| `STANDARD` | Policy-driven | Full seal | Off | Default |
| `FULL` | Always | Full seal | On | Regulated decisions |
| `AUDIT` | Always | Full seal + proof | On | Regulator-facing |
