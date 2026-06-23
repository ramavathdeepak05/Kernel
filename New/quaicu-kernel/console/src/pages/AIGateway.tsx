// AI gateway (/ai) — connect your own LLM provider (BYO key). Once connected, point any
// OpenAI-compatible SDK's base_url at <origin>/v1/ai and authenticate with a QUAICU API key:
// every model call is governed (policy + ledger) then forwarded to YOUR provider with YOUR key.

import { useState } from "react";
import { api, ApiError } from "../api/client";
import { Badge, ErrorBox, Loading, useApi } from "../components";
import { getSession } from "../state/auth";

const PRESETS: Record<string, string> = {
  OpenAI: "https://api.openai.com/v1",
  "Together AI": "https://api.together.xyz/v1",
  Groq: "https://api.groq.com/openai/v1",
  Mistral: "https://api.mistral.ai/v1",
  Custom: "",
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

export default function AIGateway() {
  const conn = useApi(() => api.getAIConnection(), []);
  const [provider, setProvider] = useState("OpenAI");
  const [baseUrl, setBaseUrl] = useState(PRESETS.OpenAI);
  const [apiKey, setApiKey] = useState("");
  const [defaultModel, setDefaultModel] = useState("");
  const [maskPii, setMaskPii] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const gatewayBase = `${apiOrigin()}/v1/ai`;
  const asErr = (e: unknown) => (e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));

  function pickProvider(p: string) {
    setProvider(p);
    if (p in PRESETS && PRESETS[p]) setBaseUrl(PRESETS[p]);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.setAIConnection({ provider, base_url: baseUrl.trim(), api_key: apiKey.trim(), default_model: defaultModel.trim(), mask_pii: maskPii });
      setApiKey("");
      conn.reload();
    } catch (err) {
      setError(asErr(err));
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!window.confirm("Disconnect your AI provider? Governed calls will fail until you reconnect.")) return;
    setError(null);
    try {
      await api.deleteAIConnection();
      conn.reload();
    } catch (err) {
      setError(asErr(err));
    }
  }

  const snippet = `from openai import OpenAI

client = OpenAI(
    base_url="${gatewayBase}",
    api_key="qk_your_quaicu_key",   # your QUAICU key, not your provider key
)

resp = client.chat.completions.create(
    model="${defaultModel || "gpt-4o-mini"}",
    messages=[{"role": "user", "content": "Hello"}],
)
print(resp.choices[0].message.content)
# -> governed by your ai.chat policies + sealed to your ledger, then run on YOUR provider`;

  const connected = conn.data?.connected;

  return (
    <div className="page">
      <div className="page-head"><h1>AI gateway</h1>{connected && <Badge value="ACTIVATED" />}</div>
      <p className="muted">
        Connect your own LLM provider. Point any OpenAI-compatible SDK at the gateway and every model
        call is <strong>governed</strong> (your <code>ai.chat</code> policies + sealed to your ledger),
        then forwarded to <strong>your</strong> provider with <strong>your</strong> key — you pay your
        provider directly.
      </p>

      {error && <ErrorBox message={error} />}

      {conn.loading ? <Loading what="connection" /> : (
        <>
          {connected && conn.data && (
            <div className="card key-callout">
              <div className="card-body">
                <div className="kv-row"><span className="kv-label">Provider</span><span>{conn.data.provider}</span></div>
                <div className="kv-row"><span className="kv-label">Base URL</span><code className="key-value">{conn.data.base_url}</code></div>
                <div className="kv-row"><span className="kv-label">Key</span><span className="mono">{conn.data.key_hint}</span></div>
                {conn.data.default_model && <div className="kv-row"><span className="kv-label">Model</span><span className="mono">{conn.data.default_model}</span></div>}
                <div className="kv-row"><span className="kv-label">PII masking</span><span>{conn.data.mask_pii ? "On — PII tokenized before your provider sees it" : "Off"}</span></div>
                <button className="secondary small" onClick={disconnect}>Disconnect</button>
              </div>
            </div>
          )}

          <section className="step">
            <div className="step-head"><span className="step-no">{connected ? "↻" : "1"}</span><h2>{connected ? "Replace connection" : "Connect a provider"}</h2></div>
            <form className="signin-form" onSubmit={save} style={{ maxWidth: 520 }}>
              <label>Provider
                <select value={provider} onChange={(e) => pickProvider(e.target.value)}>
                  {Object.keys(PRESETS).map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </label>
              <label>Base URL
                <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" />
              </label>
              <label>Provider API key
                <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-…  (stored encrypted, shown back only masked)" autoComplete="off" />
              </label>
              <label>Default model <span className="muted small">(optional)</span>
                <input value={defaultModel} onChange={(e) => setDefaultModel(e.target.value)} placeholder="gpt-4o-mini" />
              </label>
              <label className="checkbox-row">
                <input type="checkbox" checked={maskPii} onChange={(e) => setMaskPii(e.target.checked)} />
                <span>Mask PII <span className="muted small">— tokenize emails, PAN, Aadhaar, cards, etc. before your provider sees them; rehydrated in the response. Available on all plans.</span></span>
              </label>
              <button className="primary" type="submit" disabled={busy || !baseUrl.trim() || !apiKey.trim()}>
                {busy ? "Saving…" : connected ? "Replace connection" : "Connect"}
              </button>
            </form>
          </section>

          <section className="step">
            <div className="step-head"><span className="step-no">{connected ? "2" : "→"}</span><h2>Use it from your code</h2></div>
            <p className="muted small">
              One line changes — your existing OpenAI SDK, pointed at the gateway, authenticated with a{" "}
              <strong>QUAICU API key</strong> (create one on the API keys page). Streaming (<code>stream=True</code>) is supported.
            </p>
            <div className="code-block">
              <div className="code-head"><span className="mono small">python</span><CopyButton text={snippet} /></div>
              <pre>{snippet}</pre>
            </div>
            <div className="kv-row"><span className="kv-label">Gateway URL</span><code className="key-value">{gatewayBase}</code><CopyButton text={gatewayBase} /></div>
          </section>

          <section className="step">
            <div className="step-head"><span className="step-no">+</span><h2>More providers — coming soon</h2></div>
            <p className="muted small">
              Today the gateway speaks the OpenAI-compatible API (OpenAI, Together, Groq, Mistral,
              OpenRouter, local vLLM, …). Native shims for these land in the next kernel release:
            </p>
            <div className="coming-soon-row">
              <span className="provider-chip disabled">Azure OpenAI <Badge value="SOON" /></span>
              <span className="provider-chip disabled">Anthropic <Badge value="SOON" /></span>
            </div>
            <p className="muted small">
              Want early access? <a href="mailto:support@quaicu.org?subject=AI%20gateway%20provider%20pre-order">Pre-order / notify me →</a>
            </p>
          </section>
        </>
      )}
    </div>
  );
}
