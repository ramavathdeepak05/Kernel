# Policy Lifecycle

Every policy in the QUAICU Kernel follows a mandatory lifecycle. You cannot skip stages, each transition requires explicit action.

```
DRAFT → REVIEW → BACKTEST → SHADOW_MODE → ACTIVATED → DEPRECATED
```

## Stages

| Stage | What it means | Effect on live traffic |
|-------|--------------|----------------------|
| `DRAFT` | Initial state after creation | None |
| `REVIEW` | Submitted for team review | None |
| `BACKTEST` | Running against historical actions | None (read-only replay) |
| `SHADOW_MODE` | Evaluating against live traffic, logging only | Logs would-be decisions, no enforcement |
| `ACTIVATED` | Actively enforced | Full enforcement on matching actions |
| `DEPRECATED` | Retired | None |

## Transitions

```bash
# Create (starts as DRAFT)
POST /v1/policies

# Advance to REVIEW
PATCH /v1/policies/{id} -d '{"lifecycle": "REVIEW"}'

# Run backtest (required before SHADOW_MODE)
POST /v1/policies/{id}/backtest

# Advance to SHADOW_MODE
PATCH /v1/policies/{id} -d '{"lifecycle": "SHADOW_MODE"}'

# Activate
PATCH /v1/policies/{id} -d '{"lifecycle": "ACTIVATED"}'

# Deprecate
PATCH /v1/policies/{id} -d '{"lifecycle": "DEPRECATED"}'
```

## Rollback

To roll back an active policy, deprecate it. The kernel immediately stops evaluating deprecated policies against live traffic. A rollback does not affect actions that were already sealed.

## See also

[Write a Policy →](../../how-to/write-a-policy.md)
