# QUAICU regulated-FS demo — the shipped policy packs, governing a tenant

Shows **how things work in a real environment**: the **in-the-box** policy packs an India FS customer
adopts — **RBI FREE-AI · DPDP · EU AI Act** — loaded into a demo tenant, governing a realistic action
stream (allow / deny / require-approval), sealed to an offline-verifiable ledger. No bespoke policy:
this is the same pack content the live console's *"Start from a policy pack"* imports.

Two ways: a **local script** (fully verified, no servers) and a **live walkthrough** on
`kernel.quaicu.org` (the way a customer integrates).

---

## A. Local — the shipped packs on an in-process tenant (verified, ~10s)

```bash
cd New/quaicu-kernel
python examples/policy-pack-demo/demo.py
```

Loads the real `docs/policy-packs/{rbi,dpdp,eu-ai-act}/` content via `core.policy.packs` (the loader
behind the live import API) into tenant `demo-nbfc`, then runs ~12 governed actions:

| Regime | Example action | Outcome |
|---|---|---|
| RBI | store KYC in India, encrypted | ✅ sealed |
| RBI | store **payment** data outside India | ⛔ denied (localization) |
| RBI | cross-border data transfer | ✅ require-approval → approved → sealed |
| RBI | material outsourcer, **no** audit rights | ⛔ denied |
| DPDP | process personal data, consent ✓ | ✅ sealed |
| DPDP | process **without consent** | ⛔ denied |
| DPDP | cross-border personal-data transfer | ✅ require-approval → approved → sealed |
| EU AI Act | invoke **prohibited-risk** AI | ⛔ denied |
| EU AI Act | high-risk AI, **no** human oversight | ✅ require-approval → approved → sealed |

…then exports the proof bundle and **verifies it offline**. This is the reliable demo — run it live on
a call or record it.

---

## B. Living console demo — `kernel.quaicu.org` with a fake credit + KYC/AML AI

The goal: a **demo account on the live console** with **all packs loaded** and a **fake AI system**
firing credit-underwriting + KYC/AML calls, so the **Audit** and **Approvals** pages fill with realistic
governed traffic. This touches a **production** system, so the account/key/pack steps are yours to do in
the browser (an agent can't do OTP + payment + console clicks for you); the **fake AI traffic** is a
script you run with your key.

### B1. Create the demo account (browser, one-time ~5 min)
1. **`https://kernel.quaicu.org`** → **Plans** → **Starter** (self-serve).
2. Sign up: email **OTP** → onboarding survey → password → the one-time **₹2 signup fee** via Razorpay
   (currently **test** keys, so effectively free). You're auto-logged-in. *(This creates a durable
   account/tenant — use a throwaway and have ops clean it up after.)*
3. Console → **API Keys** → **Create** → copy the `qk_…` key. (Ensure it has action-write scope.)

### B2. Load + activate all the packs (console — it has policy-admin)
- Console → **Policies → "Start from a policy pack"** → import **RBI**, **DPDP**, **EU AI Act** (they
  land as **DRAFTs** — never silently enforced).
- **Activate** the policies you want enforced (open → backtest → activate, the F-10 gate). Activate the
  data.store / data.transfer / personal_data.process / ai_system.invoke / access.grant rules so the fake
  AI's calls are actually governed. *(Optional: `realenv.py --import-packs` imports via API if your key
  has policy-admin — but activation is still a console step.)*

### B3. Run the fake AI system (the living traffic)
```bash
# PowerShell:
$env:QUAICU_API_KEY = "qk_xxx"
python examples/policy-pack-demo/fake_ai_agent.py --base https://kernel.quaicu.org --applicants 8
# keep the console alive during a call:
python examples/policy-pack-demo/fake_ai_agent.py --loop --interval 20
# preview the call plan without sending:
python examples/policy-pack-demo/fake_ai_agent.py --dry-run
```
Two simulated agents (KYC/AML onboarding + credit underwriting) fire a believable stream of governed
`POST /v1/actions/propose` calls mapped onto the shipped packs:

| Fake-AI step | Action type | Pack | Typical outcome |
|---|---|---|---|
| KYC identity screen | `personal_data.process` | DPDP | allow (or **deny** if no consent) |
| store KYC docs | `data.store` | RBI | allow (India + encrypted) |
| AML sanctions screening | `data.transfer` | RBI | **review** if cross-border |
| credit-bureau pull | `personal_data.process` | DPDP | allow |
| store financials | `data.store` | RBI | **deny** if payment data offshore |
| AI credit decision | `ai_system.invoke` | EU AI Act | **review** if high-risk + no human oversight |
| analyst case access | `access.grant` | RBI | allow (logged) |

So **Audit** fills with sealed actions and **Approvals** fills with cross-border AML reviews + no-oversight
credit decisions awaiting a human. (The exact action→outcome mapping is verified locally by `demo.py`.)

### B4. Show it in the console
- **Audit** → the sealed governed actions → **Download proof bundle (JSON)** (offline-verifiable).
- **Approvals** → the pending high-risk credit + cross-border AML reviews.
- **Policies** → the three imported packs governing it all.

### Honest notes
- **The local script (A) is the verified source of truth.** The live demo has real edges: signup is a
  browser flow; pack import needs a policy-admin key (do it in the console); **enforcement needs
  activation** (until then, actions fall through to the fail-closed default — that's expected); and the
  synchronous-propose approval path means a high-risk action is recorded for approval but won't
  re-execute on approve (that full semantic is what the local scripts show cleanly).
- `fake_ai_agent.py` / `realenv.py` **write to your tenant**. Run them on a demo tenant you own.

---

## Files
| File | Purpose |
|------|---------|
| `demo.py` | Local, verified — shipped packs govern a tenant end-to-end + offline verify. |
| `fake_ai_agent.py` | The fake credit + KYC/AML AI → a stream of governed calls to a live console (`--dry-run`/`--loop`). |
| `realenv.py` | Setup helper — API-key auth check + optional pack import + a few sample `/v1/authorize` calls. |
| `README.md` | This file. |

## See also
- The HITL-gated single-policy story: [`../underwriting-demo/`](../underwriting-demo/README.md)
- Regime → control mapping: [`../../docs/compliance/COMPLIANCE_MATRIX.md`](../../docs/compliance/COMPLIANCE_MATRIX.md)
- Pack contents & payload contracts: [`../../docs/policy-packs/`](../../docs/policy-packs/)
