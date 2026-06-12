import { useState } from "react";
import { api, ApiError } from "../api/client";
import { Empty, ErrorBox, Loading, useApi } from "../components";

export default function Approvals() {
  const pending = useApi(() => api.listApprovals(), []);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function decide(handleId: string, kind: "approve" | "reject") {
    setBusy(handleId);
    setActionError(null);
    try {
      await (kind === "approve" ? api.approve(handleId) : api.reject(handleId));
      pending.reload();
    } catch (e) {
      setActionError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>HITL approvals</h1>
        <button onClick={pending.reload}>Refresh</button>
      </div>
      <p className="muted note">
        Approve/reject is gated by the kernel: only an eligible approver may decide, and the proposer
        cannot approve their own action.
      </p>

      {actionError && <ErrorBox message={actionError} />}

      {pending.loading ? <Loading what="queue" /> : pending.error ? <ErrorBox message={pending.error} /> : (
        (pending.data?.count ?? 0) === 0 ? <Empty message="No pending approvals" /> : (
          <table className="data">
            <thead>
              <tr><th>Action</th><th>Required approvers</th><th>Proposed by</th><th>Requested</th><th></th></tr>
            </thead>
            <tbody>
              {pending.data!.approvals.map((a) => (
                <tr key={a.handle_id}>
                  <td><code>{a.action_id}</code></td>
                  <td>{a.required_approvers.join(", ")}</td>
                  <td>{a.proposed_by ?? "—"}</td>
                  <td className="muted">{new Date(a.requested_at).toLocaleString()}</td>
                  <td className="actions">
                    <button className="primary" disabled={busy === a.handle_id} onClick={() => decide(a.handle_id, "approve")}>Approve</button>
                    <button className="danger" disabled={busy === a.handle_id} onClick={() => decide(a.handle_id, "reject")}>Reject</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
