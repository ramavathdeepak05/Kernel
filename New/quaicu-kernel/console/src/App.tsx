import { useState, useSyncExternalStore, type ReactNode } from "react";
import { Link, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { api, ApiError } from "./api/client";
import { ErrorBox } from "./components";
import { clearSession, getSession, isAuthenticated, setSession, subscribe } from "./state/auth";
import { EntitlementsProvider, useEntitlements, useFeature } from "./state/entitlements";
import { beginLogin, oidcEnabled } from "./oidc/oidc";
import Dashboard from "./pages/Dashboard";
import Policies from "./pages/Policies";
import Audit from "./pages/Audit";
import Approvals from "./pages/Approvals";
import Billing from "./pages/Billing";
import Callback from "./pages/Callback";
import Signup from "./pages/Signup";
import Plans from "./pages/Plans";
import ApiKeys from "./pages/ApiKeys";

function useSession() {
  return useSyncExternalStore(subscribe, getSession);
}

function useAuthed() {
  return useSyncExternalStore(subscribe, isAuthenticated);
}

function TierBadge() {
  const { data } = useEntitlements();
  if (!data?.tier) return null;
  return <span className={`tier-badge tier-${data.tier.toLowerCase()}`}>{data.tier}</span>;
}

function SignInButton() {
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    setErr(null);
    try {
      await beginLogin(); // redirects away on success
    } catch (e) {
      setErr(String((e as Error)?.message ?? e));
      setBusy(false);
    }
  }
  return (
    <>
      <button className="primary" onClick={go} disabled={busy}>
        {busy ? "Redirecting…" : "Sign in with your IdP"}
      </button>
      {err && <p className="error">{err}</p>}
    </>
  );
}

// Top-bar account menu — only mounted once signed in. Shows the tenant + tier and a sign-out.
function AccountMenu() {
  const session = useSession();
  const [open, setOpen] = useState(false);
  return (
    <div className="settings">
      <TierBadge />
      <button className="settings-toggle" onClick={() => setOpen((o) => !o)}>
        {session.tenant} ▾
      </button>
      {open && (
        <div className="settings-panel">
          <div className="muted small">Signed in as <strong>{session.tenant}</strong></div>
          <div className="settings-actions">
            <button className="secondary" onClick={clearSession}>Sign out</button>
          </div>
        </div>
      )}
    </div>
  );
}

// Developer sign-in: paste a token directly (local dev, or a dedicated deploy with no OIDC).
// Collapsed by default; lives inside the centered sign-in gate.
function DevSignIn() {
  const session = useSession();
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState(session.token);
  const [tenant, setTenant] = useState(session.tenant);
  const [apiBase, setApiBase] = useState(session.apiBase);

  function save() {
    setSession({ token: token.trim(), tenant: tenant.trim(), apiBase: apiBase.trim() });
  }

  return (
    <div className="dev-block">
      <button className="dev-toggle" onClick={() => setOpen((o) => !o)}>
        Developer sign-in {open ? "▴" : "▾"}
      </button>
      {open && (
        <div className="dev-signin">
          <label>
            Tenant id
            <input value={tenant} onChange={(e) => setTenant(e.target.value)} placeholder="ciro-bank" />
          </label>
          <label>
            Bearer token
            <input value={token} onChange={(e) => setToken(e.target.value)} placeholder="paste JWT or API key…" />
          </label>
          <label>
            API base (blank = built-in default)
            <input value={apiBase} onChange={(e) => setApiBase(e.target.value)} placeholder="" />
          </label>
          <div className="settings-actions">
            <button className="primary" onClick={save}>Save</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Nav() {
  const policies = useFeature("policies");
  const approvals = useFeature("approvals");
  const { data } = useEntitlements();
  const billing = (data?.billing_providers?.length ?? 0) > 0;
  return (
    <nav className="nav">
      <NavLink to="/" end>Dashboard</NavLink>
      {policies && <NavLink to="/policies">Policies</NavLink>}
      <NavLink to="/audit">Audit trail</NavLink>
      {approvals && <NavLink to="/approvals">Approvals</NavLink>}
      <NavLink to="/keys">API keys</NavLink>
      {billing && <NavLink to="/billing">Billing</NavLink>}
    </nav>
  );
}

function FeatureGate({ feature, label, children }: { feature: string; label: string; children: ReactNode }) {
  const enabled = useFeature(feature);
  const { data } = useEntitlements();
  if (enabled) return <>{children}</>;
  return (
    <div className="gate">
      <h2>{label} isn't included in your plan</h2>
      <p className="muted">
        This tenant is on the <strong>{data?.tier ?? "current"}</strong> tier. Upgrade to unlock{" "}
        {label.toLowerCase()}.
      </p>
    </div>
  );
}

// Primary sign-in: email + password → session token.
function LoginForm() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const resp = await api.login({ email: email.trim(), password });
      setSession({ token: resp.session_token, tenant: resp.tenant_id });
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === "INVALID_CREDENTIALS") {
        setError("Invalid email or password.");
      } else {
        setError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="signin-form" onSubmit={submit}>
      {error && <ErrorBox message={error} />}
      <label>
        Email
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" />
      </label>
      <label>
        Password
        <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" />
      </label>
      <button className="primary" type="submit" disabled={busy || !email.trim() || !password}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}

function SignInGate() {
  return (
    <div className="gate">
      <h2>Sign in to the console</h2>
      <div className="signin-hub">
        <LoginForm />
        {oidcEnabled() && (
          <>
            <div className="divider"><span>or</span></div>
            <p className="muted small">Authenticate with your organization's identity provider.</p>
            <SignInButton />
          </>
        )}
        <div className="divider"><span>new here?</span></div>
        <Link className="signup-cta" to="/plans">View plans &amp; sign up →</Link>
        <p className="muted small">Starter, Business, or Enterprise — pick your tier.</p>
        <div className="divider"><span>advanced</span></div>
        <DevSignIn />
      </div>
    </div>
  );
}

export default function App() {
  const authed = useAuthed();
  return (
    <EntitlementsProvider>
      <div className="app">
        <header className="topbar">
          <div className="brand">QUAICU&nbsp;<span className="muted">Console</span></div>
          {authed && <Nav />}
          {authed && <AccountMenu />}
        </header>
        <main className="content">
          <Routes>
            <Route path="/callback" element={<Callback />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/plans" element={<Plans />} />
            {authed ? (
              <>
                <Route path="/" element={<Dashboard />} />
                <Route
                  path="/policies"
                  element={
                    <FeatureGate feature="policies" label="Policy management">
                      <Policies />
                    </FeatureGate>
                  }
                />
                <Route path="/audit" element={<Audit />} />
                <Route
                  path="/approvals"
                  element={
                    <FeatureGate feature="approvals" label="Approvals">
                      <Approvals />
                    </FeatureGate>
                  }
                />
                <Route path="/keys" element={<ApiKeys />} />
                <Route path="/billing" element={<Billing />} />
              </>
            ) : (
              <Route path="*" element={<SignInGate />} />
            )}
          </Routes>
        </main>
      </div>
    </EntitlementsProvider>
  );
}
