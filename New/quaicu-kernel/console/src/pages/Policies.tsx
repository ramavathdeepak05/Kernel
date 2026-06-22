import { useState } from "react";
import { api, ApiError } from "../api/client";
import { Badge, Empty, ErrorBox, Loading, useApi } from "../components";
import type {
  PolicyPack,
  PolicyPackImportResult,
  PolicyRegisterBody,
  PolicyResponse,
  SimulateResponse,
} from "../api/types";

const LIFECYCLES = ["", "DRAFT", "REVIEW", "ACTIVATED", "DEPRECATED"];
const DECISIONS = ["allow", "deny", "require_approval"];

const BLANK: PolicyRegisterBody = {
  id: "", version: 1, governs: "", scope: { tenant: "*" }, condition: "true",
  decision: "allow", approvers: [], regulatory_refs: [],
};

export default function Policies() {
  const [filter, setFilter] = useState("");
  const list = useApi(() => api.listPolicies(filter || undefined), [filter]);
  const [err, setErr] = useState<string | null>(null);

  function wrap(p: Promise<unknown>) {
    setErr(null);
    p.then(() => list.reload()).catch((e) => setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)));
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>Policies</h1>
        <label className="inline">
          Lifecycle
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            {LIFECYCLES.map((l) => <option key={l} value={l}>{l || "all"}</option>)}
          </select>
        </label>
      </div>

      {err && <ErrorBox message={err} />}
      <PolicyPacks onImported={() => list.reload()} setErr={setErr} />
      <CreateForm onCreated={() => list.reload()} setErr={setErr} />

      {list.loading ? <Loading what="policies" /> : list.error ? <ErrorBox message={list.error} /> : (
        (list.data?.count ?? 0) === 0 ? <Empty message="No policies" /> : (
          <table className="data">
            <thead>
              <tr><th>Policy</th><th>Governs</th><th>Decision</th><th>Lifecycle</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {list.data!.policies.map((p) => (
                <PolicyRow key={`${p.id}@${p.version}`} p={p} wrap={wrap} setErr={setErr} reload={list.reload} />
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}

function PolicyRow({ p, wrap, setErr, reload }: {
  p: PolicyResponse;
  wrap: (x: Promise<unknown>) => void;
  setErr: (s: string | null) => void;
  reload: () => void;
}) {
  const [sim, setSim] = useState<SimulateResponse | null>(null);
  const [reviewedBy, setReviewedBy] = useState("user:compliance_officer");
  const [open, setOpen] = useState(false);

  function runSim() {
    setErr(null);
    api.simulatePolicy(p.id, p.version, { reviewed_by: reviewedBy })
      .then(setSim)
      .catch((e) => setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)));
  }

  function activate() {
    if (!sim) return;
    const r = sim.impact_report;
    // The operator's explicit click is the F-10 acknowledgment.
    wrap(api.activatePolicy(p.id, p.version, {
      reviewed_by: r.reviewed_by, reviewed_at: r.reviewed_at,
      decision_distribution: r.decision_distribution, flip_count: r.flip_count,
      fairness_delta: r.fairness_delta, acknowledged: true,
    }));
  }

  return (
    <>
      <tr>
        <td><code>{p.id}</code> <span className="muted">v{p.version}</span></td>
        <td>{p.governs}</td>
        <td><Badge value={p.decision} /></td>
        <td><Badge value={p.lifecycle} /></td>
        <td className="actions">
          {p.lifecycle === "DRAFT" && (
            <button onClick={() => wrap(api.submitPolicy(p.id, p.version))}>Submit for review</button>
          )}
          {p.lifecycle === "REVIEW" && (
            <button onClick={() => setOpen((o) => !o)}>Simulate / activate</button>
          )}
          {p.lifecycle === "ACTIVATED" && (
            <button className="danger" onClick={() => wrap(api.deprecatePolicy(p.id, p.version))}>Deprecate</button>
          )}
        </td>
      </tr>
      {open && p.lifecycle === "REVIEW" && (
        <tr className="detail-row">
          <td colSpan={5}>
            <div className="sim">
              <div className="sim-head">
                <label className="inline">Reviewed by
                  <input value={reviewedBy} onChange={(e) => setReviewedBy(e.target.value)} />
                </label>
                <button onClick={runSim}>Run backtest</button>
              </div>
              {sim && (
                <div className="sim-result">
                  <span>Evaluated <b>{sim.ledger_entries_evaluated}</b></span>
                  <span>Flipped <b>{sim.decisions_flipped}</b> ({(sim.flip_rate * 100).toFixed(1)}%)</span>
                  <span>Fairness Δ <b>{sim.fairness_delta ?? "—"}</b></span>
                  <span className="dist">dist: {JSON.stringify(sim.impact_report.decision_distribution)}</span>
                  <button className="primary" onClick={() => { activate(); reload(); }}>Acknowledge &amp; activate</button>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function CreateForm({ onCreated, setErr }: { onCreated: () => void; setErr: (s: string | null) => void }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<PolicyRegisterBody>(BLANK);
  const [approvers, setApprovers] = useState("");

  function submit() {
    setErr(null);
    const body: PolicyRegisterBody = {
      ...f,
      approvers: approvers.split(",").map((s) => s.trim()).filter(Boolean),
    };
    api.registerPolicy(body)
      .then(() => { setF(BLANK); setApprovers(""); setOpen(false); onCreated(); })
      .catch((e) => setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)));
  }

  if (!open) return <button className="primary mb" onClick={() => setOpen(true)}>+ New policy</button>;
  return (
    <div className="create-form">
      <div className="form-grid">
        <label>Id<input value={f.id} onChange={(e) => setF({ ...f, id: e.target.value })} placeholder="ciro.ifrs9.stage_transition" /></label>
        <label>Version<input type="number" min={1} value={f.version} onChange={(e) => setF({ ...f, version: Number(e.target.value) })} /></label>
        <label>Governs<input value={f.governs} onChange={(e) => setF({ ...f, governs: e.target.value })} placeholder="payments.wire or *" /></label>
        <label>Scope tenant<input value={f.scope.tenant} onChange={(e) => setF({ ...f, scope: { tenant: e.target.value } })} /></label>
        <label>Decision
          <select value={f.decision} onChange={(e) => setF({ ...f, decision: e.target.value })}>
            {DECISIONS.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>
        <label>Approvers (csv)<input value={approvers} onChange={(e) => setApprovers(e.target.value)} placeholder="role:risk_head" /></label>
        <label className="wide">CEL condition<input value={f.condition} onChange={(e) => setF({ ...f, condition: e.target.value })} placeholder="payload_amount > 1000" /></label>
      </div>
      <div className="form-actions">
        <button className="primary" onClick={submit}>Register (DRAFT)</button>
        <button onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </div>
  );
}

// Browse the shipped regulatory packs and import one as DRAFT policies (then backtest + activate
// through the normal lifecycle). Collapsed by default so it doesn't crowd the authoring view.
function PolicyPacks({ onImported, setErr }: { onImported: () => void; setErr: (s: string | null) => void }) {
  const [open, setOpen] = useState(false);
  const packs = useApi(() => api.listPolicyPacks(), []);

  if (!open) {
    return <button className="primary mb" onClick={() => setOpen(true)}>▸ Start from a policy pack</button>;
  }
  return (
    <div className="packs-section">
      <div className="packs-head">
        <span className="muted small">
          Import a ready-made regulatory baseline as DRAFT policies, then backtest &amp; activate each.
        </span>
        <button className="linklike" onClick={() => setOpen(false)}>Hide</button>
      </div>
      {packs.loading ? <Loading what="packs" /> : packs.error ? <ErrorBox message={packs.error} /> : (
        <div className="packs">
          {packs.data!.packs.map((p) => (
            <PackCard key={p.id} pack={p} onImported={onImported} setErr={setErr} />
          ))}
          {packs.data!.count === 0 && <Empty message="No packs available." />}
        </div>
      )}
    </div>
  );
}

function PackCard({ pack, onImported, setErr }: {
  pack: PolicyPack;
  onImported: () => void;
  setErr: (s: string | null) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PolicyPackImportResult | null>(null);
  const [showRules, setShowRules] = useState(false);

  async function importPack() {
    setBusy(true);
    setErr(null);
    try {
      const r = await api.importPolicyPack(pack.id);
      setResult(r);
      onImported();
    } catch (e) {
      setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pack-card">
      <div className="pack-title">{pack.name}</div>
      <div className="pack-reg mono small">{pack.regulation}</div>
      <p className="muted small">{pack.summary || pack.description}</p>
      <div className="pack-meta mono small">
        {pack.policy_count} policies · {pack.action_types.join(", ")}
      </div>
      <div className="pack-actions">
        <button className="primary small" onClick={importPack} disabled={busy}>
          {busy ? "Importing…" : "Import as DRAFTs"}
        </button>
        <button className="linklike" onClick={() => setShowRules((s) => !s)}>
          {showRules ? "Hide details" : "Show details"}
        </button>
      </div>
      {result && (
        <div className="pack-result small">
          Imported <strong>{result.count}</strong> as DRAFT.
          {result.skipped.length > 0 && (
            <span className="muted"> {result.skipped.length} skipped ({result.skipped.map((s) => s.reason).join(", ")}).</span>
          )}{" "}
          See them below under <Badge value="DRAFT" />.
        </div>
      )}
      {showRules && (
        <div className="pack-details">
          {pack.usage && <p className="muted small">{pack.usage}</p>}

          {pack.action_specs.length > 0 && (
            <>
              <div className="pack-subhead">How to use</div>
              {pack.action_specs.map((a) => (
                <div className="action-spec" key={a.name}>
                  <div><code>{a.name}</code> <span className="muted small">— {a.use_case}</span></div>
                  <div className="small"><span className="kv-label">payload</span> <span className="mono">{a.payload}</span></div>
                  {a.example && <pre className="action-example">{a.example}</pre>}
                </div>
              ))}
            </>
          )}

          <div className="pack-subhead">Policies ({pack.policy_count})</div>
          <ul className="policy-list">
            {pack.policies.map((pol) => (
              <li className="policy-item" key={pol.id}>
                <div className="policy-item-head">
                  <Badge value={pol.decision} />
                  <strong>{pol.title}</strong>
                </div>
                {pol.description && <div className="muted small">{pol.description}</div>}
                <div className="policy-item-meta mono small">
                  governs {pol.governs}
                  {pol.regulatory_refs.length > 0 && <> · {pol.regulatory_refs.join(", ")}</>}
                  {pol.approvers.length > 0 && <> · approver {pol.approvers.join(", ")}</>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
