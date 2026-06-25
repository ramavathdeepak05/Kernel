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

## B. Real environment — `kernel.quaicu.org` (you drive it)

This touches a **production** system, so the account/key steps are yours to do in the browser; the
scripted part runs with your key. (Today `kernel.quaicu.org` serves the console SPA and proxies
`/v1/*` to the kernel.)

### B1. Create a demo account (browser, one-time)
1. Go to **`https://kernel.quaicu.org`** → **Plans** → pick **Starter** (self-serve).
2. Sign up: email **OTP** → onboarding survey → password → the one-time **₹2 signup fee** via Razorpay
   (currently **test** keys). You're auto-logged-in. *(Signup creates a durable account/tenant — use a
   throwaway you don't mind keeping or asking ops to clean up.)*
3. Console → **API Keys** → **Create** → copy the `qk_…` key.

### B2. Load the regulatory packs (console — has policy-admin)
- Console → **Policies → "Start from a policy pack"** → import **RBI**, **DPDP**, **EU AI Act**. They
  land as **DRAFTs** (never silently enforced).
- For each policy you want enforced: open it → backtest → **activate** (the F-10 gate). Activate a few
  to make the next step show real enforcement.

### B3. Govern actions over HTTPS with your key
```bash
# PowerShell:
$env:QUAICU_API_KEY = "qk_xxx"
python examples/policy-pack-demo/realenv.py --base https://kernel.quaicu.org --import-packs
```
The helper: confirms the key (`/v1/me/entitlements`), optionally imports the packs
(`/v1/policy-packs/{id}/import` — needs a policy-admin key; otherwise do it in the console per B2), and
sends a representative governed action per pack to `/v1/authorize`. Each decision is **sealed** to your
tenant's audit trail.

> Outcomes reflect the policies **active** in your tenant. Until you activate pack policies (B2), actions
> fall through to the deployment's fail-closed default — that's expected.

### B4. See the proof
- Console → **Audit** → the sealed decisions from B3 → **Download proof bundle (JSON)** — independently
  verifiable offline (the same `verify_ledger_proof_bundle` the local script runs).
- Console → **Get started / `/start`** also has a live try-it against a seeded policy + copy-paste
  curl/Python.

### Honest notes
- **The local script (A) is the verified source of truth.** The live walkthrough has rough edges
  (signup is a browser flow; pack import needs a policy-admin key; enforcement needs activation; the
  synchronous-propose approval semantics differ from the script). Use A to *prove it works*, B to show
  *real integration*.
- `realenv.py` **writes to your tenant** (DRAFT policies + sealed authorize records). Run it on a demo
  tenant you own.

---

## Files
| File | Purpose |
|------|---------|
| `demo.py` | Local, verified — shipped packs govern a tenant end-to-end + offline verify. |
| `realenv.py` | HTTP helper to drive the packs against a live kernel with your API key. |
| `README.md` | This file. |

## See also
- The HITL-gated single-policy story: [`../underwriting-demo/`](../underwriting-demo/README.md)
- Regime → control mapping: [`../../docs/compliance/COMPLIANCE_MATRIX.md`](../../docs/compliance/COMPLIANCE_MATRIX.md)
- Pack contents & payload contracts: [`../../docs/policy-packs/`](../../docs/policy-packs/)
