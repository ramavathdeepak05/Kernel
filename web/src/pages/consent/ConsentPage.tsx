import { useState, useEffect, useCallback } from "react";
import {
  Shield, FileText, Clock, CheckCircle2, XCircle, AlertTriangle,
  Search, Download, ChevronDown, ChevronUp, BarChart3,
} from "lucide-react";
import { ALISTabs, ALISTabsList, ALISTabsTrigger, ALISTabsContent } from "@/components/ui/alis-tabs";

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
  purple: "#a855f7",
  purpleDim: "rgba(168,85,247,0.12)",
};

const card: React.CSSProperties = {
  background: C.surface,
  border: `1px solid ${C.border}`,
  borderRadius: 12,
  padding: "20px 24px",
};

// ── purpose → display colour ────────────────────────────────────────────────
const PURPOSE_COLORS: Record<string, string> = {
  ADMISSIONS:   C.teal,
  FINANCE:      C.blue,
  ANALYTICS:    C.purple,
  MARKETING:    C.amber,
  THIRD_PARTY:  C.red,
  RESEARCH:     C.green,
  WHATSAPP:     C.green,
  DEFAULT:      C.teal,
};
function purposeColor(p: string) {
  return PURPOSE_COLORS[p] ?? PURPOSE_COLORS.DEFAULT;
}

// ── DSR type colours ────────────────────────────────────────────────────────
const DSR_TYPE_COLORS: Record<string, { color: string; bg: string }> = {
  ACCESS:        { color: C.teal,   bg: C.tealDim   },
  RECTIFICATION: { color: C.amber,  bg: C.amberDim  },
  ERASURE:       { color: C.red,    bg: C.redDim    },
  PORTABILITY:   { color: C.purple, bg: C.purpleDim },
};

function authHeader() {
  return { Authorization: `Bearer ${sessionStorage.getItem("token") ?? ""}` };
}

// ── Consents Tab ───────────────────────────────────────────────────────────
interface ConsentStat {
  purpose: string;
  given: number;
  revoked: number;
  total: number;
  rate: number;
}
interface ConsentEvent {
  purpose: string;
  action: string;
  ts: string | null;
  user_name: string;
  ip_address: string;
}

