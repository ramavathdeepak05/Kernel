import { useState, useEffect, useCallback } from "react";
import {
  Clock, CheckCircle2, AlertTriangle, Users, Search,
  RotateCcw, ThumbsUp, ThumbsDown, ArrowUp,
  CalendarCheck, Shield, Loader2,
} from "lucide-react";

// ── theme ──────────────────────────────────────────────────────────────────
const C = {
  bg: "#0f172a",
  surface: "#1e293b",
  surface2: "#253047",
  border: "rgba(255,255,255,0.06)",
  teal: "#1D9E75",
  tealDim: "rgba(29,158,117,0.15)",
  text: "#f1f5f9",
  muted: "#94a3b8",
  red: "#ef4444",
  redDim: "rgba(239,68,68,0.15)",
  amber: "#f59e0b",
  amberDim: "rgba(245,158,11,0.15)",
  green: "#22c55e",
  greenDim: "rgba(34,197,94,0.12)",
  blue: "#3b82f6",
  blueDim: "rgba(59,130,246,0.12)",
};

const card: React.CSSProperties = {
  background: C.surface,
  border: `1px solid ${C.border}`,
  borderRadius: 12,
  padding: "20px 24px",
};

// ── Types ──────────────────────────────────────────────────────────────────

interface ApprovalAction {
  id: string;
  actor_id: string;
  actor_role: string;
  action: "approve" | "reject";
  comment: string | null;
  acted_at: string;
}

interface ApprovalRequest {
  id: string;
  entity_type: string;
  entity_id: string;
  action_type: string;
  config_id: string;
  status: string;
  requested_by: string;
  required_roles: string[];
  mode: "single" | "any" | "all";
  required_count: number;
  resolved_at: string | null;
  resolution_reason: string | null;
  context: Record<string, unknown>;
  created_at: string;
  actions?: ApprovalAction[];
}

// ── API Helpers ────────────────────────────────────────────────────────────

const BASE = "/api/approvals";

