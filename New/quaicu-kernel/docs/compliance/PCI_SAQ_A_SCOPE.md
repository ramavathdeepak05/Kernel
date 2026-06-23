# PCI-DSS scope memo — QUAICU qualifies for SAQ-A

> **DRAFT — internal scoping rationale, not a PCI attestation.** This memo argues the SAQ-A
> eligibility position and lists the evidence. **Confirm with your acquiring bank / a QSA before
> relying on it** — the acquirer ultimately decides which SAQ applies.

_Owner: [compliance] · Tracks ACTION_TRACKER **W2-7** · Last updated: 2026-06-23_

## Position
QUAICU should qualify for **SAQ-A** — the shortest self-assessment questionnaire — because it
**fully outsources all cardholder-data functions** to a PCI-DSS-validated third-party payment
processor (Razorpay; Stripe where used). QUAICU never stores, processes, or transmits the primary
account number (PAN) or any cardholder data.

## Why SAQ-A (eligibility criteria)
SAQ-A applies to card-not-present merchants that have outsourced **all** cardholder-data handling and
retain **no** electronic cardholder-data storage. Mapped to QUAICU:

| SAQ-A criterion | QUAICU |
|---|---|
| Merchant accepts only card-not-present transactions | ✅ Web checkout only |
| All payment-page functions outsourced to a PCI-DSS-validated provider | ✅ Razorpay-hosted Checkout (and Stripe where used) — both validated providers |
| QUAICU retains only paper reports / no electronic cardholder data | ✅ No PAN/CVV stored anywhere in the system |
| QUAICU does not store, process, or transmit cardholder data on its systems | ✅ See evidence below |
| Any payment page is served **directly** from the PCI-validated third party | ✅ The widget loads from `checkout.razorpay.com`; card fields render inside Razorpay's iframe, not in QUAICU's DOM |

## Evidence in the codebase
- **Hosted widget, not our form.** The console lazily injects Razorpay's hosted Checkout script and
  opens **their** iframe; QUAICU renders no card-number/CVV/expiry inputs. See
  `console/src/razorpay.ts` (script `https://checkout.razorpay.com/v1/checkout.js`) and the
  open-checkout flow in `console/src/pages/Signup.tsx` / `console/src/pages/Plans.tsx`.
- **We receive a reference, not card data.** The signup/checkout completion carries only
  `razorpay_order_id` / `razorpay_payment_id` / `razorpay_signature` (see `console/src/api/types.ts`)
  — opaque references, never the PAN. This is also stated to data subjects in the privacy copy
  (`console/src/legal/content.ts`: "Payment is handled by Razorpay — we receive a payment reference,
  not your card details").
- **Webhooks carry no card data and are signature-verified.** The billing webhook authenticates the
  provider signature and processes payment *references/events*, not cardholder data.
- **CSP confines the payment surface.** The console's Content-Security-Policy (`console/worker.js`)
  permits the Razorpay origins **only** for the checkout widget — no other third-party can inject a
  payment field.

## Scope boundary (what would change the SAQ)
QUAICU must **re-scope to SAQ-A-EP (or higher)** if any of these ever become true:
- A card-number / CVV / expiry field is rendered **in QUAICU's own page DOM** (even if JS-tokenized).
- QUAICU's servers receive, log, or transmit the PAN at any point.
- The payment page is served from QUAICU's origin rather than directly from the validated provider.

## Standing obligations even under SAQ-A
- Maintain the list of PCI-DSS-validated providers and their current **Attestation of Compliance (AoC)**
  (Razorpay / Stripe) — request annually.
- Keep the integration such that the payment page comes only from the validated provider.
- Complete the SAQ-A annually and after any change to the payment flow; have an officer attest it.
- Confirm acquirer-specific reporting obligations (some acquirers require the SAQ + AoC on file).

## Next actions
1. Pull current **AoC** from Razorpay (and Stripe if enabled).
2. Send this scoping position to the **acquirer / a QSA** to confirm SAQ-A.
3. Complete and sign **SAQ-A**; file with the acquirer.
4. Add "payment-flow change ⇒ re-confirm PCI scope" to the change-management checklist.
