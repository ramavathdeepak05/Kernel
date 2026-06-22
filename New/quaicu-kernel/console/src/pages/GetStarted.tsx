// Get started (/start) — the first-run surface. Three steps:
//   1. Your credentials (tenant id + an API key for programmatic calls)
//   2. Try a governed action live — POSTs /v1/authorize and shows the real decision + ledger seal
//   3. Call it from your own code — copy-paste curl / Python pre-filled with your tenant + key
//
// The live "try it" uses the console's own login session (the api client injects the bearer); the
// code snippets use a long-lived API key (qk_…) the user mints here. The seeded STARTER policy
// `demo.payment` denies payload_amount > 1_000_000 and allows everything else, so the demo produces
// a real ALLOW/DENY out of the box with zero setup.

import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { Badge, ErrorBox, useApi } from "../components";
import { getSession } from "../state/auth";
import type { AuthorizeResponse, CreatedApiKey } from "../api/types";

const DEMO_TYPE = "demo.payment";
const PLACEHOLDER_KEY = "qk_YOUR_API_KEY";

// Absolute origin of the kernel API for copy-paste snippets. The console is served same-origin with
// the kernel (Cloudflare Worker proxies /v1), so window.location.origin is correct unless a manual
// apiBase override is set.
function apiOrigin(): string {
  const { apiBase } = getSession();
  if (apiBase && /^https?:\/\//.test(apiBase)) return apiBase.replace(/\/$/, "");
  return window.location.origin;
}

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setDone(true);
      setTimeout(() => setDone(false), 1500);
    } catch {
      setDone(false);
    }
  }
  return (
    <button className="secondary small" onClick={copy} type="button">
      {done ? "Copied ✓" : label}
    </button>
  );
}

