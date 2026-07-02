// Set password from an emailed invite link (/set-password?token=...). An invited member chooses a
// password and is signed straight in. Public (outside the auth gate).

import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { ErrorBox } from "../components";
import { setSession } from "../state/auth";

export default function SetPassword() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const asErr = (e: unknown) => (e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const resp = await api.setPassword({ token, new_password: password });
      setSession({ token: resp.session_token, tenant: resp.tenant_id });
      navigate("/", { replace: true });
    } catch (err) {
      setError(asErr(err));
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <div className="gate">
        <h2>Set your password</h2>
        <ErrorBox message="This link is missing its token. Please open the link from your invite email." />
        <p className="muted small">
          <Link to="/">Back to sign in</Link>
        </p>
      </div>
    );
  }

  return (
    <div className="gate">
      <h2>Set your password</h2>
      <p className="muted">Choose a password to sign in to QUAICU.</p>
      <form className="card signup-card signup-form" onSubmit={submit}>
        <div className="card-body">
          {error && <ErrorBox message={error} />}
          <label>
            New password
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              autoComplete="new-password"
            />
          </label>
          <label>
            Confirm password
            <input
              type="password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
            />
            {confirm && password !== confirm && (
              <span className="muted small">Passwords don't match.</span>
            )}
          </label>
          <button
            className="primary"
            type="submit"
            disabled={busy || password.length < 8 || password !== confirm}
          >
            {busy ? "Setting…" : "Set password & sign in"}
          </button>
        </div>
      </form>
      <p className="muted small">
        <Link to="/">Back to sign in</Link>
      </p>
    </div>
  );
}
