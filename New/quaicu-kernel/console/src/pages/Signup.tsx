// Verified self-serve signup (/signup). Four steps:
//   1. account  — name, company email, company, password (the console login credential).
//   2. about    — onboarding survey: role, phone, industry, size, use case, regulations (all required).
//   3. otp       — verify the email with a 6-digit code (emailed by /v1/signup/start).
//   4. done      — reveal the one-time API key, seed the session, enter the console.
// Rendered outside the auth gate (like /callback).

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { ErrorBox } from "../components";
import { setSession } from "../state/auth";

const FREE_DOMAINS = new Set([
  "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "outlook.com", "hotmail.com",
  "live.com", "aol.com", "icloud.com", "me.com", "proton.me", "protonmail.com", "gmx.com",
  "mail.com", "zoho.com", "yandex.com", "qq.com",
]);

function looksLikeCompanyEmail(email: string): boolean {
  const at = email.indexOf("@");
  if (at <= 0) return false;
  const domain = email.slice(at + 1).toLowerCase();
  return domain.includes(".") && !FREE_DOMAINS.has(domain);
}

const INDUSTRIES = ["Banking", "Fintech", "Insurance", "Healthcare", "Government", "Technology", "Other"];
const SIZES = ["1-10", "11-50", "51-200", "201-1000", "1000+"];
const USE_CASES = ["AI governance", "Audit & compliance", "Policy enforcement", "Model risk management", "Other"];
const REGULATIONS = ["RBI", "DPDP", "GDPR", "EU AI Act", "NAAC"];

type Step = "account" | "about" | "otp";

