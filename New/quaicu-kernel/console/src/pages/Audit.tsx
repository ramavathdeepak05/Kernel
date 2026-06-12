import { Fragment, useState } from "react";
import { api } from "../api/client";
import { Badge, Empty, ErrorBox, Loading, useApi } from "../components";

export default function Audit() {
  const trail = useApi(() => api.ledgerTrail(), []);
  const [expanded, setExpanded] = useState<number | null>(null);

  return (
    <div className="page">
      <div className="page-head">
        <h1>Audit trail</h1>
        <button onClick={trail.reload}>Refresh</button>
      </div>

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
