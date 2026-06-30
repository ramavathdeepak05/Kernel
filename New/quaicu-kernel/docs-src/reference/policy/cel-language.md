# CEL Policy Language Reference

QUAICU policies are evaluated using **CEL (Common Expression Language)**: a deterministic, non-Turing-complete, sandboxed expression language. CEL is guaranteed to terminate and cannot produce side effects.

---

## What a policy is

QUAICU governs **actions** (e.g. `loan.approve`, `email.send`, `record.delete`). A policy has two parts:

1. A **condition**: a CEL boolean expression describing which actions the policy applies to
2. A **decision**: what to do when the condition is true: `allow`, `deny`, or `require_approval`

Read it as: **"IF `<condition>` THEN `<decision>`."**

---

## CEL variables

The kernel flattens each action into a fixed set of CEL variables. **Use these exact names, no others exist.**

| Variable | Type | Example |
|----------|------|---------|
| `action_type` | `string` | `action_type == "loan.approve"` |
| `action_tenant` | `string` | `action_tenant == "acme"` |
| `actor_id` | `string` | `actor_id == "svc:batch"` |
| `actor_roles` | `list<string>` | `"role:analyst" in actor_roles` |
| `payload_<field>` | `string \| int \| double \| bool` | `payload_amount > 1000000` |

!!! note "Payload variables"
    Only top-level scalar payload fields are typed. `payload.amount` is **wrong**: use `payload_amount`. Nested objects arrive as their string form.

There are no time, date, request, or environment variables. If a value isn't in the action payload, it isn't available in CEL.

---

## Decisions

| Decision | Meaning |
|----------|---------|
| `allow` | Action proceeds without human intervention |
| `deny` | Action is blocked immediately |
| `require_approval` | Action is held pending a named human approver |

### Conflict resolution

When multiple policies match one action, the result is:

**`deny` > `require_approval` > `allow`** (deny always wins)

### Fail-closed behavior

If a condition errors at runtime (type mismatch, missing variable, any exception) → the evaluation returns **DENY**. Write total, type-correct conditions that cannot error.

Actions matched by **no** active policy fall through to the deployment's default decision (typically `deny` in a fail-closed setup).

---

## CEL syntax reference

```cel
// Logical operators
a && b    // AND
a || b    // OR
!a        // NOT

// Comparison
== != < <= > >=

// Arithmetic
+ - * / %

// Membership
"role:admin" in actor_roles     // list membership
"prefix" in some_string         // substring (use .contains() instead)

// Ternary
cond ? a : b

// String methods
s.startsWith("prefix")
s.endsWith("suffix")
s.contains("substring")
s.matches("regex")

// Size
size(actor_roles) == 0
size("hello") == 5
```

!!! warning "Do not"
    - Invent functions not listed here
    - Reference variables not listed in the variables table
    - Use dotted payload names (`payload.amount` is wrong, use `payload_amount`)
    - Write multi-statement code, a condition is one boolean expression

---

## Policy envelope format

```yaml
id: credit.high_value_approval
version: 3
governs: credit.approve
condition: |
  action_type == "credit.approve"
  && payload_amount > 5000000
  && "role:underwriter" in actor_roles
decision: require_approval
approvers: ["role:risk_head"]
regulatory_refs: ["rbi.ifrs9.staging"]
lifecycle: ACTIVATED
```

See [Policy Lifecycle →](lifecycle.md) for the DRAFT → ACTIVATED flow.

---

## Worked examples

```json title="High-value loan requires approval"
{
  "condition": "action_type == \"loan.approve\" && payload_amount > 1000000",
  "decision": "require_approval",
  "explanation": "Loan approvals over ₹10L need a human approver."
}
```

```json title="Only admins can delete records"
{
  "condition": "action_type == \"record.delete\" && !(\"role:admin\" in actor_roles)",
  "decision": "deny",
  "explanation": "Only admins may delete records."
}
```

```json title="External email requires review"
{
  "condition": "action_type == \"email.send\" && payload_recipient_external == true",
  "decision": "require_approval",
  "explanation": "Outbound email to external recipients is reviewed before sending."
}
```

```json title="Block PII for a specific tenant"
{
  "condition": "action_type == \"model.invoke\" && payload_contains_pii == true && action_tenant == \"eu-bank\"",
  "decision": "deny",
  "explanation": "Block model calls carrying PII for the EU tenant."
}
```

```json title="Auto-allow small refunds"
{
  "condition": "action_type == \"refund.issue\" && payload_amount <= 100",
  "decision": "allow",
  "explanation": "Auto-allow small refunds up to ₹100."
}
```

---

## Using an LLM to write policies

This reference is designed to be pasted into an LLM as context. Ask:

> "Using these rules, write a QUAICU policy that [your requirement]."

Always review the result and run it through the **draft → backtest → activate** flow before enforcing. See [Write a Policy →](../../how-to/write-a-policy.md).
