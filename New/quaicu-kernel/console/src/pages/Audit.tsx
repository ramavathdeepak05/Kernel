import { Fragment, useState } from "react";
import { api, ApiError } from "../api/client";
import { Badge, Empty, ErrorBox, Loading, useApi } from "../components";
import { getSession } from "../state/auth";
import type { LedgerEntryResponse } from "../api/types";

function downloadFile(filename: string, text: string, mime: string) {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// RFC-4180 quoting: wrap in quotes and double any embedded quotes.
function csvCell(value: unknown): string {
  const s = value == null ? "" : String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function trailToCsv(entries: LedgerEntryResponse[]): string {
  const header = ["ledger_seq", "action_type", "decision", "actor_id", "approver", "sealed_at", "policy_versions"];
  const rows = entries.map((e) =>
    [e.ledger_seq, e.action_type, e.decision, e.actor_id, e.approver ?? "", e.sealed_at, e.policy_versions.join("|")]
      .map(csvCell)
      .join(","),
  );
  return [header.join(","), ...rows].join("\r\n");
}

export default function Audit() {
  const trail = useApi(() => api.ledgerTrail(), []);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const today = new Date().toISOString().slice(0, 10);
  const tenant = getSession().tenant || "tenant";
  const entries = trail.data?.entries ?? [];

  function exportCsv() {
    downloadFile(`quaicu-audit-${tenant}-${today}.csv`, trailToCsv(entries), "text/csv");
  }

  async function exportProofBundle() {
    setBusy(true);
    setError(null);
    try {
      const bundle = await api.exportLedger();
      downloadFile(
        `quaicu-ledger-proof-${tenant}-${today}.json`,
        JSON.stringify(bundle, null, 2),
        "application/json",
      );
    } catch (err) {
      setError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>Audit trail</h1>
        <div className="head-actions">
          <button onClick={trail.reload}>Refresh</button>
          <button onClick={exportCsv} disabled={entries.length === 0}>Download CSV</button>
          <button className="primary" onClick={exportProofBundle} disabled={busy}>
            {busy ? "Exporting…" : "Download proof bundle (JSON)"}
          </button>
        </div>
      </div>
      <p className="muted small">
        The JSON proof bundle is a self-verifying regulator export — independently verifiable offline
        (RFC-6962 inclusion + consistency proofs), no access to QUAICU required.
      </p>

      {error && <ErrorBox message={error} />}

      {trail.loading ? <Loading what="ledger" /> : trail.error ? <ErrorBox message={trail.error} /> : (
        (trail.data?.count ?? 0) === 0 ? <Empty message="No sealed entries for this tenant" /> : (
          <table className="data">
            <thead>
              <tr><th className="num">Seq</th><th>Action type</th><th>Decision</th><th>Approver</th><th>Sealed at</th></tr>
            </thead>
            <tbody>
              {trail.data!.entries.map((e) => (
                <Fragment key={e.ledger_seq}>
                  <tr className="clickable" onClick={() => setExpanded(expanded === e.ledger_seq ? null : e.ledger_seq)}>
                    <td className="num">{e.ledger_seq}</td>
                    <td>{e.action_type}</td>
                    <td><Badge value={e.decision} /></td>
                    <td>{e.approver ?? "—"}</td>
                    <td className="muted">{new Date(e.sealed_at).toLocaleString()}</td>
                  </tr>
                  {expanded === e.ledger_seq && (
                    <tr className="detail-row">
                      <td colSpan={5}>
                        <div className="kv-grid">
                          <span>action_id</span><code>{e.action_id}</code>
                          <span>actor_id</span><code>{e.actor_id}</code>
                          <span>policy_versions</span><code>{e.policy_versions.join(", ") || "—"}</code>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
