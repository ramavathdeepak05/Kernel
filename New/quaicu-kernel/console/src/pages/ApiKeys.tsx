// API Keys page — create / list / revoke programmatic keys for this tenant.
// The console itself authenticates with your login session; these keys are for your own
// apps/scripts/CI calling the kernel API. New keys are shown ONCE.

import { useState } from "react";
import { api, ApiError } from "../api/client";
import { Empty, ErrorBox, Loading, useApi } from "../components";
import type { CreatedApiKey } from "../api/types";

export default function ApiKeys() {
  const list = useApi(() => api.listKeys(), []);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<CreatedApiKey | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function asError(err: unknown): string {
    return err instanceof ApiError ? `${err.code}: ${err.message}` : String(err);
  }

  async function create() {
    setCreating(true);
    setError(null);
    try {
      setCreated(await api.createKey());
      list.reload();
    } catch (err) {
      setError(asError(err));
    } finally {
      setCreating(false);
    }
  }

  async function revoke(keyId: string) {
    if (!window.confirm(`Revoke ${keyId}? Any integration using it will stop working immediately.`)) return;
    setError(null);
    try {
      await api.revokeKey(keyId);
      list.reload();
    } catch (err) {
      setError(asError(err));
    }
  }

  async function copy() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.api_key);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>API keys</h1>
        <button className="primary" onClick={create} disabled={creating}>
          {creating ? "Creating…" : "+ New key"}
        </button>
      </div>
      <p className="muted">
        Keys authenticate programmatic calls to the kernel API (your apps, scripts, CI). The console
        itself uses your login session — not a key.
      </p>

      {error && <ErrorBox message={error} />}

      {created && (
        <div className="card signup-card">
          <div className="card-title">New API key — copy it now</div>
          <div className="card-body">
            <p className="muted small">
              Shown <strong>once</strong>. Store it securely — you can't see it again.
            </p>
            <div className="key-reveal">
              <code className="key-value">{created.api_key}</code>
              <button onClick={copy}>{copied ? "Copied ✓" : "Copy"}</button>
            </div>
            <button className="linklike" onClick={() => setCreated(null)}>Dismiss</button>
          </div>
        </div>
      )}

      {list.loading ? (
        <Loading what="keys" />
      ) : list.error ? (
        <ErrorBox message={list.error} />
      ) : (list.data?.keys.length ?? 0) === 0 ? (
        <Empty message="No API keys yet. Create one when you need programmatic access." />
      ) : (
        <table className="data">
          <thead>
            <tr><th>Key id</th><th>Created</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {list.data!.keys.map((k) => (
              <tr key={k.key_id}>
                <td><code>{k.key_id}</code></td>
                <td className="muted">{new Date(k.created_at).toLocaleString()}</td>
                <td>{k.revoked ? <span className="muted">revoked</span> : "active"}</td>
                <td>{!k.revoked && <button className="linklike" onClick={() => revoke(k.key_id)}>Revoke</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
