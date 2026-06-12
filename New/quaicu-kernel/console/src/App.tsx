import { useState, useSyncExternalStore } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { getSession, isAuthenticated, setSession, subscribe } from "./state/auth";
import Dashboard from "./pages/Dashboard";
import Policies from "./pages/Policies";
import Audit from "./pages/Audit";
import Approvals from "./pages/Approvals";

function useSession() {
  return useSyncExternalStore(subscribe, getSession);
}

function SettingsBar() {
  const session = useSession();
  const [open, setOpen] = useState(!isAuthenticated());
  const [token, setToken] = useState(session.token);
  const [tenant, setTenant] = useState(session.tenant);
  const [apiBase, setApiBase] = useState(session.apiBase);

  function save() {
    setSession({ token: token.trim(), tenant: tenant.trim(), apiBase: apiBase.trim() });
    setOpen(false);
  }

  return (
    <div className="settings">
      <button className="settings-toggle" onClick={() => setOpen((o) => !o)}>
        {isAuthenticated() ? `${session.tenant} ▾` : "Set token ▾"}
      </button>
      {open && (
        <div className="settings-panel">
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
          <button className="primary" onClick={save}>Save</button>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const authed = useSyncExternalStore(subscribe, isAuthenticated);
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">QUAICU&nbsp;<span className="muted">Console</span></div>
        <nav className="nav">
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/policies">Policies</NavLink>
          <NavLink to="/audit">Audit trail</NavLink>
          <NavLink to="/approvals">Approvals</NavLink>
        </nav>
        <SettingsBar />
      </header>
      <main className="content">
        {!authed ? (
          <div className="gate">
            <h2>Not authenticated</h2>
            <p className="muted">
              Set a <strong>tenant id</strong> and a <strong>bearer token</strong> (top-right) to
              reach the kernel API. The console does not mint tokens — paste one your IdentityPort
              accepts.
            </p>
          </div>
        ) : (
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/policies" element={<Policies />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="/approvals" element={<Approvals />} />
          </Routes>
        )}
      </main>
    </div>
  );
}
