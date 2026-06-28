# Python SDK Reference

!!! info "Coming soon"
    Full SDK reference is being written. It covers `Kernel.from_config()`, `@kernel.governed`, `@kernel.governed_tool`, `kernel.generate()`, `kernel.for_agent()`, and `GovernanceProfile` presets (LITE, STANDARD, FULL, AUDIT).

## Quick reference

```python
from delivery.sdk import Kernel, GovernanceProfile

# Initialize from config file
kernel = Kernel.from_config("kernel.toml")

# Decorate any async function — signature unchanged
@kernel.governed(policy="credit.approve")
async def approve_credit(loan_id: str, amount: float) -> dict:
    return {"status": "approved", "loan_id": loan_id, "amount": amount}

# Use it normally — governance is transparent
result = await approve_credit("L-9821", 75000.0)

# Or use a GovernanceProfile preset
@kernel.governed(policy="credit.approve", profile=GovernanceProfile.FULL)
async def approve_credit_full_audit(loan_id: str, amount: float) -> dict:
    ...
```

## GovernanceProfile presets

| Preset | HITL | Ledger | Explainability | Use case |
|--------|------|--------|---------------|----------|
| `LITE` | Policy-driven | Hash only | Off | High-volume, low-risk |
| `STANDARD` | Policy-driven | Full seal | Off | Default |
| `FULL` | Always | Full seal | On | Regulated decisions |
| `AUDIT` | Always | Full seal + proof | On | Regulator-facing |
