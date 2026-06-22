import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Badge, Card, Empty, ErrorBox, Loading, Stat, useApi } from "../components";

export default function Dashboard() {
  const overview = useApi(() => api.overview(), []);
  const timeline = useApi(() => api.decisions(14), []);
  const top = useApi(() => api.topActions(8), []);
  const queue = useApi(() => api.hitlQueue(), []);

  // First-run nudge: a brand-new tenant has governed nothing yet — send them to the try-it page
  // instead of staring at empty charts.
  const noActivity = overview.data?.total_governed === 0;

  return (
    <div className="page">
      <h1>Governance dashboard</h1>

      {noActivity && (
        <div className="card getstarted-callout">
          <div className="card-body">
            <strong>No governed actions yet.</strong>{" "}
            <span className="muted">
              Run your first governed decision and see it sealed to the ledger.
            </span>
            <Link className="primary small callout-cta" to="/start">Get started →</Link>
          </div>
        </div>
      )}

      <div className="grid-4">
        <Card title="Overview">
          {overview.loading ? <Loading /> : overview.error ? <ErrorBox message={overview.error} /> : overview.data && (
            <div className="stats">
              <Stat label="Governed actions" value={overview.data.total_governed} />
              <Stat label="Denial rate" value={`${(overview.data.denial_rate * 100).toFixed(1)}%`} />
              <Stat label="Last ledger seq" value={overview.data.last_ledger_seq ?? "—"} />
            </div>
          )}
        </Card>

        <Card title="HITL queue">
          {queue.loading ? <Loading /> : queue.error ? <ErrorBox message={queue.error} /> : (
            <Stat label="Pending approvals" value={queue.data?.pending ?? 0} />
          )}
        </Card>

        <Card title="Decision mix">
          {overview.data && (
            <table className="kv">
              <tbody>
                {Object.entries(overview.data.decision_counts).map(([k, v]) => (
                  <tr key={k}><td><Badge value={k} /></td><td className="num">{v}</td></tr>
                ))}
                {Object.keys(overview.data.decision_counts).length === 0 && (
                  <tr><td colSpan={2}><Empty message="No decisions sealed yet" /></td></tr>
                )}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <Card title="Decisions — last 14 days">
        {timeline.loading ? <Loading /> : timeline.error ? <ErrorBox message={timeline.error} /> : (
          (timeline.data?.buckets.length ?? 0) === 0 ? <Empty message="No activity in window" /> : (
            <div className="timeline">
              {timeline.data!.buckets.map((b) => (
                <div className="tl-row" key={b.date}>
                  <span className="tl-date">{b.date}</span>
                  <span className="tl-bar">
                    {Object.entries(b.decision_counts).map(([d, n]) => (
                      <span key={d} className={`tl-seg badge-${d}`} style={{ flexGrow: n }} title={`${d}: ${n}`} />
                    ))}
                  </span>
                  <span className="tl-total num">{b.total}</span>
                </div>
              ))}
            </div>
          )
        )}
      </Card>

      <Card title="Top action types">
        {top.loading ? <Loading /> : top.error ? <ErrorBox message={top.error} /> : (
          <table className="data">
            <thead><tr><th>Action type</th><th className="num">Volume</th><th className="num">Denials</th></tr></thead>
            <tbody>
              {top.data?.by_volume.map((a) => (
                <tr key={a.action_type}>
                  <td>{a.action_type}</td>
                  <td className="num">{a.total}</td>
                  <td className="num">{a.denials}</td>
                </tr>
              ))}
              {(top.data?.by_volume.length ?? 0) === 0 && (
                <tr><td colSpan={3}><Empty message="No actions yet" /></td></tr>
              )}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