async function getApprovals(path = "", params?: Record<string, string>) {
  const token = localStorage.getItem("token") ?? "";
  const qs = params ? "?" + new URLSearchParams(params) : "";
  const res = await fetch(`${BASE}${path}${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function postApproval(path: string, body: unknown) {
  const token = localStorage.getItem("token") ?? "";
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── Utility ────────────────────────────────────────────────────────────────

function ageHours(iso: string): number {
  return (Date.now() - new Date(iso).getTime()) / 3_600_000;
}

function relativeTime(iso: string): string {
  const h = ageHours(iso);
  if (h < 1) return `${Math.floor(h * 60)}m ago`;
  if (h < 24) return `${Math.floor(h)}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatDuration(start: string, end: string | null): string {
  if (!end) return "—";
  const h = (new Date(end).getTime() - new Date(start).getTime()) / 3_600_000;
  return `${h.toFixed(1)}h`;
}

function actionDot(type: string): string {
  const t = type.toUpperCase();
  if (t.includes("FEE") || t.includes("WAIVER") || t.includes("SCHOLAR")) return C.amber;
  if (t.includes("OFFER") || t.includes("ENROLL") || t.includes("HOSTEL") || t.includes("ADMIT")) return C.teal;
  if (t.includes("GRADE") || t.includes("OVERRIDE") || t.includes("REEVAL")) return C.red;
  return C.blue;
}

const ROLE_LABEL: Record<string, string> = {
  hod: "HOD", dean: "Dean", registrar: "Registrar",
  finance_officer: "Finance", hr_admin: "HR",
  admin: "Admin", super_admin: "Super Admin",
};

function roleLabel(r: string): string {
  return ROLE_LABEL[r] ?? r.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function studentLabel(r: ApprovalRequest): string {
  return String(r.context.student_name ?? r.context.name ?? r.entity_id);
}

function descLabel(r: ApprovalRequest): string {
  return String(
    r.context.description ?? r.context.reason ?? r.context.notes ??
    `${r.action_type.replace(/_/g, " ")} approval requested`,
  );
}

// ── sub-components ─────────────────────────────────────────────────────────

function StatStrip({ items }: { items: { label: string; value: string | number; icon: React.ReactNode; color: string }[] }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginBottom: 24 }}>
      {items.map((s, i) => (
        <div key={i} style={{ ...card, display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ width: 44, height: 44, borderRadius: 10, background: `${s.color}1a`, display: "flex", alignItems: "center", justifyContent: "center", color: s.color, flexShrink: 0 }}>
            {s.icon}
          </div>
          <div>
            <div style={{ fontSize: 22, fontWeight: 700, color: C.text }}>{s.value}</div>
            <div style={{ fontSize: 12, color: C.muted, marginTop: 2 }}>{s.label}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function BadgePill({ label, color, bg }: { label: string; color: string; bg: string }) {
  return (
    <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", color, background: bg, padding: "3px 8px", borderRadius: 4, whiteSpace: "nowrap" }}>
      {label}
    </span>
  );
}

function LoadingPane({ label }: { label: string }) {
  return (
    <div style={{ textAlign: "center", padding: "64px 24px" }}>
      <Loader2 size={28} color={C.teal} style={{ margin: "0 auto 12px", display: "block" }} />
      <div style={{ color: C.muted, fontSize: 13 }}>{label}</div>
    </div>
  );
}

function EmptyPane({ icon, title, sub }: { icon: React.ReactNode; title: string; sub: string }) {
  return (
    <div style={{ ...card, textAlign: "center", padding: "48px 24px" }}>
      <div style={{ margin: "0 auto 12px", display: "flex", justifyContent: "center" }}>{icon}</div>
      <div style={{ color: C.text, fontWeight: 600, fontSize: 16 }}>{title}</div>
      <div style={{ color: C.muted, fontSize: 13, marginTop: 6 }}>{sub}</div>
    </div>
  );
}

// ── Queue Tab ──────────────────────────────────────────────────────────────

interface QueueTabProps {
  items: ApprovalRequest[];
  escalatedCount: number;
  resolvedToday: number;
  loading: boolean;
  onAction: (id: string, action: "approve" | "reject") => Promise<void>;
}

const ROLE_FILTERS = ["All", "hod", "dean", "registrar", "finance_officer", "hr_admin"];

function QueueTab({ items, escalatedCount, resolvedToday, loading, onAction }: QueueTabProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [roleFilter, setRoleFilter] = useState("All");
  const [search, setSearch] = useState("");

  async function handleAction(id: string, action: "approve" | "reject") {
    setBusy(id + action);
    try {
      await onAction(id, action);
      setFlash(id + action);
      setTimeout(() => setFlash(null), 800);
    } catch {
      // no-op — parent handles error toast
    } finally {
      setBusy(null);
    }
  }

  const avgWait = items.length > 0
    ? `${(items.reduce((s, r) => s + ageHours(r.created_at), 0) / items.length).toFixed(1)}h`
    : "—";

  const visible = items.filter(r =>
    (roleFilter === "All" || r.required_roles.includes(roleFilter)) &&
    (search === "" ||
      studentLabel(r).toLowerCase().includes(search.toLowerCase()) ||
      r.action_type.toLowerCase().includes(search.toLowerCase())),
  );

  return (
    <div>
      <StatStrip items={[
        { label: "Pending Approvals", value: items.length, icon: <Clock size={20} />, color: C.amber },
        { label: "Avg Wait", value: avgWait, icon: <RotateCcw size={20} />, color: C.blue },
        { label: "Escalated", value: escalatedCount, icon: <ArrowUp size={20} />, color: C.red },
        { label: "Resolved Today", value: resolvedToday, icon: <CheckCircle2 size={20} />, color: C.teal },
      ]} />

      <div style={{ display: "flex", gap: 12, marginBottom: 20, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {ROLE_FILTERS.map(r => (
            <button key={r} onClick={() => setRoleFilter(r)} style={{
              padding: "6px 14px", borderRadius: 20, fontSize: 12, fontWeight: 600, cursor: "pointer", border: "none",
              background: roleFilter === r ? C.teal : C.surface2,
              color: roleFilter === r ? "#fff" : C.muted,
              transition: "all 0.15s",
            }}>
              {r === "All" ? "All" : roleLabel(r)}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 8, padding: "6px 12px", flex: 1, maxWidth: 320 }}>
          <Search size={14} color={C.muted} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search entity or event type…"
            style={{ background: "none", border: "none", outline: "none", color: C.text, fontSize: 13, flex: 1 }}
          />
        </div>
      </div>

      {loading
        ? <LoadingPane label="Loading approval queue…" />
        : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {visible.length === 0 && (
              <EmptyPane
                icon={<CheckCircle2 size={40} color={C.teal} />}
                title="All caught up!"
                sub="No pending approvals in this queue."
              />
            )}
            {visible.map(row => {
              const dot = actionDot(row.action_type);
              const isFlashing = flash?.startsWith(row.id) ?? false;
              const inProgress = busy?.startsWith(row.id) ?? false;
              return (
                <div key={row.id} style={{
                  ...card, display: "flex", alignItems: "center", gap: 16, padding: "14px 20px",
                  opacity: isFlashing || inProgress ? 0.5 : 1, transition: "opacity 0.3s",
                  position: "relative", overflow: "hidden",
                }}>
                  {isFlashing && (
                    <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(29,158,117,0.08)", fontSize: 18, fontWeight: 700, color: C.teal }}>
                      ✓ Done
                    </div>
                  )}
                  <div style={{ width: 10, height: 10, borderRadius: "50%", background: dot, flexShrink: 0 }} />
                  <BadgePill label={row.action_type.replace(/_/g, " ")} color={dot} bg={`${dot}22`} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                      <span style={{ fontWeight: 600, color: C.text, fontSize: 14 }}>{studentLabel(row)}</span>
                      <span style={{ fontSize: 11, color: C.muted, background: C.surface2, padding: "2px 8px", borderRadius: 4 }}>
                        {row.required_roles.map(roleLabel).join(", ")}
                      </span>
                      <span style={{ fontSize: 11, color: C.muted }}>{relativeTime(row.created_at)}</span>
                    </div>
                    <div style={{ fontSize: 12, color: C.muted, marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {descLabel(row)}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
                    <button
                      onClick={() => handleAction(row.id, "approve")}
                      disabled={inProgress}
                      style={{
                        padding: "7px 16px", borderRadius: 8, border: "none", background: C.teal, color: "#fff",
                        fontSize: 12, fontWeight: 600, cursor: inProgress ? "not-allowed" : "pointer",
                        display: "flex", alignItems: "center", gap: 6, opacity: inProgress ? 0.6 : 1,
                      }}
                    >
                      <ThumbsUp size={12} /> Approve
                    </button>
                    <button
                      onClick={() => handleAction(row.id, "reject")}
                      disabled={inProgress}
                      style={{
                        padding: "7px 16px", borderRadius: 8, border: `1px solid ${C.red}55`, background: C.redDim, color: C.red,
                        fontSize: 12, fontWeight: 600, cursor: inProgress ? "not-allowed" : "pointer",
                        display: "flex", alignItems: "center", gap: 6, opacity: inProgress ? 0.6 : 1,
                      }}
                    >
                      <ThumbsDown size={12} /> Reject
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
    </div>
  );
}

// ── Escalations Tab ─────────────────────────────────────────────────────────

interface EscalationsTabProps {
  items: ApprovalRequest[];
  loading: boolean;
  onForceResolve: (id: string) => Promise<void>;
}

function EscalationsTab({ items, loading, onForceResolve }: EscalationsTabProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [resolved, setResolved] = useState<Set<string>>(new Set());

  async function handleForceResolve(id: string) {
    setBusy(id);
    try {
      await onForceResolve(id);
      setResolved(prev => new Set([...prev, id]));
    } catch {
      // no-op
    } finally {
      setBusy(null);
    }
  }

  const visible = items.filter(e => !resolved.has(e.id));

  if (loading) return <LoadingPane label="Loading escalations…" />;

  if (visible.length === 0) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <EmptyPane
          icon={<Shield size={36} color={C.teal} />}
          title="No active escalations"
          sub="All approval requests are within SLA."
        />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {visible.map(e => {
        const overdueMins = Math.floor((ageHours(e.created_at) - 24) * 60);
        const overduePct = Math.min(100, (overdueMins / 240) * 100);
        const isBusy = busy === e.id;

        return (
          <div key={e.id} style={{ ...card }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                  <AlertTriangle size={16} color={C.red} />
                  <span style={{ fontWeight: 700, color: C.text, fontSize: 15 }}>
                    {e.action_type.replace(/_/g, " ")} — {studentLabel(e)}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: C.muted }}>
                  <span style={{ color: C.amber }}>Reason:</span> SLA breach — pending for {Math.floor(ageHours(e.created_at))}h (limit: 24h)
                </div>
              </div>
              <span style={{ fontSize: 11, color: C.muted }}>{relativeTime(e.created_at)}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
              <div style={{ background: C.surface2, borderRadius: 8, padding: "10px 14px" }}>
                <div style={{ fontSize: 10, color: C.muted, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.08em" }}>Required Approver</div>
                <div style={{ fontSize: 13, color: C.text }}>{e.required_roles.map(roleLabel).join(", ")}</div>
              </div>
              <div style={{ background: C.surface2, borderRadius: 8, padding: "10px 14px" }}>
                <div style={{ fontSize: 10, color: C.muted, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.08em" }}>Escalated To</div>
                <div style={{ fontSize: 13, color: C.teal }}>Admin Review</div>
              </div>
            </div>
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span style={{ fontSize: 11, color: C.muted }}>SLA Overdue</span>
                <span style={{ fontSize: 11, fontWeight: 700, color: C.red }}>
                  +{overdueMins < 60 ? `${overdueMins}m` : `${Math.floor(overdueMins / 60)}h ${overdueMins % 60}m`}
                </span>
              </div>
              <div style={{ height: 6, background: C.surface2, borderRadius: 3, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${overduePct}%`, background: C.red, borderRadius: 3 }} />
              </div>
            </div>
            <button
              onClick={() => handleForceResolve(e.id)}
              disabled={isBusy}
              style={{
                padding: "8px 18px", borderRadius: 8, border: `1px solid ${C.red}55`, background: C.redDim,
                color: C.red, fontSize: 12, fontWeight: 600, cursor: isBusy ? "not-allowed" : "pointer",
                opacity: isBusy ? 0.6 : 1,
              }}
            >
              {isBusy ? "Resolving…" : "Force Resolve"}
            </button>
          </div>
        );
      })}
    </div>
  );
}

// ── Quorum Tab ──────────────────────────────────────────────────────────────

interface QuorumTabProps {
  items: ApprovalRequest[];
  currentUserId: string | undefined;
  loading: boolean;
  onVote: (id: string) => Promise<void>;
}

function QuorumTab({ items, currentUserId, loading, onVote }: QuorumTabProps) {
  const [voting, setVoting] = useState<string | null>(null);
  const [voted, setVoted] = useState<Set<string>>(new Set());

  if (loading) return <LoadingPane label="Loading quorum decisions…" />;

  if (items.length === 0) {
    return (
      <EmptyPane
        icon={<Users size={36} color={C.teal} />}
        title="No quorum decisions pending"
        sub="All multi-approver requests have been resolved."
      />
    );
  }

  async function castVote(id: string) {
    setVoting(id);
    try {
      await onVote(id);
      setVoted(prev => new Set([...prev, id]));
    } catch {
      // no-op
    } finally {
      setVoting(null);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {items.map(q => {
        const actions = q.actions ?? [];
        const approveActions = actions.filter(a => a.action === "approve");
        const approvedRoles = new Set(approveActions.map(a => a.actor_role));
        const voteCount = approveActions.length;
        const allApproved = voteCount >= q.required_count;
        const pct = (voteCount / Math.max(q.required_count, 1)) * 100;
        const hasVoted = voted.has(q.id) || (!!currentUserId && actions.some(a => a.actor_id === currentUserId));
        const isVoting = voting === q.id;

        return (
          <div key={q.id} style={{ ...card }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
              <div style={{ fontWeight: 700, color: C.text, fontSize: 15 }}>
                {String(q.context.title ?? `${q.action_type.replace(/_/g, " ")} — ${q.entity_id}`)}
              </div>
              <span style={{ fontSize: 13, fontWeight: 700, color: allApproved ? C.teal : C.amber }}>
                {voteCount}/{q.required_count} approved
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
              {q.required_roles.map((role, i) => {
                const hasRoleVoted = approvedRoles.has(role);
                return (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{ width: 20, height: 20, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", background: hasRoleVoted ? C.greenDim : C.surface2, border: `1px solid ${hasRoleVoted ? C.green : C.border}` }}>
                      {hasRoleVoted
                        ? <CheckCircle2 size={12} color={C.green} />
                        : <Clock size={10} color={C.muted} />}
                    </div>
                    <span style={{ fontSize: 13, color: hasRoleVoted ? C.text : C.muted }}>{roleLabel(role)}</span>
                    {hasRoleVoted && (
                      <span style={{ fontSize: 10, color: C.green, background: C.greenDim, padding: "2px 6px", borderRadius: 4 }}>VOTED</span>
                    )}
                  </div>
                );
              })}
            </div>
            <div style={{ marginBottom: 16 }}>
              <div style={{ height: 8, background: C.surface2, borderRadius: 4, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${Math.min(100, pct)}%`, background: allApproved ? C.teal : C.amber, borderRadius: 4, transition: "width 0.4s" }} />
              </div>
            </div>
            <button
              onClick={() => !hasVoted && !allApproved && castVote(q.id)}
              disabled={hasVoted || allApproved || isVoting}
              style={{
                padding: "8px 20px", borderRadius: 8, border: "none",
                cursor: hasVoted || allApproved || isVoting ? "default" : "pointer",
                background: hasVoted || allApproved ? C.surface2 : C.teal,
                color: hasVoted || allApproved ? C.muted : "#fff",
                fontSize: 13, fontWeight: 600,
              }}
            >
              {allApproved ? "✓ Quorum Reached" : hasVoted ? "Vote Recorded" : isVoting ? "Recording…" : "Cast Your Vote"}
            </button>
          </div>
        );
      })}
    </div>
  );
}

// ── History Tab ─────────────────────────────────────────────────────────────

interface HistoryTabProps {
  items: ApprovalRequest[];
  loading: boolean;
}

function HistoryTab({ items, loading }: HistoryTabProps) {
  const outcomeCfg: Record<string, { color: string; bg: string }> = {
    APPROVED: { color: C.green, bg: C.greenDim },
    REJECTED: { color: C.red, bg: C.redDim },
  };

  if (loading) return <LoadingPane label="Loading history…" />;

  if (items.length === 0) {
    return (
      <EmptyPane
        icon={<CalendarCheck size={36} color={C.teal} />}
        title="No history yet"
        sub="Resolved approvals will appear here."
      />
    );
  }

  return (
    <div style={{ ...card, padding: 0, overflow: "hidden" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: C.surface2, borderBottom: `1px solid ${C.border}` }}>
            {["Date", "Event", "Entity", "Resolution", "Outcome", "Duration"].map(h => (
              <th key={h} style={{ padding: "12px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.07em" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((row, i) => {
            const oc = outcomeCfg[row.status] ?? { color: C.muted, bg: C.surface2 };
            const dateStr = new Date(row.resolved_at ?? row.created_at).toLocaleString("en-IN", {
              month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
            });
            return (
              <tr key={row.id} style={{ borderBottom: `1px solid ${C.border}`, background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.01)" }}>
                <td style={{ padding: "12px 16px", fontSize: 12, color: C.muted, whiteSpace: "nowrap" }}>{dateStr}</td>
                <td style={{ padding: "12px 16px" }}>
                  <BadgePill label={row.action_type.replace(/_/g, " ")} color={C.blue} bg={C.blueDim} />
                </td>
                <td style={{ padding: "12px 16px", fontSize: 13, color: C.text }}>{studentLabel(row)}</td>
                <td style={{ padding: "12px 16px", fontSize: 12, color: C.muted }}>
                  {String(row.context.approved_by ?? row.required_roles.map(roleLabel).join(", "))}
                </td>
                <td style={{ padding: "12px 16px" }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: oc.color, background: oc.bg, padding: "3px 8px", borderRadius: 4 }}>{row.status}</span>
                </td>
                <td style={{ padding: "12px 16px", fontSize: 12, color: C.muted }}>
                  {formatDuration(row.created_at, row.resolved_at)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Page ────────────────────────────────────────────────────────────────────

type Tab = "queue" | "escalations" | "quorum" | "history";

export function WorkflowsPage() {
  const [tab, setTab] = useState<Tab>("queue");
  const [pending, setPending] = useState<ApprovalRequest[]>([]);
  const [quorumDetails, setQuorumDetails] = useState<ApprovalRequest[]>([]);
  const [history, setHistory] = useState<ApprovalRequest[]>([]);
  const [loadingPending, setLoadingPending] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(true);

  const currentUserId: string | undefined = (() => {
    try {
      const u = localStorage.getItem("user");
      return u ? JSON.parse(u).id : undefined;
    } catch { return undefined; }
  })();

  const loadPending = useCallback(async () => {
    setLoadingPending(true);
    try {
      const data = await getApprovals("/pending") as { pending: ApprovalRequest[] };
      const items = data.pending ?? [];
      setPending(items);

      // Load quorum item details (with actions) — typically ≤5 items
      const quorumItems = items.filter(r => r.mode !== "single");
      if (quorumItems.length > 0) {
        const details = await Promise.all(
          quorumItems.map(r => getApprovals(`/${r.id}`) as Promise<ApprovalRequest>),
        );
        setQuorumDetails(details);
      } else {
        setQuorumDetails([]);
      }
    } catch {
      setPending([]);
      setQuorumDetails([]);
    } finally {
      setLoadingPending(false);
    }
  }, []);

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const [approved, rejected] = await Promise.all([
        getApprovals("", { status: "APPROVED", limit: "25" }) as Promise<{ requests: ApprovalRequest[] }>,
        getApprovals("", { status: "REJECTED", limit: "25" }) as Promise<{ requests: ApprovalRequest[] }>,
      ]);
      const combined = [
        ...(approved.requests ?? []),
        ...(rejected.requests ?? []),
      ].sort(
        (a, b) =>
          new Date(b.resolved_at ?? b.created_at).getTime() -
          new Date(a.resolved_at ?? a.created_at).getTime(),
      );
      setHistory(combined.slice(0, 50));
    } catch {
      setHistory([]);
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    loadPending();
    loadHistory();
  }, [loadPending, loadHistory]);

  const handleAction = async (id: string, action: "approve" | "reject") => {
    await postApproval(`/${id}/${action}`, { comment: "" });
    await loadPending();
  };

  // Derived data splits
  const singleItems = pending.filter(r => r.mode === "single");
  const escalatedItems = pending.filter(r => ageHours(r.created_at) > 24);
  const resolvedToday = history.filter(r =>
    r.resolved_at && ageHours(r.resolved_at) < 24,
  ).length;

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "queue",       label: "Queue",       icon: <Clock size={14} /> },
    { id: "escalations", label: "Escalations", icon: <AlertTriangle size={14} /> },
    { id: "quorum",      label: "Quorum",      icon: <Users size={14} /> },
    { id: "history",     label: "History",     icon: <CalendarCheck size={14} /> },
  ];

  return (
    <div style={{ minHeight: "100vh", background: C.bg, padding: "32px 40px", fontFamily: "Inter, system-ui, sans-serif" }}>
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
          <Shield size={22} color={C.teal} />
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: C.text }}>Approval Workflows</h1>
        </div>
        <p style={{ margin: 0, fontSize: 13, color: C.muted }}>Manage pending approvals, escalations, quorum decisions, and review history.</p>
      </div>

      <div style={{ display: "flex", gap: 4, marginBottom: 28, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: 4, width: "fit-content" }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            display: "flex", alignItems: "center", gap: 7, padding: "8px 18px", borderRadius: 7, border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600, transition: "all 0.15s",
            background: tab === t.id ? C.teal : "transparent",
            color: tab === t.id ? "#fff" : C.muted,
          }}>
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      {tab === "queue" && (
        <QueueTab
          items={singleItems}
          escalatedCount={escalatedItems.length}
          resolvedToday={resolvedToday}
          loading={loadingPending}
          onAction={handleAction}
        />
      )}
      {tab === "escalations" && (
        <EscalationsTab
          items={escalatedItems}
          loading={loadingPending}
          onForceResolve={id => handleAction(id, "reject")}
        />
      )}
      {tab === "quorum" && (
        <QuorumTab
          items={quorumDetails}
          currentUserId={currentUserId}
          loading={loadingPending}
          onVote={id => handleAction(id, "approve")}
        />
      )}
      {tab === "history" && (
        <HistoryTab
          items={history}
          loading={loadingHistory}
        />
      )}
    </div>
  );
}
