# Live demo runbook — fake AI (credit + KYC/AML) on kernel.quaicu.org

Step-by-step to stand up the **living console demo** on the hosted kernel: a demo account, the regulatory
packs, and a fake AI firing governed credit-underwriting + KYC/AML calls so **Audit** and **Approvals**
fill with real data. Reflects the actual behaviour of the live SaaS plane (verified 2026-06-25).

> **Status:** verified working — 43 governed credit/KYC actions were sealed to tenant `quaicu-222af5`'s
> ledger during setup. The steps below reproduce and extend that.

---

## 0. Prerequisites

- A demo account on `https://kernel.quaicu.org` (sign up via **Plans → Starter**: email OTP → survey →
  password → ₹2 test-key fee). One-time, in the browser.
- Python 3.11+ and this repo checked out.

---

## 1. Get a session JWT (the credential that actually works)

On the live SaaS plane, **governed actions and policy operations require a session JWT** — a `qk_` API
key authenticates the edge (`/v1/me/*`, AI gateway) but resolves **no lifecycle actor**, so governed
actions fail-closed. Use the session token the console already holds:

1. Log into `https://kernel.quaicu.org`.
2. **F12 → Network**. Click any data page (e.g. **Audit**) so a `/v1/...` request appears.
3. Click that request → **Headers → Request Headers** → copy the value after `Authorization: Bearer `
   (a long `eyJ…` string).

The JWT carries your tenant + `owner`/`policy_admin` roles, and **expires in ~24h** (log out to kill it).

```powershell
# PowerShell
$env:QUAICU_API_KEY = "eyJ...your-session-jwt..."
```
```bash
# bash
export QUAICU_API_KEY="eyJ...your-session-jwt..."
```

---

## 2. Confirm connectivity

```bash
python examples/policy-pack-demo/fake_ai_agent.py --base https://kernel.quaicu.org --applicants 1
```
Expect 7 lines of `✓ … → COMPLETED`. If you see `error code: 1010`, a CDN is blocking the client —
this repo's scripts already send a normal `User-Agent`; make sure you're on the latest. If you see
`TENANT_UNRESOLVED`/`Invalid JWT`, your bearer isn't a valid session JWT — re-grab it (step 1).

---

## 3. Load + activate the packs (console — it has policy-admin)

The fake AI's calls map onto the shipped packs. Until rules are **active**, everything matches only the
default `starter-allow-baseline` (`allow *`) and seals as `COMPLETED` — good for populating Audit, but no
denials/approvals yet.

1. Console → **Policies → "Start from a policy pack"** → import **RBI**, **DPDP**, **EU AI Act**
   (imported as DRAFTs — never silently enforced).
2. **Activate** rules via each policy's backtest → activate flow. **Your STARTER tenant caps at 5 active
   policies** (`max_policies: 5`), and `starter-allow-baseline` + `starter-high-value-guardrail` already
   use 2 — so you have **~3 slots**. Activate these three for the best demo variety:

   | Policy id | Pack | Effect on the fake AI |
   |---|---|---|
   | `rbi-payment-data-localization` | RBI | "store financials" with payment data offshore → **DENY** |
   | `rbi-cross-border-transfer` | RBI | "AML sanctions screening" cross-border → **review** (`role:compliance`) |
   | `eu-ai-act-high-risk-oversight` | EU AI Act | "AI credit decision" with no human oversight → **review** (`role:compliance_officer`) |

   *(For all 25 pack policies at once you'd need a higher tier — STARTER's 5-policy cap is the limit.)*

---

## 4. Run the fake AI

```bash
# one pass — 7 governed calls per applicant (KYC/AML + credit)
python examples/policy-pack-demo/fake_ai_agent.py --base https://kernel.quaicu.org --applicants 6

# keep the console alive during a live demo (Ctrl-C to stop)
python examples/policy-pack-demo/fake_ai_agent.py --loop --interval 20

# preview the call plan without sending anything
python examples/policy-pack-demo/fake_ai_agent.py --dry-run
```

Two simulated agents (KYC/AML onboarding + credit underwriting) fire a believable stream. With the
policies from step 3 active you'll now see a mix: most `COMPLETED` (sealed), some `DENIED`, and some
routed to approval. **"Re-run the agent"** just means run this command again — each run creates fresh
actions (new ids), so re-running after activation produces new traffic shaped by the active policies.
Keep passes under the rate limit (`rate_limit_per_min: 60`).

---

## 5. Show it in the console

- **Audit** → the sealed governed actions (credit + KYC/AML), each with a ledger seq → **Download proof
  bundle (JSON)** → independently verifiable offline.
- **Approvals** → cross-border AML screenings + no-oversight credit decisions awaiting a human.
- **Policies** → the imported packs + the rules you activated.

---

## 6. Housekeeping & known limits

- 🔑 **Rotate any API key / session token** shared outside the browser (console → API Keys → revoke;
  log out to invalidate the session JWT).
- **5-policy cap** (STARTER): full three-pack (25-policy) coverage needs a higher tier or a quota raise.
- **API-key gap:** the `qk_` key can't drive governed actions on the SaaS plane (needs a session JWT).
  The durable fix — bridging the API-key principal → lifecycle actor so the documented integration
  credential works — is a small kernel change + a prod redeploy.
- **Approval semantics:** on the synchronous propose path, a high-risk action is recorded for approval
  but approving it in the UI doesn't re-execute it. The clean approve→execute→seal flow is shown by the
  local scripts (`demo.py`, `../underwriting-demo/demo.py`).

## See also
- Local, no-server version (all 3 packs, offline-verified): [`demo.py`](demo.py) / [`README.md`](README.md)
- HITL-gated single-policy story: [`../underwriting-demo/`](../underwriting-demo/README.md)
