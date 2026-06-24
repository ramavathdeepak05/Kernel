# QUAICU underwriting demo — *governed → gated → sealed → verify*

A runnable demo of **use-case 1 (credit-underwriting assist, HITL-gated)** from
[`docs/gtm/PILOT_USE_CASES.md`](../../docs/gtm/PILOT_USE_CASES.md). It's the strategy memo's
"10-minute activation demo": an AI drafts credit decisions, the kernel governs each one, high-risk
drafts wait for a human, and every executed decision is sealed to an **offline-verifiable** RFC-6962
ledger.

> **The pitch:** *"Don't just observe your AI. Govern it — and prove it."* This demo ends with a
> cryptographic proof bundle a regulator can verify **without trusting QUAICU**.

Two ways to run it. The **script** is self-contained and fully verified end-to-end; the **console**
path adds a clickable browser walkthrough.

---

## 1. Script (no Docker, ~10 seconds)

```bash
python examples/underwriting-demo/demo.py
```

Runs the whole story in one process with **zero external services** (in-memory CEL engine + HITL
queue + a software Ed25519-signing RFC-6962 ledger):

1. **Low-risk draft** (₹2,50,000) → policy **ALLOWS** → executed → sealed.
2. **High-risk draft** (₹75,00,000) → policy **REQUIRES APPROVAL** → routed to the HITL queue → a
   human (`role:risk_head`) approves → executed → sealed **with the approver's identity**.
3. **Over-limit draft** (₹6,00,00,000) → policy **DENIES** (fail-closed) → the AI's decision does
   **not** execute.
4. **Proof bundle** → exported and **verified offline** via
   `core.regmap.export.verify_ledger_proof_bundle` — the exact check a regulator runs, independent of
   QUAICU.

Everything is assembly of already-built kernel surfaces: K·01 CEL policy engine, K·03 in-process HITL
gate, K·02 RFC-6962 TrustLedger + Ed25519 signer, and the WS-F proof export/verify. No new core logic.

---

## 2. Live console (browser walkthrough)

For a screen-share where a prospect clicks through the **Approvals** queue and the **Audit** page
(including the CSV + proof-bundle downloads shipped in W6-6):

```bash
# A) start the kernel pointed at the demo config (CEL engine + in-process approvals + signing ledger)
cd delivery/docker
KERNEL_CONFIG=/etc/quaicu/kernel.toml docker-compose up --build
#    …mounting examples/underwriting-demo/kernel.demo.toml as /etc/quaicu/kernel.toml
#    (point the `kernel` service's volume at this file, or copy it over kernel.dev.toml).

# B) seed a populated audit trail + approvals queue
python examples/underwriting-demo/seed.py --base http://localhost:7000

# C) run the console (see console/README) and open:
#    • Audit      → the sealed low-risk drafts + downloadable, offline-verifiable proof bundle
#    • Approvals  → the pending high-risk draft
```

**Honest note on the console path.** The console is the **UI surface** over the same APIs. The
*fully-correct* approve → re-execute → seal semantics (and the offline-verify punchline) are what the
**script** demonstrates and what CI verifies
(`tests/unit/adapters/test_memory_signed_ledger.py`). The browser path here is a documented
walkthrough that requires the dev stack running; it has not been pinned in CI. Use the script as the
source of truth for "it works," and the console for the visual story.

---

## What's in this folder

| File | Purpose |
|------|---------|
| `demo.py` | The self-contained reference-agent script (the verified end-to-end demo). |
| `kernel.demo.toml` | One config driving both paths: CEL engine + in-process HITL + `memory_signed_ledger` + the `credit.approve` policy pack (`[[policy.seed]]`). |
| `seed.py` | Populates a *running* kernel (HTTP) so the console shows data. Stdlib only. |
| `README.md` | This file. |

## The demo policy (why it ships its own)

The shipped RBI pack (`docs/policy-packs/rbi/`) governs `data.*` / `outsourcing.*`, **not** credit
underwriting — so this demo ships its own `credit.approve` policy in `kernel.demo.toml`:

| Amount (INR) | Decision | Regulatory hook |
|---|---|---|
| ≤ 10,00,000 | `allow` | RBI FREE-AI model-risk |
| 10,00,001 – 5,00,00,000 | `require_approval` (`role:risk_head`) | RBI FREE-AI human accountability |
| > 5,00,00,000 | `deny` | above delegated authority |

CEL is written against the activation schema in [`docs/CEL_POLICY_GUIDE.md`](../../docs/CEL_POLICY_GUIDE.md)
(`action_type` / `actor_roles` / `payload_<field>`).

## See also

- Use-cases & pilot framing: [`docs/gtm/PILOT_USE_CASES.md`](../../docs/gtm/PILOT_USE_CASES.md)
- Architecture one-pager: [`docs/ARCHITECTURE_ONEPAGER.md`](../../docs/ARCHITECTURE_ONEPAGER.md)
- Compliance matrix: [`docs/compliance/COMPLIANCE_MATRIX.md`](../../docs/compliance/COMPLIANCE_MATRIX.md)
- Security whitepaper: [`docs/compliance/SECURITY_WHITEPAPER.md`](../../docs/compliance/SECURITY_WHITEPAPER.md)
