// Forgot/reset password (/reset). Step 1: enter email → emailed a code. Step 2: code + new
// password → auto-login. Public.

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { ErrorBox } from "../components";
import { setSession } from "../state/auth";

export default function ResetPassword() {
  const navigate = useNavigate();
  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [otp, setOtp] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const asErr = (e: unknown) => (e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));

  async function requestCode(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const resp = await api.forgotPassword({ email: email.trim() });
      setToken(resp.reset_token);
      setStep("code");
    } catch (err) {
      setError(asErr(err));
    } finally {
      setBusy(false);
    }
  }

  async function submitReset(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const resp = await api.resetPassword({ reset_token: token, otp: otp.trim(), new_password: password });
      setSession({ token: resp.session_token, tenant: resp.tenant_id });
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === "SIGNUP_VERIFICATION_FAILED") {
        setError("Incorrect or expired code.");
      } else {
        setError(asErr(err));
      }
    } finally {
      setBusy(false);
    }
  }

  if (step === "code") {
    return (
      <div className="gate">
        <h2>Set a new password</h2>
        <p className="muted">
          If an account exists for <strong>{email.trim()}</strong>, we emailed a 6-digit code. Enter it
          with your new password.
        </p>
        <form className="card signup-card signup-form" onSubmit={submitReset}>
          <div className="card-body">
            {error && <ErrorBox message={error} />}
            <label>
              Reset code
              <input inputMode="numeric" pattern="[0-9]*" maxLength={6} required value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))} placeholder="123456"
                style={{ letterSpacing: "0.3em", textAlign: "center" }} />
            </label>
            <label>
              New password
              <input type="password" required minLength={8} value={password}
                onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters"
                autoComplete="new-password" />
            </label>
            <label>
              Confirm password
              <input type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password" />
              {confirm && password !== confirm && <span className="muted small">Passwords don't match.</span>}
            </label>
            <button className="primary" type="submit"
              disabled={busy || otp.trim().length !== 6 || password.length < 8 || password !== confirm}>
              {busy ? "Updating…" : "Update password & sign in"}
            </button>
          </div>
        </form>
        <p className="muted small"><Link to="/">Back to sign in</Link></p>
      </div>
    );
  }

  return (
    <div className="gate">
      <h2>Reset your password</h2>
      <p className="muted">Enter your account email and we'll send a reset code.</p>
      <form className="card signup-card signup-form" onSubmit={requestCode}>
        <div className="card-body">
          {error && <ErrorBox message={error} />}
          <label>
            Email
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com" autoComplete="email" />
          </label>
          <button className="primary" type="submit" disabled={busy || !email.trim()}>
            {busy ? "Sending…" : "Send reset code"}
          </button>
        </div>
      </form>
      <p className="muted small"><Link to="/">Back to sign in</Link></p>
    </div>
  );
}
