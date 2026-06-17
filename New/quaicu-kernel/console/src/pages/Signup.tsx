// Self-serve signup (/signup). Collects email + org name, calls POST /v1/signup, reveals the
// one-time API key, then seeds it as the session bearer so the user lands in the console already
// governing on the free STARTER tier. Rendered outside the auth gate (like /callback).

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { ErrorBox } from "../components";
import { setSession } from "../state/auth";
import type { SignupResponse } from "../api/types";

export default function Signup() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SignupResponse | null>(null);
  const [copied, setCopied] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const resp = await api.signup({ email: email.trim(), name: name.trim() });
      setResult(resp);
    } catch (err) {
      if (err instanceof ApiError && err.code === "SIGNUP_DISABLED") {
        setError("Self-serve signup isn't enabled on this deployment. Ask your operator for an API key.");
      } else if (err instanceof ApiError && err.status === 409) {
        setError("An account already exists for that email. Sign in with your existing API key instead.");
      } else {
        setError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
      }
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
    // The API key is the bearer the kernel verifies; the tenant routes the request (X-Tenant-Id).
    setSession({ token: result.api_key, tenant: result.tenant_id });
    navigate("/", { replace: true });
  }

  // ── Step 2: the key is provisioned — show it ONCE, then enter the console ──────────
  if (result) {
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

  // ── Step 1: the signup form ───────────────────────────────────────────────────────
  return (
    <div className="gate">
      <h2>Start free</h2>
      <p className="muted">
        Create a STARTER workspace in seconds. No credit card — you get a tenant, an API key, and live
        governance you can upgrade later.
      </p>
      <form className="card signup-card signup-form" onSubmit={submit}>
        <div className="card-body">
          {error && <ErrorBox message={error} />}
          <label>
            Work email
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
            />
          </label>
          <label>
            Organisation / workspace name
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Acme Bank"
            />
          </label>
          <button className="primary" type="submit" disabled={busy || !email.trim() || !name.trim()}>
            {busy ? "Creating…" : "Create free workspace"}
          </button>
        </div>
      </form>
      <p className="muted small">
        Already have a key? <Link to="/">Sign in</Link>.
      </p>
    </div>
  );
}