function ConsentsTab() {
  const [stats, setStats] = useState<ConsentStat[]>([]);
  const [events, setEvents] = useState<ConsentEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    const headers = authHeader();
    Promise.all([
      fetch("/api/v1/consent/admin/stats", { headers }).then(r => r.ok ? r.json() : null),
      fetch("/api/v1/consent/admin/events?limit=50", { headers }).then(r => r.ok ? r.json() : null),
    ]).then(([statsData, eventsData]) => {
      if (statsData?.stats) setStats(statsData.stats);
      if (eventsData?.events) setEvents(eventsData.events);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const totalGiven   = stats.reduce((s, c) => s + c.given,   0);
  const totalRevoked = stats.reduce((s, c) => s + c.revoked, 0);
  const totalRecords = stats.reduce((s, c) => s + c.total,   0);

  const filtered = events.filter(e =>
    search === "" ||
    e.user_name.toLowerCase().includes(search.toLowerCase()) ||
    e.purpose.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) return <div style={{ textAlign: "center", padding: 40, color: C.muted }}>Loading…</div>;

  return (
    <div>
      {/* stat strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginBottom: 24 }}>
        {[
          { label: "Total Consent Records", value: totalRecords.toLocaleString(), icon: <FileText size={20} />, color: C.blue },
          { label: "Active Consents",        value: totalGiven.toLocaleString(),   icon: <CheckCircle2 size={20} />, color: C.teal },
          { label: "Revoked",                value: totalRevoked.toLocaleString(), icon: <XCircle size={20} />,     color: C.red  },
          { label: "Purposes Tracked",       value: String(stats.length || "—"),   icon: <Clock size={20} />,       color: C.amber },
        ].map((s, i) => (
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

      {/* purpose cards */}
      {stats.length > 0 ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 16, marginBottom: 28 }}>
          {stats.map(cat => {
            const col = purposeColor(cat.purpose);
            return (
              <div key={cat.purpose} style={{ ...card }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{cat.purpose.replace(/_/g, " ")}</div>
                </div>
                <div style={{ fontSize: 38, fontWeight: 800, color: col, marginBottom: 8 }}>{cat.rate}%</div>
                <div style={{ height: 6, background: C.surface2, borderRadius: 3, overflow: "hidden", marginBottom: 10 }}>
                  <div style={{ height: "100%", width: `${cat.rate}%`, background: col, borderRadius: 3 }} />
                </div>
                <div style={{ display: "flex", gap: 16 }}>
                  <div style={{ fontSize: 11, color: C.muted }}>
                    <span style={{ color: C.green, fontWeight: 700 }}>{cat.given.toLocaleString()}</span> given
                  </div>
                  <div style={{ fontSize: 11, color: C.muted }}>
                    <span style={{ color: C.red, fontWeight: 700 }}>{cat.revoked}</span> revoked
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p style={{ color: C.muted, fontSize: 13, marginBottom: 28 }}>No consent records found.</p>
      )}

      {/* recent consent events table */}
      <div style={{ ...card, padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "14px 20px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontWeight: 700, fontSize: 13, color: C.text }}>Recent Consent Events</span>
          <div style={{ flex: 1 }} />
          <div style={{ display: "flex", alignItems: "center", gap: 8, background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 8, padding: "6px 12px" }}>
            <Search size={13} color={C.muted} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search…"
              style={{ background: "none", border: "none", outline: "none", color: C.text, fontSize: 12, width: 160 }} />
          </div>
        </div>
        {filtered.length === 0 ? (
          <div style={{ padding: 32, textAlign: "center", color: C.muted, fontSize: 13 }}>No events found.</div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: C.surface2 }}>
                {["User", "Purpose", "Action", "Timestamp", "IP"].map(h => (
                  <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.07em" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((row, i) => (
                <tr key={i} style={{ borderTop: `1px solid ${C.border}`, background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.01)" }}>
                  <td style={{ padding: "10px 16px", fontSize: 13, color: C.text, fontWeight: 500 }}>{row.user_name}</td>
                  <td style={{ padding: "10px 16px", fontSize: 12, color: C.muted }}>{row.purpose.replace(/_/g, " ")}</td>
                  <td style={{ padding: "10px 16px" }}>
                    <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 8px", borderRadius: 4,
                      color: row.action === "GIVEN" ? C.green : C.red,
                      background: row.action === "GIVEN" ? C.greenDim : C.redDim,
                    }}>{row.action}</span>
                  </td>
                  <td style={{ padding: "10px 16px", fontSize: 12, color: C.muted, whiteSpace: "nowrap" }}>
                    {row.ts ? new Date(row.ts).toLocaleString("en-IN", { hour12: false }).replace(",", "") : "—"}
                  </td>
                  <td style={{ padding: "10px 16px", fontSize: 12, color: C.muted, fontFamily: "monospace" }}>{row.ip_address || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ── DSR Tab ────────────────────────────────────────────────────────────────
interface DSRRecord {
  id: string;
  type: string;
  status: string;
  reason: string;
  user_name: string;
  requested_at: string | null;
  due_by: string | null;
  sla_hours_remaining: number | null;
  completed_at: string | null;
  rejected_at: string | null;
  rejection_reason: string;
}

const ASSIGNEES = ["Dr. Priya Nair (DPO)", "Rahul Mishra (IT)", "Sunita Rao (Registrar)", "Karthik Nambiar (Legal)"];

function DSRTab() {
  const [pending, setPending] = useState<DSRRecord[]>([]);
  const [completed, setCompleted] = useState<DSRRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState<string | null>(null);
  const [assignee, setAssignee] = useState("");
  const [priority, setPriority] = useState("NORMAL");
  const [notes, setNotes] = useState("");
  const [completedOpen, setCompletedOpen] = useState(false);

  const load = useCallback(() => {
    const headers = authHeader();
    Promise.all([
      fetch("/api/v1/consent/admin/dsr", { headers }).then(r => r.ok ? r.json() : null),
      fetch("/api/v1/consent/admin/dsr?status=COMPLETED", { headers }).then(r => r.ok ? r.json() : null),
    ]).then(([pendingData, completedData]) => {
      if (pendingData?.requests) setPending(pendingData.requests);
      if (completedData?.requests) setCompleted(completedData.requests);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  function handleSubmit(id: string) {
    // Optimistically remove from pending list
    setPending(s => s.filter(d => d.id !== id));
    setProcessing(null);
    setAssignee(""); setPriority("NORMAL"); setNotes("");
  }

  if (loading) return <div style={{ textAlign: "center", padding: 40, color: C.muted }}>Loading…</div>;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
        <AlertTriangle size={16} color={C.amber} />
        <span style={{ fontSize: 13, color: C.muted }}>DPDP §12 — Data Subject Requests must be resolved within 72 hours of receipt.</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 28 }}>
        {pending.map(dsr => {
          const tc = DSR_TYPE_COLORS[dsr.type] ?? DSR_TYPE_COLORS.ERASURE;
          const isOpen = processing === dsr.id;
          const slaH = dsr.sla_hours_remaining ?? 72;
          const slaColor = slaH < 24 ? C.red : slaH < 48 ? C.amber : C.teal;
          const slaPct = Math.min(100, (slaH / 72) * 100);
          return (
            <div key={dsr.id} style={{ ...card }}>
              <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
                <div style={{ fontFamily: "monospace", fontSize: 12, fontWeight: 700, color: C.teal, width: 140, flexShrink: 0 }}>{dsr.id.slice(0, 18)}…</div>
                <div style={{ flex: 1, fontSize: 14, fontWeight: 600, color: C.text }}>{dsr.user_name}</div>
                <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 4, color: tc.color, background: tc.bg }}>{dsr.type}</span>
                <span style={{ fontSize: 12, color: C.muted }}>
                  {dsr.requested_at ? new Date(dsr.requested_at).toLocaleDateString("en-IN") : "—"}
                </span>
                <button onClick={() => setProcessing(isOpen ? null : dsr.id)} style={{
                  padding: "7px 16px", borderRadius: 8, border: "none", background: C.teal, color: "#fff",
                  fontSize: 12, fontWeight: 600, cursor: "pointer", flexShrink: 0,
                }}>
                  {isOpen ? "Cancel" : "Assign & Process"}
                </button>
              </div>

              <div style={{ marginTop: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                  <span style={{ fontSize: 11, color: C.muted }}>SLA Remaining</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: slaColor }}>{slaH}h</span>
                </div>
                <div style={{ height: 5, background: C.surface2, borderRadius: 3, overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${slaPct}%`, background: slaColor, borderRadius: 3 }} />
                </div>
              </div>

              {isOpen && (
                <div style={{ marginTop: 16, padding: "16px", background: C.surface2, borderRadius: 10, display: "flex", flexDirection: "column", gap: 12 }}>
                  <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                    <div style={{ flex: 1, minWidth: 180 }}>
                      <label style={{ fontSize: 11, color: C.muted, display: "block", marginBottom: 4 }}>Assignee</label>
                      <select value={assignee} onChange={e => setAssignee(e.target.value)} style={{
                        width: "100%", padding: "8px 10px", borderRadius: 7, border: `1px solid ${C.border}`,
                        background: C.surface, color: C.text, fontSize: 13, outline: "none",
                      }}>
                        <option value="">Select assignee…</option>
                        {ASSIGNEES.map(a => <option key={a} value={a}>{a}</option>)}
                      </select>
                    </div>
                    <div style={{ minWidth: 140 }}>
                      <label style={{ fontSize: 11, color: C.muted, display: "block", marginBottom: 4 }}>Priority</label>
                      <select value={priority} onChange={e => setPriority(e.target.value)} style={{
                        width: "100%", padding: "8px 10px", borderRadius: 7, border: `1px solid ${C.border}`,
                        background: C.surface, color: C.text, fontSize: 13, outline: "none",
                      }}>
                        <option value="LOW">Low</option>
                        <option value="NORMAL">Normal</option>
                        <option value="HIGH">High</option>
                        <option value="URGENT">Urgent</option>
                      </select>
                    </div>
                  </div>
                  <div>
                    <label style={{ fontSize: 11, color: C.muted, display: "block", marginBottom: 4 }}>Notes</label>
                    <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={3} placeholder="Processing notes or instructions…"
                      style={{ width: "100%", padding: "8px 10px", borderRadius: 7, border: `1px solid ${C.border}`, background: C.surface, color: C.text, fontSize: 13, outline: "none", resize: "vertical", boxSizing: "border-box" }} />
                  </div>
                  <button onClick={() => handleSubmit(dsr.id)} disabled={!assignee} style={{
                    padding: "8px 20px", borderRadius: 8, border: "none", alignSelf: "flex-start",
                    background: assignee ? C.teal : C.surface, color: assignee ? "#fff" : C.muted,
                    fontSize: 13, fontWeight: 600, cursor: assignee ? "pointer" : "not-allowed",
                  }}>
                    Submit
                  </button>
                </div>
              )}
            </div>
          );
        })}

        {pending.length === 0 && (
          <div style={{ ...card, textAlign: "center", padding: "40px 24px" }}>
            <CheckCircle2 size={36} color={C.teal} style={{ margin: "0 auto 12px" }} />
            <div style={{ color: C.text, fontWeight: 600 }}>All DSR requests processed</div>
          </div>
        )}
      </div>

      {/* completed accordion */}
      <div style={{ ...card, padding: 0, overflow: "hidden" }}>
        <button onClick={() => setCompletedOpen(o => !o)} style={{
          width: "100%", padding: "14px 20px", background: "none", border: "none", cursor: "pointer",
          display: "flex", alignItems: "center", gap: 10, borderBottom: completedOpen ? `1px solid ${C.border}` : "none",
        }}>
          {completedOpen ? <ChevronUp size={16} color={C.muted} /> : <ChevronDown size={16} color={C.muted} />}
          <span style={{ fontWeight: 700, fontSize: 13, color: C.text }}>Completed Requests</span>
          <span style={{ fontSize: 11, color: C.muted, background: C.surface2, padding: "2px 8px", borderRadius: 10 }}>{completed.length}</span>
        </button>
        {completedOpen && (
          completed.length === 0 ? (
            <div style={{ padding: "20px 24px", color: C.muted, fontSize: 13 }}>No completed requests.</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: C.surface2 }}>
                  {["Request ID", "User", "Type", "Resolved"].map(h => (
                    <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.07em" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {completed.map((r, i) => {
                  const tc = DSR_TYPE_COLORS[r.type] ?? DSR_TYPE_COLORS.ERASURE;
                  return (
                    <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
                      <td style={{ padding: "10px 16px", fontFamily: "monospace", fontSize: 12, color: C.teal }}>{r.id.slice(0, 18)}…</td>
                      <td style={{ padding: "10px 16px", fontSize: 13, color: C.text }}>{r.user_name}</td>
                      <td style={{ padding: "10px 16px" }}>
                        <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 4, color: tc.color, background: tc.bg }}>{r.type}</span>
                      </td>
                      <td style={{ padding: "10px 16px", fontSize: 12, color: C.muted }}>
                        {r.completed_at ? new Date(r.completed_at).toLocaleDateString("en-IN") : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )
        )}
      </div>
    </div>
  );
}

// ── Audit Log Tab ──────────────────────────────────────────────────────────
interface AuditLogEntry {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  actor_role: string;
  metadata: Record<string, unknown>;
  timestamp: string;
}

interface AuditRow {
  ts: string;
  student: string;
  action: string;
  purpose: string;
  channel: string;
  ip: string;
  officer: string;
}

function AuditLogTab() {
  const [toast, setToast] = useState(false);
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = sessionStorage.getItem("token") ?? "";
    fetch("/api/v1/audit/logs?entity_type=consent&limit=50", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() as Promise<{ logs?: AuditLogEntry[] }> : null)
      .then(data => {
        const logs = data?.logs ?? [];
        setRows(logs.map(l => ({
          ts: new Date(l.timestamp).toLocaleString("en-IN", { hour12: false }).replace(",", ""),
          student: String(l.metadata?.student_name ?? l.metadata?.user_name ?? l.entity_id ?? "—"),
          action: l.action.toUpperCase() === "CREATE" ? "GIVEN" : l.action.toUpperCase() === "DELETE" ? "REVOKED" : l.action.toUpperCase(),
          purpose: String(l.metadata?.purpose ?? l.entity_type ?? "—"),
          channel: String(l.metadata?.channel ?? "System"),
          ip: String(l.metadata?.ip_address ?? "—"),
          officer: String(l.metadata?.actor_name ?? l.actor_role ?? "—"),
        })));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  function handleExport() {
    setToast(true);
    setTimeout(() => setToast(false), 2000);
  }

  return (
    <div style={{ position: "relative" }}>
      {toast && (
        <div style={{
          position: "fixed", bottom: 32, right: 32, background: C.teal, color: "#fff",
          padding: "12px 24px", borderRadius: 10, fontWeight: 700, fontSize: 14,
          boxShadow: "0 8px 32px rgba(29,158,117,0.4)", zIndex: 1000,
        }}>
          Exported!
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
        <button onClick={handleExport} style={{
          display: "flex", alignItems: "center", gap: 8, padding: "8px 18px", borderRadius: 8,
          border: `1px solid ${C.border}`, background: C.surface2, color: C.text, fontSize: 13, fontWeight: 600, cursor: "pointer",
        }}>
          <Download size={14} color={C.teal} /> Export CSV
        </button>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: 40, color: C.muted }}>Loading audit log…</div>
      ) : rows.length === 0 ? (
        <div style={{ textAlign: "center", padding: 40, color: C.muted, fontSize: 13 }}>No consent audit entries found.</div>
      ) : (
        <div style={{ ...card, padding: 0, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: C.surface2 }}>
                {["Timestamp", "User", "Action", "Purpose", "Channel", "IP Address", "Officer"].map(h => (
                  <th key={h} style={{ padding: "11px 14px", textAlign: "left", fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.07em", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} style={{ borderTop: `1px solid ${C.border}`, background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.01)" }}>
                  <td style={{ padding: "9px 14px", fontSize: 11, color: C.muted, whiteSpace: "nowrap", fontFamily: "monospace" }}>{row.ts}</td>
                  <td style={{ padding: "9px 14px", fontSize: 12, color: C.text, whiteSpace: "nowrap" }}>{row.student}</td>
                  <td style={{ padding: "9px 14px" }}>
                    <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 4,
                      color: row.action === "GIVEN" ? C.green : C.red,
                      background: row.action === "GIVEN" ? C.greenDim : C.redDim,
                    }}>{row.action}</span>
                  </td>
                  <td style={{ padding: "9px 14px", fontSize: 11, color: C.muted, maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.purpose}</td>
                  <td style={{ padding: "9px 14px", fontSize: 11, color: C.muted }}>{row.channel}</td>
                  <td style={{ padding: "9px 14px", fontSize: 11, color: C.muted, fontFamily: "monospace" }}>{row.ip}</td>
                  <td style={{ padding: "9px 14px", fontSize: 11, color: C.muted }}>{row.officer}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────
type Tab = "consents" | "dsr" | "audit";

export function ConsentPage() {
  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "consents", label: "Consents",     icon: <Shield size={14} /> },
    { id: "dsr",      label: "DSR Requests", icon: <FileText size={14} /> },
    { id: "audit",    label: "Audit Log",    icon: <BarChart3 size={14} /> },
  ];

  return (
    <div style={{ minHeight: "100vh", background: C.bg, padding: "32px 40px", fontFamily: "Inter, system-ui, sans-serif" }}>
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
          <Shield size={22} color={C.teal} />
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: C.text }}>Consent Management</h1>
          <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 6, background: C.tealDim, color: C.teal }}>DPDP 2023</span>
        </div>
        <p style={{ margin: 0, fontSize: 13, color: C.muted }}>Manage student consents, data subject requests (DSR), and maintain a full consent audit trail.</p>
      </div>

      <ALISTabs defaultValue="consents">
        <ALISTabsList>
          {tabs.map(t => (
            <ALISTabsTrigger key={t.id} value={t.id}>{t.icon} {t.label}</ALISTabsTrigger>
          ))}
        </ALISTabsList>
        <ALISTabsContent value="consents"><ConsentsTab /></ALISTabsContent>
        <ALISTabsContent value="dsr"><DSRTab /></ALISTabsContent>
        <ALISTabsContent value="audit"><AuditLogTab /></ALISTabsContent>
      </ALISTabs>
    </div>
  );
}
