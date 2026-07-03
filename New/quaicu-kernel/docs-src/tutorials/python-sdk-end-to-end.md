# Python SDK End-to-End

Govern an existing function with one decorator, then handle the three outcomes it can produce —
**allowed**, **denied**, and **pending human approval** — using only the `delivery.sdk` surface.

**What you'll learn:**

- Wrapping an existing async function with `@kernel.guard` (signature unchanged)
- Binding the acting identity with `kernel.actor_context(...)`
- Catching the typed governance exceptions
- Driving the async maker-checker approval loop with `kernel.approve` / `kernel.reject`

A complete, runnable version of everything below lives in
[`examples/sdk-approval-demo/`](https://github.com/quaicu/kernel/tree/main/examples/sdk-approval-demo)
(`python examples/sdk-approval-demo/demo.py`, zero external services).

## 1. Govern a function

`@kernel.guard` governs an existing function **without changing its signature or call-sites**. The
acting identity comes from `kernel.actor_context(...)` at the request boundary:

```python
from delivery.sdk import Kernel

kernel = Kernel.from_config("kernel.toml")

@kernel.guard(policy="payments.transfer")
async def transfer(*, amount: int, to: str) -> dict:
    return await bank.transfer(amount, to)      # unchanged body

async with kernel.actor_context(current_user_actor):
    result = await transfer(amount=5_000, to="ACC-2")   # unchanged call-site
```

On **ALLOW** the function runs and returns normally, and the action is sealed to the K·02 ledger.

## 2. Handle a denial

If policy denies the action, the call raises `LifecycleDeniedError` — terminal, do not retry:

```python
from delivery.sdk import LifecycleDeniedError

try:
    async with kernel.actor_context(user):
        await transfer(amount=10_000_000, to="ACC-9")
except LifecycleDeniedError as exc:
    return refuse(reason=exc.detail)     # e.g. surface a 403 to your caller
```

## 3. Handle human approval (async maker-checker)

A `require_approval` policy **suspends the action durably** and raises
`LifecyclePendingApprovalError` — this is *not* a failure. The exception carries the `handle_id` an
approver decides against:

```python
from delivery.sdk import LifecyclePendingApprovalError

try:
    async with kernel.actor_context(maker):
        await transfer(amount=250_000, to="ACC-7")
except LifecyclePendingApprovalError as exc:
    handle_id = exc.detail["handle_id"]
    # The action now waits durably. A *different* authorized approver decides — the kernel blocks
    # self-approval (separation of duties):
    await kernel.approve(handle_id, actor=checker)   # → resumes, executes, seals → COMPLETED
    # ...or  await kernel.reject(handle_id, actor=checker)   # → DENIED
```

The approver need not be in the same process: the same pending record is decidable via `/v1/approvals`,
a signed email/Microsoft Teams link, or the in-browser compliance console — whichever channel the
deployment configured. `approve`/`reject` are thin wrappers over `kernel.decide_approval(...)`.

## 4. A note on misuse vs. outcomes

Governance *outcomes* are the `Lifecycle*` exceptions above. A *programmer* error — calling a
guarded function with no actor in scope, or `kernel.generate` with no inference adapter — raises
`SdkUsageError`. Both, plus the `QUAICUError` root, import from `delivery.sdk`. See the
[SDK Reference → Exceptions](../reference/sdk/kernel-class.md#exceptions--error-semantics).
