// Verified self-serve signup (/signup). Three steps:
//   1. Collect professional details (company email only — free/personal providers rejected).
//   2. Verify the email with a 6-digit OTP (POST /v1/signup/start emailed it).
//   3. Reveal the one-time API key, then seed it as the session and enter the console.
// Rendered outside the auth gate (like /callback).

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { ErrorBox } from "../components";
import { setSession } from "../state/auth";
import type { SignupResponse } from "../api/types";

// Quick client-side hint mirroring the server's company-email rule (the server is authoritative).
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

type Step = "details" | "otp" | "done";

export default function Signup() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("details");

  // Step 1 — details
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [phone, setPhone] = useState("");

  // Step 2 — OTP
  const [token, setToken] = useState("");
  const [otp, setOtp] = useState("");

  // Step 3 — result
  const [result, setResult] = useState<SignupResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const detailsValid =
    fullName.trim() && companyName.trim() && looksLikeCompanyEmail(email.trim());

  function mapError(err: unknown): string {
    if (err instanceof ApiError) {
      if (err.code === "SIGNUP_DISABLED")
        return "Self-serve signup isn't enabled on this deployment. Ask your operator for an API key.";
      if (err.code === "EMAIL_DOMAIN_NOT_ALLOWED")
        return "Please use your company email — free/personal providers (gmail, yahoo, …) aren't accepted.";
      if (err.status === 409)
        return "An account already exists for that email. Sign in with your existing API key instead.";
      if (err.code === "SIGNUP_VERIFICATION_FAILED")
        return `${err.message}`;
      return `${err.code}: ${err.message}`;
    }
    return String(err);
  }

  async function startSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const resp = await api.startSignup({
        full_name: fullName.trim(),
        email: email.trim(),
        company_name: companyName.trim(),
        job_title: jobTitle.trim(),
        phone: phone.trim(),
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
      setResult(resp);
      setStep("done");
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
        full_name: fullName.trim(),
        email: email.trim(),
        company_name: companyName.trim(),
        job_title: jobTitle.trim(),
        phone: phone.trim(),
      });
      setToken(resp.verification_token);
      setOtp("");
    } catch (err) {
      setError(mapError(err));
    } finally {
      setBusy(false);
    }
  }

  async function copyKey() {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.api_key);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  function enterConsole() {
    if (!result) return;
    setSession({ token: result.api_key, tenant: result.tenant_id });
    navigate("/", { replace: true });
  }

  // ── Step 3: key provisioned — show it ONCE ──────────────────────────────────
  if (step === "done" && result) {
    return (
      <div className="gate">
        <h2>Your free workspace is ready</h2>
        <p className="muted">
          You're on the <span className="tier-badge tier-starter">STARTER</span> tier — real CEL
          governance, 10,000 governed actions/day, no card required.
        </p>
        <div className="card signup-card">
          <div className="card-title">Your API key</div>
          <div className="card-body">
            <p className="muted small">
              Copy this now — it is shown <strong>once</strong> and never again. It authenticates your
              calls to the kernel API as tenant <code>{result.tenant_id}</code>.
            </p>
            <div className="key-reveal">
              <code className="key-value">{result.api_key}</code>
              <button onClick={copyKey}>{copied ? "Copied ✓" : "Copy"}</button>
            </div>
          </div>
        </div>
        <button className="primary" onClick={enterConsole}>Enter the console →</button>
      </div>
    );
  }

  // ── Step 2: OTP verification ────────────────────────────────────────────────
  if (step === "otp") {
    return (
      <div className="gate">
        <h2>Verify your email</h2>
        <p className="muted">
          We sent a 6-digit code to <strong>{email.trim()}</strong>. Enter it below to finish creating
          your workspace.
        </p>
        <form className="card signup-card signup-form" onSubmit={verifySubmit}>
          <div className="card-body">
            {error && <ErrorBox message={error} />}
            <label>
              Verification code
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]*"
                maxLength={6}
                required
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
                placeholder="123456"
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
          <button className="linklike" type="button" onClick={resendCode} disabled={busy}>
            Resend code
          </button>{" "}
          ·{" "}
          <button
            className="linklike"
            type="button"
            onClick={() => { setStep("details"); setError(null); setOtp(""); }}
          >
            Change details
          </button>
        </p>
      </div>
    );
  }

  // ── Step 1: customer details ────────────────────────────────────────────────
  return (
    <div className="gate">
      <h2>Start free</h2>
      <p className="muted">
        Create a STARTER workspace. No credit card — a tenant, an API key, and live governance you can
        upgrade later. We just need a few details and your <strong>company email</strong>.
      </p>
      <form className="card signup-card signup-form" onSubmit={startSubmit}>
        <div className="card-body">
          {error && <ErrorBox message={error} />}
          <label>
            Full name
            <input
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Ada Lovelace"
              autoComplete="name"
            />
          </label>
          <label>
            Work email
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              autoComplete="email"
            />
            {email.trim() && !looksLikeCompanyEmail(email.trim()) && (
              <span className="muted small">Use your company email — personal providers aren't accepted.</span>
            )}
          </label>
          <label>
            Company name
            <input
              required
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="Acme Bank"
              autoComplete="organization"
            />
          </label>
          <label>
            Job title <span className="muted small">(optional)</span>
            <input
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
              placeholder="Compliance Lead"
              autoComplete="organization-title"
            />
          </label>
          <label>
            Phone <span className="muted small">(optional)</span>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+1 555 123 4567"
              autoComplete="tel"
            />
          </label>
          <button className="primary" type="submit" disabled={busy || !detailsValid}>
            {busy ? "Sending code…" : "Continue →"}
          </button>
        </div>
      </form>
      <p className="muted small">
        Already have a key? <Link to="/">Sign in</Link>.
      </p>
    </div>
  );
}
