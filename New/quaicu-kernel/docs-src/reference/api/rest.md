# REST API Reference

The QUAICU Kernel REST API is a FastAPI application. Interactive docs (Swagger UI) are available at `/docs` and OpenAPI spec at `/openapi.json` on any running instance.

## Authentication

All requests require an API key in the `X-API-Key` header:

```bash
-H "X-API-Key: qk_live_..."
```

Dev instances accept `dev-key-starter` without configuration.

## Base URL

```
https://your-kernel/v1/
```

---

## Actions

### POST /v1/actions/propose

Submit an action for governance evaluation.

**Request:**
```json
{
  "action_type": "loan.approve",
  "payload": {
    "loan_id": "L-9821",
    "amount": 75000
  },
  "actor": {
    "id": "user-123",
    "roles": ["role:underwriter"]
  },
  "idempotency_key": "req-abc-123"
}
```

**Response (ALLOW):**
```json
{
  "action_id": "act_01j...",
  "decision": "ALLOW",
  "seal": {
    "ledger_seq": 1,
    "hash": "sha256:abc...",
    "signed_at": "2026-06-28T10:00:00Z"
  },
  "elapsed_ms": 12
}
```

**Response (DENY):**
```json
{
  "action_id": "act_01j...",
  "decision": "DENY",
  "denial_reason": "policy:loan.high_value_approval",
  "elapsed_ms": 8
}
```

**Response (REQUIRE_APPROVAL):**
```json
{
  "action_id": "act_01j...",
  "decision": "REQUIRE_APPROVAL",
  "approval_id": "appr_01j...",
  "approvers": ["role:risk_head"],
  "expires_at": "2026-06-28T11:00:00Z"
}
```

---

## Ledger

### GET /v1/ledger/trail

Returns the append-only audit trail for the current tenant.

```bash
curl http://localhost:7000/v1/ledger/trail \
  -H "X-API-Key: $QUAICU_KEY"
```

### GET /v1/ledger/{ledger_seq}/proof

Returns the RFC-6962 inclusion proof for a specific ledger entry.

---

## Policies

### GET /v1/policies

List all policies for the current tenant.

### POST /v1/policies

Create a new policy (starts in DRAFT lifecycle).

### PATCH /v1/policies/{policy_id}

Update a policy (advance lifecycle, edit condition).

### POST /v1/policies/{policy_id}/backtest

Run a backtest against historical actions.

---

## Approvals

### GET /v1/approvals

List pending HITL approvals.

### POST /v1/approvals/{approval_id}/approve

Approve a pending action.

### POST /v1/approvals/{approval_id}/reject

Reject a pending action.

---

## Health

### GET /health

Returns kernel status. No auth required.

```json
{"status": "ok", "version": "0.1.0", "tenant": "starter"}
```

!!! info "Full interactive docs"
    Run the kernel locally and visit [http://localhost:7000/docs](http://localhost:7000/docs) for the complete Swagger UI with live request testing.
