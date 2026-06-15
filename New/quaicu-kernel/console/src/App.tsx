import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { clearSession, getSession, isAuthenticated, setSession, subscribe } from "./state/auth";
import { EntitlementsProvider, useEntitlements, useFeature } from "./state/entitlements";
import { beginLogin, oidcEnabled } from "./oidc/oidc";
import Dashboard from "./pages/Dashboard";
import Policies from "./pages/Policies";
import Audit from "./pages/Audit";
import Approvals from "./pages/Approvals";
import Billing from "./pages/Billing";
import Callback from "./pages/Callback";

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

function SettingsBar() {
  const session = useSession();
  const authed = useAuthed();
  const [open, setOpen] = useState(!authed);
  const [token, setToken] = useState(session.token);
  const [tenant, setTenant] = useState(session.tenant);
  const [apiBase, setApiBase] = useState(session.apiBase);

  // Collapse the panel once a session exists (e.g. after an OIDC redirect completes).
  useEffect(() => {
    if (authed) setOpen(false);
  }, [authed]);

  function save() {
    setSession({ token: token.trim(), tenant: tenant.trim(), apiBase: apiBase.trim() });
    setOpen(false);
  }

  function signOut() {
    clearSession();
    setToken("");
    setTenant("");
    setOpen(true);
  }

  return (
    <div className="settings">
      <TierBadge />
      <button className="settings-toggle" onClick={() => setOpen((o) => !o)}>
        {authed ? `${session.tenant} ▾` : "Sign in ▾"}
      </button>
      {open && (
        <div className="settings-panel">
          {oidcEnabled() && !authed && (
            <div className="oidc-row">
              <SignInButton />
              <div className="divider"><span>or set a token manually</span></div>
            </div>
          )}
          <label>
            Tenant id
            <input value={tenant} onChange={(e) => setTenant(e.target.value)} placeholder="ciro-bank" />
          </label>
          <label>
            Bearer token
            <input value={token} onChange={(e) => setToken(e.target.value)} placeholder="paste JWT…" />
          </label>
          <label>
            API base (blank = dev proxy)
            <input value={apiBase} onChange={(e) => setApiBase(e.target.value)} placeholder="" />
          </label>
          <div className="settings-actions">
            <button className="primary" onClick={save}>Save</button>
            {authed && (
              <button className="secondary" onClick={signOut}>Sign out</button>
            )}
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

function SignInGate() {
  return (
    <div className="gate">
      <h2>Sign in to the console</h2>
      {oidcEnabled() ? (
        <>
          <p className="muted">Authenticate with your organization's identity provider.</p>
          <SignInButton />
          <p className="muted small">
            Or set a token manually from the menu (top-right) for local development.
          </p>
        </>
      ) : (
        <p className="muted">
          Set a <strong>tenant id</strong> and a <strong>bearer token</strong> (top-right) to reach the
          kernel API. The console does not mint tokens — paste one your IdentityPort accepts.
        </p>
      )}
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
          <SettingsBar />
        </header>
        <main className="content">
          <Routes>
            <Route path="/callback" element={<Callback />} />
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
