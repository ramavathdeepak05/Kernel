// MCP gateway (/mcp) — connect your own downstream MCP server (BYO tools). Once connected, point any
// MCP client at <origin>/mcp and authenticate with a QUAICU API key: every tool call is governed
// (policy + ledger) then forwarded to YOUR downstream MCP server.

import { useState } from "react";
import { api, ApiError } from "../api/client";
import { Badge, ErrorBox, Loading, useApi } from "../components";
import { getSession } from "../state/auth";

const TRANSPORTS: Record<string, string> = {
  "Streamable HTTP": "streamable_http",
  SSE: "sse",
};

function apiOrigin(): string {
  const { apiBase } = getSession();
  if (apiBase && /^https?:\/\//.test(apiBase)) return apiBase.replace(/\/$/, "");
  return window.location.origin;
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button className="secondary small" type="button" onClick={async () => {
      try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); } catch { /* ignore */ }
    }}>{done ? "Copied ✓" : "Copy"}</button>
  );
}

export default function MCPGateway() {
  const conn = useApi(() => api.getMCPConnection(), []);
  const [url, setUrl] = useState("");
  const [transportLabel, setTransportLabel] = useState("Streamable HTTP");
  const [authValue, setAuthValue] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const gatewayBase = `${apiOrigin()}/mcp`;
  const asErr = (e: unknown) => (e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.setMCPConnection({
        url: url.trim(),
        transport: TRANSPORTS[transportLabel],
        auth_value: authValue.trim(),
        name: name.trim(),
      });
      setAuthValue("");
      conn.reload();
    } catch (err) {
      setError(asErr(err));
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!window.confirm("Disconnect your downstream MCP server? Governed tool calls will fail until you reconnect.")) return;
    setError(null);
    try {
      await api.deleteMCPConnection();
      conn.reload();
    } catch (err) {
      setError(asErr(err));
    }
  }

  const snippet = `# Point any MCP client at the governed endpoint with your QUAICU key:
#   URL:  ${gatewayBase}
#   Auth: Authorization: Bearer qk_your_quaicu_key
#
# Every tools/call is governed by your mcp.* policies + sealed to your ledger,
# then forwarded to YOUR downstream MCP server.`;

  const connected = conn.data?.connected;

  return (
    <div className="page">
      <div className="page-head"><h1>MCP gateway</h1>{connected && <Badge value="ACTIVATED" />}</div>
      <p className="muted">
        Connect your own <strong>downstream MCP server</strong>. Point any MCP client at the gateway and
        every tool call is <strong>governed</strong> (your <code>mcp.*</code> policies + sealed to your
        ledger), then forwarded to <strong>your</strong> tools — one governed endpoint, your tools, your
        policies. No code shipped to your agents.
      </p>

      {error && <ErrorBox message={error} />}

      {conn.loading ? <Loading what="connection" /> : (
        <>
          {connected && conn.data && (
            <div className="card key-callout">
              <div className="card-body">
                {conn.data.name && <div className="kv-row"><span className="kv-label">Name</span><span>{conn.data.name}</span></div>}
                <div className="kv-row"><span className="kv-label">Downstream URL</span><code className="key-value">{conn.data.url}</code></div>
                <div className="kv-row"><span className="kv-label">Transport</span><span className="mono">{conn.data.transport}</span></div>
                <div className="kv-row"><span className="kv-label">Auth</span><span>{conn.data.auth_set ? `Set (${conn.data.auth_header})` : "None"}</span></div>
                <button className="secondary small" onClick={disconnect}>Disconnect</button>
              </div>
            </div>
          )}

          <section className="step">
            <div className="step-head"><span className="step-no">{connected ? "↻" : "1"}</span><h2>{connected ? "Replace connection" : "Connect a downstream"}</h2></div>
            <form className="signin-form" onSubmit={save} style={{ maxWidth: 520 }}>
              <label>Downstream MCP URL
                <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://tools.example.com/mcp" />
              </label>
              <label>Transport
                <select value={transportLabel} onChange={(e) => setTransportLabel(e.target.value)}>
                  {Object.keys(TRANSPORTS).map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
              <label>Auth header value <span className="muted small">(optional — e.g. "Bearer …"; stored encrypted, shown back only masked)</span>
                <input type="password" value={authValue} onChange={(e) => setAuthValue(e.target.value)} placeholder="Bearer ••••••••" autoComplete="off" />
              </label>
              <label>Name <span className="muted small">(optional)</span>
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme tools" />
              </label>
              <button className="primary" type="submit" disabled={busy || !url.trim()}>
                {busy ? "Saving…" : connected ? "Replace connection" : "Connect"}
              </button>
            </form>
          </section>

          <section className="step">
            <div className="step-head"><span className="step-no">{connected ? "2" : "→"}</span><h2>Point your agent at it</h2></div>
            <p className="muted small">
              Connect any MCP client (Streamable HTTP) to the gateway, authenticated with a{" "}
              <strong>QUAICU API key</strong> (create one on the API keys page). The gateway mirrors your
              downstream's tools and governs every call.
            </p>
            <div className="code-block">
              <div className="code-head"><span className="mono small">mcp</span><CopyButton text={snippet} /></div>
              <pre>{snippet}</pre>
            </div>
            <div className="kv-row"><span className="kv-label">Gateway URL</span><code className="key-value">{gatewayBase}</code><CopyButton text={gatewayBase} /></div>
          </section>
        </>
      )}
    </div>
  );
}
