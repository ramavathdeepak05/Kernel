# Write a Policy

This guide walks through creating a new governance policy — from writing the CEL condition to activating it in production.

## Policy lifecycle

```
DRAFT → REVIEW → BACKTEST → SHADOW_MODE → ACTIVATED → DEPRECATED
```

A policy must pass through every stage before it can block real actions. This prevents accidental denials.

---

## Step 1 — Write the condition

Policies use CEL (Common Expression Language). See the full [CEL Reference →](../reference/policy/cel-language.md).

**Example:** Loan approvals above ₹50L require a risk officer's approval.

```json
{
  "condition": "action_type == \"loan.approve\" && payload_amount > 5000000",
  "decision": "require_approval",
  "approvers": ["role:risk_officer"]
}
```

**Rules:**
- Use only the [allowed variables](../reference/policy/cel-language.md#cel-variables) — `action_type`, `actor_roles`, `payload_<field>`, etc.
- One boolean expression per condition — no multi-statement code
- Type-correct: integer payload → `payload_amount > 5000000` (not `> "5000000"`)

---

## Step 2 — Create the policy (DRAFT)

```bash
curl -X POST http://localhost:7000/v1/policies \
  -H "X-API-Key: $QUAICU_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "loan.high_value_approval",
    "governs": "loan.approve",
    "condition": "action_type == \"loan.approve\" && payload_amount > 5000000",
    "decision": "require_approval",
    "approvers": ["role:risk_officer"]
  }'
```

The policy is created in **DRAFT** state — it has no effect on live traffic.

---

## Step 3 — Run a backtest

```bash
curl -X POST http://localhost:7000/v1/policies/loan.high_value_approval/backtest \
  -H "X-API-Key: $QUAICU_KEY"
```

The backtest replays recent historical actions against the new policy and returns an impact report:
- How many actions would have been affected
- Which actors would have been routed to approvers
- Any condition errors (type mismatches, missing variables)

Fix any errors before proceeding.

---

## Step 4 — Shadow mode

```bash
curl -X PATCH http://localhost:7000/v1/policies/loan.high_value_approval \
  -H "X-API-Key: $QUAICU_KEY" \
  -d '{"lifecycle": "SHADOW_MODE"}'
```

In shadow mode, the policy evaluates against live traffic and logs what it *would* do — without actually blocking or routing to approvers. Monitor for unexpected denials.

---

## Step 5 — Activate

Once you're satisfied:

```bash
curl -X PATCH http://localhost:7000/v1/policies/loan.high_value_approval \
  -H "X-API-Key: $QUAICU_KEY" \
  -d '{"lifecycle": "ACTIVATED"}'
```

The policy is now live. All matching actions will be evaluated against it.

---

## Conflict resolution

If multiple policies match one action, the result is: **`deny` beats `require_approval` beats `allow`**.

Write policies at the most specific scope possible to avoid unintended interactions.

---

## See also

- [CEL Policy Language Reference →](../reference/policy/cel-language.md)
- [Policy Lifecycle →](../reference/policy/lifecycle.md)
