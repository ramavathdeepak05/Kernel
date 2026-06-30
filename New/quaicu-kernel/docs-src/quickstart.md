# Quickstart: Docker in 60 Seconds

Get the QUAICU Governance Kernel running locally, make your first governed call, and see a sealed ledger entry, all in under 60 seconds.

## Prerequisites

- Docker + Docker Compose (v2)
- `curl`

No Python, no database setup, no keys. The Docker Compose file includes a local Postgres instance.

---

## 1. Clone and start

```bash
git clone https://github.com/ramavathdeepak05/Kernel.git
cd Kernel/New/quaicu-kernel/delivery/docker
docker compose up --build
```

Wait for:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:7000
```

This takes about 30–60 seconds on first run (Python deps + Postgres migration).

---

## 2. Verify the kernel is running

```bash
curl http://localhost:7000/health
```

Expected response:
```json
{"status": "ok", "version": "0.1.0", "tenant": "starter"}
```

The interactive API docs are at **[http://localhost:7000/docs](http://localhost:7000/docs)**.

---

## 3. Your first governed action

```bash
curl -X POST http://localhost:7000/v1/actions/propose \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key-starter" \
  -d '{
    "action_type": "document.approve",
    "payload": {"document_id": "DOC-001", "amount": 1000},
    "actor": {"id": "user-1", "roles": ["staff"]}
  }'
```

Expected response:
```json
{
  "action_id": "act_01j...",
  "decision": "ALLOW",
  "seal": {
    "ledger_seq": 1,
    "hash": "sha256:abc123...",
    "signed_at": "2026-06-28T10:00:00Z"
  },
  "elapsed_ms": 12
}
```

The decision was evaluated against active policies, executed, and sealed to the immutable audit ledger in a single call.

---

## 4. See the ledger entry

```bash
curl http://localhost:7000/v1/ledger/trail \
  -H "X-API-Key: dev-key-starter"
```

You'll see the append-only log of every governed action, each with its hash, actor, decision, and timestamp.

---

## 5. Try a policy denial

```bash
curl -X POST http://localhost:7000/v1/actions/propose \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key-starter" \
  -d '{
    "action_type": "document.approve",
    "payload": {"document_id": "DOC-002", "amount": 999999},
    "actor": {"id": "user-1", "roles": ["staff"]}
  }'
```

If a high-value policy is active, this returns `"decision": "DENY"`: the action was blocked before execution. Nothing was written to the ledger.

---

## What just happened

Every call went through the full governance lifecycle:

```
PROPOSE → EVALUATE → GATE → EXECUTE → SEAL → EMIT
```

1. **PROPOSE**: action received with an idempotency key
2. **EVALUATE**: policies checked (CEL expressions), consent verified, model registry consulted
3. **GATE**: human approval routed if policy required it
4. **EXECUTE**: state change executed via durable workflow
5. **SEAL**: result written to the RFC-6962 Merkle tree and HSM-signed
6. **EMIT**: structured event published after seal

Any failure at any step → **DENY** or **HALT**. No silent passthrough.

---

## Next steps

<div class="grid cards" markdown>

- **[Your First Governed Action →](tutorials/first-governed-action.md)**  
  End-to-end tutorial with a real use case (loan approval with HITL)

- **[Write a Policy →](how-to/write-a-policy.md)**  
  Define your own CEL rules and activate them

- **[Python SDK End-to-End →](tutorials/python-sdk-end-to-end.md)**  
  Embed the kernel directly in your Python application

- **[Deploy Sovereign →](how-to/deploy-sovereign.md)**  
  Production deployment on your own infrastructure

</div>