export default function GetStarted() {
  const session = getSession();
  const tenant = session.tenant;
  const origin = apiOrigin();

  // ── Step 2: live try-it ──────────────────────────────────────────────────
  const [amount, setAmount] = useState(250000);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<AuthorizeResponse | null>(null);
  const [tryError, setTryError] = useState<string | null>(null);

  async function runAuthorize(value: number) {
    setAmount(value);
    setRunning(true);
    setTryError(null);
    setResult(null);
    try {
      const r = await api.authorize({ type: DEMO_TYPE, payload: { amount: value } });
      setResult(r);
    } catch (err) {
      setTryError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setRunning(false);
    }
  }

  // ── Step 1/3: API key for the snippets ───────────────────────────────────
  const keys = useApi(() => api.listKeys(), []);
  const [created, setCreated] = useState<CreatedApiKey | null>(null);
  const [creating, setCreating] = useState(false);
  const [keyError, setKeyError] = useState<string | null>(null);

  async function createKey() {
    setCreating(true);
    setKeyError(null);
    try {
      setCreated(await api.createKey());
      keys.reload();
    } catch (err) {
      setKeyError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setCreating(false);
    }
  }

  const snippetKey = created?.api_key ?? PLACEHOLDER_KEY;
  const hasActiveKey = (keys.data?.keys.some((k) => !k.revoked) ?? false) || !!created;

  const curlSnippet = `curl -X POST ${origin}/v1/authorize \\
  -H "Authorization: Bearer ${snippetKey}" \\
  -H "X-Tenant-Id: ${tenant}" \\
  -H "Content-Type: application/json" \\
  -d '{"type":"${DEMO_TYPE}","payload":{"amount":${amount}}}'`;

  const pySnippet = `import requests

resp = requests.post(
    "${origin}/v1/authorize",
    headers={
        "Authorization": "Bearer ${snippetKey}",
        "X-Tenant-Id": "${tenant}",
    },
    json={"type": "${DEMO_TYPE}", "payload": {"amount": ${amount}}},
)
verdict = resp.json()
print(verdict["decision"], verdict["allowed"])  # -> "deny" False  (amount > 1,000,000)`;

  return (
    <div className="page getstarted">
      <div className="page-head">
        <h1>Get started</h1>
        <Badge value="STARTER" />
      </div>
      <p className="muted">
        QUAICU governs every AI/automated action against your policy before it runs —{" "}
        <strong>AI proposes, rules enforce, humans approve</strong>. Try a real governed decision
        below, then drop the same call into your own code.
      </p>

      {/* Step 1 — credentials ------------------------------------------------ */}
      <section className="step">
        <div className="step-head"><span className="step-no">1</span><h2>Your credentials</h2></div>
        <div className="kv-row">
          <span className="kv-label">Tenant id</span>
          <code className="key-value">{tenant}</code>
          <CopyButton text={tenant} />
        </div>
        <div className="kv-row">
          <span className="kv-label">API base</span>
          <code className="key-value">{origin}</code>
          <CopyButton text={origin} />
        </div>

        {keyError && <ErrorBox message={keyError} />}
        {created ? (
          <div className="card key-callout">
            <div className="card-body">
              <p className="muted small">
                New API key — shown <strong>once</strong>. It's baked into the snippets below; store
                it somewhere safe.
              </p>
              <div className="key-reveal">
                <code className="key-value">{created.api_key}</code>
                <CopyButton text={created.api_key} />
              </div>
            </div>
          </div>
        ) : (
          <div className="kv-row">
            <span className="kv-label">API key</span>
            <span className="muted small">
              {hasActiveKey
                ? "You already have an active key. Create a fresh one to use in the snippets below (the old one keeps working)."
                : "Mint a key for programmatic calls — the console itself uses your login session."}
            </span>
            <button className="primary small" onClick={createKey} disabled={creating} type="button">
              {creating ? "Creating…" : "+ Create API key"}
            </button>
          </div>
        )}
      </section>

      {/* Step 2 — live try-it ------------------------------------------------ */}
      <section className="step">
        <div className="step-head"><span className="step-no">2</span><h2>Try a governed action</h2></div>
        <p className="muted small">
          The seeded <code>{DEMO_TYPE}</code> policy <strong>denies</strong> amounts over
          ₹10,00,000 and allows the rest. This hits the live kernel and seals the decision to your
          tamper-evident ledger.
        </p>
        <div className="try-panel">
          <label className="try-amount">
            Amount (₹)
            <input
              type="number"
              min={0}
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value))}
            />
          </label>
          <div className="try-presets">
            <button className="secondary small" type="button" onClick={() => runAuthorize(250000)}>
              Allowed example (₹2,50,000)
            </button>
            <button className="secondary small" type="button" onClick={() => runAuthorize(1500000)}>
              Denied example (₹15,00,000)
            </button>
          </div>
          <button className="primary" type="button" disabled={running} onClick={() => runAuthorize(amount)}>
            {running ? "Evaluating…" : "▸ Run authorize"}
          </button>
        </div>

        {tryError && <ErrorBox message={tryError} />}
        {result && (
          <div className={`decision-result ${result.allowed ? "is-allow" : "is-deny"}`}>
            <div className="decision-head">
              <Badge value={result.decision} />
              <span className="muted small">actor {result.actor_id}</span>
            </div>
            <table className="kv">
              <tbody>
                {result.reason && (
                  <tr><td>Reason</td><td>{result.reason}</td></tr>
                )}
                <tr><td>Enforced layers</td><td className="mono small">{result.enforced_layers.join(", ") || "—"}</td></tr>
                <tr><td>Policy versions</td><td className="mono small">{result.policy_versions.join(", ") || "—"}</td></tr>
                <tr>
                  <td>Sealed to ledger</td>
                  <td>{result.sealed ? `yes — entry #${result.ledger_seq}` : "no"}</td>
                </tr>
              </tbody>
            </table>
            {result.sealed && (
              <p className="muted small">
                This decision is now an immutable entry in your{" "}
                <Link to="/audit">audit trail</Link>.
              </p>
            )}
          </div>
        )}
      </section>

      {/* Step 3 — code ------------------------------------------------------- */}
      <section className="step">
        <div className="step-head"><span className="step-no">3</span><h2>Call it from your code</h2></div>
        <p className="muted small">
          Same call, with a long-lived API key. Make this your Policy Enforcement Point: ask the
          kernel <em>before</em> you execute, then honour the verdict.
          {!created && (
            <> Snippets show <code>{PLACEHOLDER_KEY}</code> — create a key in step 1 to bake in a real one.</>
          )}
        </p>

        <div className="code-block">
          <div className="code-head"><span className="mono small">curl</span><CopyButton text={curlSnippet} /></div>
          <pre>{curlSnippet}</pre>
        </div>
        <div className="code-block">
          <div className="code-head"><span className="mono small">python</span><CopyButton text={pySnippet} /></div>
          <pre>{pySnippet}</pre>
        </div>
      </section>

      {/* Next ---------------------------------------------------------------- */}
      <section className="step">
        <div className="step-head"><span className="step-no">→</span><h2>Next</h2></div>
        <ul className="next-links">
          <li><Link to="/policies">Author your own policies</Link> — replace the demo rule with your CEL.</li>
          <li><Link to="/audit">Audit trail</Link> — every sealed decision, tamper-evident.</li>
          <li><Link to="/keys">API keys</Link> — manage programmatic access.</li>
        </ul>
      </section>
    </div>
  );
}
