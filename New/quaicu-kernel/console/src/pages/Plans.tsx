// Public plans / pricing page (/plans) — pick a tier before signing up.
//   Starter   → self-serve signup (₹10,000/yr).
//   Business  → ₹50,000 consultation deposit → Razorpay → notify the integrations team.
//   Enterprise→ same consultation flow (custom plan).

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { ErrorBox } from "../components";
import { loadRazorpayScript } from "../razorpay";

const PLANS = [
  {
    tier: "STARTER",
    name: "Starter",
    price: "₹10,000 / year",
    blurb: "Self-serve. Real CEL governance, 10,000 governed actions/day, audit trail.",
    cta: "Get started",
    kind: "signup" as const,
  },
  {
    tier: "BUSINESS",
    name: "Business",
    price: "from ₹20,00,000",
    blurb: "Durable Postgres + KMS-signed ledger, higher quotas, priority support.",
    cta: "Pay ₹50,000 to connect",
    kind: "consult" as const,
  },
  {
    tier: "ENTERPRISE",
    name: "Enterprise",
    price: "from ₹50,00,000 · custom",
    blurb: "Dedicated deployment, custom governance, SLAs, a dedicated integrations team.",
    cta: "Pay ₹50,000 to connect",
    kind: "consult" as const,
  },
];

export default function Plans() {
  const navigate = useNavigate();
  const [consultTier, setConsultTier] = useState<string | null>(null);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const asErr = (err: unknown) => (err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));

  function pick(kind: "signup" | "consult", tier: string) {
    if (kind === "signup") return navigate("/signup");
    setError(null);
    setConsultTier(tier);
  }

  async function submitConsult(e: React.FormEvent) {
    e.preventDefault();
    if (!consultTier) return;
    setBusy(true);
    setError(null);
    const lead = {
      tier: consultTier,
      full_name: fullName.trim(),
      email: email.trim(),
      company_name: company.trim(),
      phone: phone.trim(),
    };
    try {
      const order = await api.startConsultation(lead);
      await loadRazorpayScript();
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const Razorpay = (window as unknown as { Razorpay: any }).Razorpay;
      const rzp = new Razorpay({
        key: order.razorpay_key_id,
        order_id: order.order_id,
        amount: order.amount_paise,
        currency: order.currency,
        name: "QUAICU",
        description: `${consultTier} consultation`,
        prefill: { name: fullName.trim(), email: email.trim(), contact: phone.trim() },
        theme: { color: "#111111" },
        handler: async (r: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) => {
          try {
            await api.completeConsultation({
              ...lead,
              razorpay_order_id: r.razorpay_order_id,
              razorpay_payment_id: r.razorpay_payment_id,
              razorpay_signature: r.razorpay_signature,
            });
            setDone(consultTier);
            setConsultTier(null);
          } catch (err) {
            setError(asErr(err));
          }
        },
        modal: { ondismiss: () => setError("Payment cancelled.") },
      });
      rzp.open();
    } catch (err) {
      setError(asErr(err));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="gate">
        <h2>Thank you — we'll be in touch</h2>
        <p className="muted">
          Your <strong>{done}</strong> consultation is booked. Our integrations team will reach out
          shortly to scope your plan and onboard you.
        </p>
        <button className="primary" onClick={() => navigate("/")}>Done</button>
      </div>
    );
  }

  if (consultTier) {
    const valid = fullName.trim() && email.trim() && company.trim() && phone.trim();
    return (
      <div className="gate">
        <h2>{consultTier} — book a consultation</h2>
        <p className="muted">
          A ₹50,000 consultation deposit connects you with our integrations team to scope your plan.
        </p>
        <form className="card signup-card signup-form" onSubmit={submitConsult}>
          <div className="card-body">
            {error && <ErrorBox message={error} />}
            <label>Full name<input required value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Ada Lovelace" /></label>
            <label>Work email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" /></label>
            <label>Company<input required value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Acme Bank" /></label>
            <label>Phone<input type="tel" required value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91 …" /></label>
            <button className="primary" type="submit" disabled={busy || !valid}>
              {busy ? "Starting…" : "Pay ₹50,000 &amp; connect"}
            </button>
            <button className="linklike" type="button" onClick={() => { setConsultTier(null); setError(null); }}>← Back to plans</button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <div className="gate plans-gate">
      <h2>Choose your plan</h2>
      <div className="plans">
        {PLANS.map((p) => (
          <div key={p.tier} className="card plan-card">
            <div className="card-title">{p.name}</div>
            <div className="card-body">
              <div className="plan-price">{p.price}</div>
              <p className="muted small">{p.blurb}</p>
              <button className="primary" onClick={() => pick(p.kind, p.tier)}>{p.cta}</button>
            </div>
          </div>
        ))}
      </div>
      <p className="muted small">Already have an account? <Link to="/">Sign in</Link>.</p>
    </div>
  );
}