export default function Signup() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("account");

  // Step 1 — account
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  // Step 2 — about
  const [jobTitle, setJobTitle] = useState("");
  const [phone, setPhone] = useState("");
  const [industry, setIndustry] = useState("");
  const [companySize, setCompanySize] = useState("");
  const [useCase, setUseCase] = useState("");
  const [regulations, setRegulations] = useState<string[]>([]);

  // Step 3 — otp
  const [token, setToken] = useState("");
  const [otp, setOtp] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const accountValid =
    fullName.trim() && companyName.trim() && looksLikeCompanyEmail(email.trim()) &&
    password.length >= 8 && password === confirm;
  const aboutValid =
    jobTitle.trim() && phone.trim() && industry && companySize && useCase && regulations.length > 0;

  function mapError(err: unknown): string {
    if (err instanceof ApiError) {
      if (err.code === "SIGNUP_DISABLED") return "Self-serve signup isn't enabled on this deployment.";
      if (err.code === "EMAIL_DOMAIN_NOT_ALLOWED") return "Please use your company email — free/personal providers aren't accepted.";
      if (err.code === "PASSWORD_TOO_WEAK") return err.message;
      if (err.status === 409) return "An account already exists for that email. Sign in instead.";
      if (err.code === "SIGNUP_VERIFICATION_FAILED") return err.message;
      return `${err.code}: ${err.message}`;
    }
    return String(err);
  }

  function toggleReg(reg: string) {
    setRegulations((cur) => (cur.includes(reg) ? cur.filter((r) => r !== reg) : [...cur, reg]));
  }

  async function submitAbout(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const resp = await api.startSignup({
        full_name: fullName.trim(),
        email: email.trim(),
        company_name: companyName.trim(),
        password,
        job_title: jobTitle.trim(),
        phone: phone.trim(),
        use_case: useCase,
        industry,
        company_size: companySize,
        regulations,
      });
      setToken(resp.verification_token);
      setStep("otp");
    } catch (err) {
      setError(mapError(err));
    } finally {
      setBusy(false);
    }
  }

  async function verifySubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const resp = await api.verifySignup({ verification_token: token, otp: otp.trim() });
      // Auto-login with the returned session, then into the console — no API key shown here.
      setSession({ token: resp.session_token, tenant: resp.tenant_id });
      navigate("/", { replace: true });
    } catch (err) {
      setError(mapError(err));
    } finally {
      setBusy(false);
    }
  }

  async function resendCode() {
    setBusy(true);
    setError(null);
    try {
      const resp = await api.startSignup({
        full_name: fullName.trim(), email: email.trim(), company_name: companyName.trim(), password,
        job_title: jobTitle.trim(), phone: phone.trim(), use_case: useCase, industry,
        company_size: companySize, regulations,
      });
      setToken(resp.verification_token);
      setOtp("");
    } catch (err) {
      setError(mapError(err));
    } finally {
      setBusy(false);
    }
  }

  // ── Step 3: OTP ─────────────────────────────────────────────────────────────
  if (step === "otp") {
    return (
      <div className="gate">
        <h2>Verify your email</h2>
        <p className="muted">We sent a 6-digit code to <strong>{email.trim()}</strong>.</p>
        <form className="card signup-card signup-form" onSubmit={verifySubmit}>
          <div className="card-body">
            {error && <ErrorBox message={error} />}
            <label>
              Verification code
              <input
                inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]*" maxLength={6} required
                value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))} placeholder="123456"
                style={{ letterSpacing: "0.4em", fontSize: "1.25rem", textAlign: "center" }}
              />
            </label>
            <button className="primary" type="submit" disabled={busy || otp.trim().length !== 6}>
              {busy ? "Verifying…" : "Verify & create workspace"}
            </button>
          </div>
        </form>
        <p className="muted small">
          Didn't get it?{" "}
          <button className="linklike" type="button" onClick={resendCode} disabled={busy}>Resend code</button>{" "}
          ·{" "}
          <button className="linklike" type="button" onClick={() => { setStep("about"); setError(null); setOtp(""); }}>Back</button>
        </p>
      </div>
    );
  }

  // ── Step 2: about / survey ──────────────────────────────────────────────────
  if (step === "about") {
    return (
      <div className="gate">
        <h2>Tell us about your use</h2>
        <p className="muted">A few details so we can tailor your workspace. All fields required.</p>
        <form className="card signup-card signup-form" onSubmit={submitAbout}>
          <div className="card-body">
            {error && <ErrorBox message={error} />}
            <label>
              Job title
              <input required value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} placeholder="Compliance Lead" autoComplete="organization-title" />
            </label>
            <label>
              Phone
              <input type="tel" required value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+1 555 123 4567" autoComplete="tel" />
            </label>
            <label>
              Industry
              <select required value={industry} onChange={(e) => setIndustry(e.target.value)}>
                <option value="" disabled>Select…</option>
                {INDUSTRIES.map((i) => <option key={i} value={i}>{i}</option>)}
              </select>
            </label>
            <label>
              Company size
              <select required value={companySize} onChange={(e) => setCompanySize(e.target.value)}>
                <option value="" disabled>Select…</option>
                {SIZES.map((s) => <option key={s} value={s}>{s} employees</option>)}
              </select>
            </label>
            <label>
              How do you plan to use QUAICU?
              <select required value={useCase} onChange={(e) => setUseCase(e.target.value)}>
                <option value="" disabled>Select…</option>
                {USE_CASES.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
            </label>
            <fieldset className="reg-group">
              <legend>Regulations of interest <span className="muted small">(pick at least one)</span></legend>
              {REGULATIONS.map((reg) => (
                <label key={reg} className="reg-check">
                  <input type="checkbox" checked={regulations.includes(reg)} onChange={() => toggleReg(reg)} />
                  {reg}
                </label>
              ))}
            </fieldset>
            <button className="primary" type="submit" disabled={busy || !aboutValid}>
              {busy ? "Sending code…" : "Continue →"}
            </button>
            <button className="linklike" type="button" onClick={() => { setStep("account"); setError(null); }}>← Back</button>
          </div>
        </form>
      </div>
    );
  }

  // ── Step 1: account ─────────────────────────────────────────────────────────
  return (
    <div className="gate">
      <h2>Start free</h2>
      <p className="muted">Create a STARTER workspace. No credit card. Use your <strong>company email</strong>.</p>
      <form className="card signup-card signup-form" onSubmit={(e) => { e.preventDefault(); if (accountValid) setStep("about"); }}>
        <div className="card-body">
          {error && <ErrorBox message={error} />}
          <label>
            Full name
            <input required value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Ada Lovelace" autoComplete="name" />
          </label>
          <label>
            Work email
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" />
            {email.trim() && !looksLikeCompanyEmail(email.trim()) && (
              <span className="muted small">Use your company email — personal providers aren't accepted.</span>
            )}
          </label>
          <label>
            Company name
            <input required value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="Acme Bank" autoComplete="organization" />
          </label>
          <label>
            Password
            <input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" autoComplete="new-password" />
          </label>
          <label>
            Confirm password
            <input type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="Re-enter password" autoComplete="new-password" />
            {confirm && password !== confirm && <span className="muted small">Passwords don't match.</span>}
          </label>
          <button className="primary" type="submit" disabled={!accountValid}>Continue →</button>
        </div>
      </form>
      <p className="muted small">Already have an account? <Link to="/">Sign in</Link>.</p>
    </div>
  );
}
