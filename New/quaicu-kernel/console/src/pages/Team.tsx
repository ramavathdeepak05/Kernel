// Team page (W6-1) — invite / list members, change roles, deactivate.
// Members are the users in your tenant. Enterprise IdPs can also provision them over SCIM 2.0;
// deactivating a member (here or via the IdP) revokes their API keys.

import { useState } from "react";
import { api, ApiError } from "../api/client";
import { Empty, ErrorBox, Loading, useApi } from "../components";

export default function Team() {
  const list = useApi(() => api.listMembers(), []);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("VIEWER");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const roles = list.data?.roles ?? ["OWNER", "ADMIN", "COMPLIANCE", "VIEWER"];

  function asError(err: unknown): string {
    return err instanceof ApiError ? `${err.code}: ${err.message}` : String(err);
  }

  async function invite() {
    if (!email.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.inviteMember({ email: email.trim(), role });
      setEmail("");
      list.reload();
    } catch (err) {
      setError(asError(err));
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(memberId: string, newRole: string) {
    setError(null);
    try {
      await api.setMemberRole(memberId, newRole);
      list.reload();
    } catch (err) {
      setError(asError(err));
    }
  }

  async function deactivate(memberId: string, who: string) {
    if (!window.confirm(`Deactivate ${who}? Their API keys are revoked immediately.`)) return;
    setError(null);
    try {
      await api.deactivateMember(memberId);
      list.reload();
    } catch (err) {
      setError(asError(err));
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>Team</h1>
      </div>
      <p className="muted">
        Members are the people in your workspace. Enterprise IdPs (Okta, Entra) can also provision
        members automatically over SCIM 2.0 — deactivating a member revokes their access.
      </p>

      {error && <ErrorBox message={error} />}

      <div className="card">
        <div className="card-title">Invite a member</div>
        <div className="card-body invite-row">
          <input
            type="email"
            placeholder="name@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-label="Member email"
          />
          <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role">
            {roles.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
          <button className="primary" onClick={invite} disabled={busy || !email.trim()}>
            {busy ? "Inviting…" : "Invite"}
          </button>
        </div>
      </div>

      {list.loading ? (
        <Loading what="members" />
      ) : list.error ? (
        <ErrorBox message={list.error} />
      ) : (list.data?.members.length ?? 0) === 0 ? (
        <Empty message="No members yet. Invite your first teammate above." />
      ) : (
        <table className="data">
          <thead>
            <tr><th>Email</th><th>Name</th><th>Role</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {list.data!.members.map((m) => {
              const active = m.status === "ACTIVE";
              return (
                <tr key={m.member_id}>
                  <td>{m.email}</td>
                  <td className="muted">{m.display_name}</td>
                  <td>
                    <select
                      value={m.role}
                      disabled={!active}
                      onChange={(e) => changeRole(m.member_id, e.target.value)}
                      aria-label={`Role for ${m.email}`}
                    >
                      {roles.map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                  </td>
                  <td>{active ? "active" : <span className="muted">deactivated</span>}</td>
                  <td>
                    {active && (
                      <button className="linklike" onClick={() => deactivate(m.member_id, m.email)}>
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
