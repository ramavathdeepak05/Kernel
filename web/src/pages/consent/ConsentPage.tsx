import { useState, useEffect } from "react";
import {
  Shield, FileText, Clock, CheckCircle2, XCircle, AlertTriangle,
  Search, Download, ChevronDown, ChevronUp, X, Users, BarChart3,
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
  purple: "#a855f7",
  purpleDim: "rgba(168,85,247,0.12)",
};

const card: React.CSSProperties = {
  background: C.surface,
  border: `1px solid ${C.border}`,
  borderRadius: 12,
  padding: "20px 24px",
};

// ── mock data ──────────────────────────────────────────────────────────────
const CONSENT_CATEGORIES = [
  { id: "data-proc",   title: "Data Processing",          rate: 96, given: 1192, revoked: 55,  color: C.teal   },
  { id: "marketing",   title: "Marketing Communications", rate: 74, given: 918,  revoked: 280, color: C.blue   },
  { id: "third-party", title: "Third-party Sharing",      rate: 61, given: 758,  revoked: 489, color: C.amber  },
  { id: "research",    title: "Research Usage",            rate: 83, given: 1033, revoked: 214, color: C.purple },
  { id: "whatsapp",    title: "WhatsApp Notifications",   rate: 88, given: 1096, revoked: 151, color: C.green  },
  { id: "analytics",   title: "Analytics",                rate: 91, given: 1131, revoked: 116, color: C.teal   },
];

const CONSENT_EVENTS = [
  { student: "Priya Sharma",     purpose: "Data Processing",          action: "GIVEN",   ts: "2026-03-19 09:45", channel: "Portal"   },
  { student: "Arjun Mehta",      purpose: "Marketing Communications", action: "REVOKED", ts: "2026-03-19 08:30", channel: "Email"    },
  { student: "Sneha Patel",      purpose: "WhatsApp Notifications",   action: "GIVEN",   ts: "2026-03-18 17:10", channel: "WhatsApp" },
  { student: "Rohan Nair",       purpose: "Analytics",                action: "GIVEN",   ts: "2026-03-18 14:00", channel: "Portal"   },
  { student: "Kavya Reddy",      purpose: "Third-party Sharing",      action: "REVOKED", ts: "2026-03-18 11:20", channel: "Portal"   },
  { student: "Vikram Iyer",      purpose: "Research Usage",           action: "GIVEN",   ts: "2026-03-18 09:05", channel: "App"      },
  { student: "Ananya Singh",     purpose: "Data Processing",          action: "GIVEN",   ts: "2026-03-17 16:50", channel: "Portal"   },
  { student: "Rahul Gupta",      purpose: "Marketing Communications", action: "REVOKED", ts: "2026-03-17 14:30", channel: "Email"    },
  { student: "Deepika Kumar",    purpose: "WhatsApp Notifications",   action: "REVOKED", ts: "2026-03-17 12:00", channel: "WhatsApp" },
  { student: "Nikhil Joshi",     purpose: "Analytics",                action: "GIVEN",   ts: "2026-03-16 10:45", channel: "App"      },
];

type DSRType = "ACCESS" | "RECTIFICATION" | "ERASURE" | "PORTABILITY";

const DSR_TYPE_COLORS: Record<DSRType, { color: string; bg: string }> = {
  ACCESS:        { color: C.teal,   bg: C.tealDim   },
  RECTIFICATION: { color: C.amber,  bg: C.amberDim  },
  ERASURE:       { color: C.red,    bg: C.redDim    },
  PORTABILITY:   { color: C.purple, bg: C.purpleDim },
};

const INITIAL_DSR = [
  { id: "DSR-2026-0041", student: "Mithun Das",      type: "ACCESS"        as DSRType, submitted: "2026-03-17", slaH: 20 },
  { id: "DSR-2026-0042", student: "Sonal Mehta",     type: "ERASURE"       as DSRType, submitted: "2026-03-18", slaH: 44 },
  { id: "DSR-2026-0043", student: "Kiran Bose",      type: "PORTABILITY"   as DSRType, submitted: "2026-03-18", slaH: 52 },
  { id: "DSR-2026-0044", student: "Aarav Patel",     type: "RECTIFICATION" as DSRType, submitted: "2026-03-19", slaH: 68 },
  { id: "DSR-2026-0045", student: "Deepika Kumar",   type: "ACCESS"        as DSRType, submitted: "2026-03-19", slaH: 71 },
];

const COMPLETED_DSR = [
  { id: "DSR-2026-0038", student: "Tanmay Roy",      type: "ACCESS"        as DSRType, resolved: "2026-03-14" },
  { id: "DSR-2026-0039", student: "Anjali Verma",    type: "ERASURE"       as DSRType, resolved: "2026-03-15" },
  { id: "DSR-2026-0040", student: "Siddharth Rao",   type: "PORTABILITY"   as DSRType, resolved: "2026-03-16" },
];

const ASSIGNEES = ["Dr. Priya Nair (DPO)", "Rahul Mishra (IT)", "Sunita Rao (Registrar)", "Karthik Nambiar (Legal)"];

const AUDIT_ROWS = [
  { ts: "2026-03-19 09:45", student: "Priya Sharma",   action: "GIVEN",   purpose: "Data Processing",          channel: "Portal",   ip: "103.21.44.12", officer: "Self-service" },
  { ts: "2026-03-19 08:30", student: "Arjun Mehta",    action: "REVOKED", purpose: "Marketing Communications", channel: "Email",    ip: "49.207.18.55", officer: "Self-service" },
  { ts: "2026-03-18 17:10", student: "Sneha Patel",    action: "GIVEN",   purpose: "WhatsApp Notifications",   channel: "WhatsApp", ip: "182.64.33.9",  officer: "Self-service" },
  { ts: "2026-03-18 14:00", student: "Rohan Nair",     action: "GIVEN",   purpose: "Analytics",                channel: "Portal",   ip: "103.21.44.88", officer: "Self-service" },
  { ts: "2026-03-18 11:20", student: "Kavya Reddy",    action: "REVOKED", purpose: "Third-party Sharing",      channel: "Portal",   ip: "49.207.18.3",  officer: "Self-service" },
  { ts: "2026-03-18 09:05", student: "Vikram Iyer",    action: "GIVEN",   purpose: "Research Usage",           channel: "App",      ip: "117.96.44.22", officer: "Self-service" },
  { ts: "2026-03-17 16:50", student: "Ananya Singh",   action: "GIVEN",   purpose: "Data Processing",          channel: "Portal",   ip: "103.21.44.55", officer: "Self-service" },
  { ts: "2026-03-17 14:30", student: "Rahul Gupta",    action: "REVOKED", purpose: "Marketing Communications", channel: "Email",    ip: "49.207.18.71", officer: "DPO-Admin"    },
  { ts: "2026-03-17 12:00", student: "Deepika Kumar",  action: "REVOKED", purpose: "WhatsApp Notifications",   channel: "WhatsApp", ip: "182.64.33.44", officer: "Self-service" },
  { ts: "2026-03-16 10:45", student: "Nikhil Joshi",   action: "GIVEN",   purpose: "Analytics",                channel: "App",      ip: "117.96.44.99", officer: "Self-service" },
  { ts: "2026-03-15 09:20", student: "Preeti Singh",   action: "GIVEN",   purpose: "Data Processing",          channel: "Portal",   ip: "103.21.44.20", officer: "Self-service" },
  { ts: "2026-03-14 15:00", student: "Tanmay Roy",     action: "REVOKED", purpose: "Analytics",                channel: "Portal",   ip: "49.207.18.88", officer: "Self-service" },
  { ts: "2026-03-14 11:10", student: "Anjali Verma",   action: "GIVEN",   purpose: "Research Usage",           channel: "App",      ip: "117.96.44.7",  officer: "Self-service" },
  { ts: "2026-03-13 13:45", student: "Siddharth Rao",  action: "GIVEN",   purpose: "Data Processing",          channel: "Portal",   ip: "103.21.44.66", officer: "Self-service" },
  { ts: "2026-03-12 10:00", student: "Nandini Krishnan",action: "REVOKED",purpose: "Third-party Sharing",      channel: "Email",    ip: "49.207.18.40", officer: "DPO-Admin"    },
  { ts: "2026-03-11 08:30", student: "Farhan Shaikh",  action: "GIVEN",   purpose: "WhatsApp Notifications",   channel: "WhatsApp", ip: "182.64.33.60", officer: "Self-service" },
  { ts: "2026-03-10 16:15", student: "Mithun Das",     action: "GIVEN",   purpose: "Marketing Communications", channel: "Portal",   ip: "103.21.44.77", officer: "Self-service" },
  { ts: "2026-03-09 11:00", student: "Sonal Mehta",    action: "GIVEN",   purpose: "Analytics",                channel: "App",      ip: "117.96.44.33", officer: "Self-service" },
  { ts: "2026-03-08 14:20", student: "Kiran Bose",     action: "REVOKED", purpose: "Research Usage",           channel: "Portal",   ip: "49.207.18.22", officer: "Self-service" },
  { ts: "2026-03-07 09:00", student: "Aarav Patel",    action: "GIVEN",   purpose: "Data Processing",          channel: "Portal",   ip: "103.21.44.99", officer: "Self-service" },
];

// ── Consents Tab ───────────────────────────────────────────────────────────
function ConsentsTab() {
  const [search, setSearch] = useState("");
  const filtered = CONSENT_EVENTS.filter(e =>
    search === "" ||
    e.student.toLowerCase().includes(search.toLowerCase()) ||
    e.purpose.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div>
      {/* stat strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginBottom: 24 }}>
        {[
          { label: "Total Consent Records", value: "1,247", icon: <FileText size={20} />, color: C.blue },
          { label: "Active Consents",        value: "1,198", icon: <CheckCircle2 size={20} />, color: C.teal },
          { label: "Revoked",                value: "49",    icon: <XCircle size={20} />, color: C.red },
          { label: "Pending Review",         value: "12",    icon: <Clock size={20} />, color: C.amber },
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

      {/* category cards 2x3 grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 16, marginBottom: 28 }}>
        {CONSENT_CATEGORIES.map(cat => (
          <div key={cat.id} style={{ ...card }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{cat.title}</div>
              <button style={{ background: "none", border: "none", color: C.teal, fontSize: 11, cursor: "pointer", fontWeight: 600, padding: 0 }}>View Details</button>
            </div>
            <div style={{ fontSize: 38, fontWeight: 800, color: cat.color, marginBottom: 8 }}>{cat.rate}%</div>
            {/* progress bar */}
            <div style={{ height: 6, background: C.surface2, borderRadius: 3, overflow: "hidden", marginBottom: 10 }}>
              <div style={{ height: "100%", width: `${cat.rate}%`, background: cat.color, borderRadius: 3 }} />
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
        ))}
      </div>

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
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: C.surface2 }}>
              {["Student", "Purpose", "Action", "Timestamp", "Channel"].map(h => (
                <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.07em" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((row, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${C.border}`, background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.01)" }}>
                <td style={{ padding: "10px 16px", fontSize: 13, color: C.text, fontWeight: 500 }}>{row.student}</td>
                <td style={{ padding: "10px 16px", fontSize: 12, color: C.muted }}>{row.purpose}</td>
                <td style={{ padding: "10px 16px" }}>
                  <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 8px", borderRadius: 4,
                    color: row.action === "GIVEN" ? C.green : C.red,
                    background: row.action === "GIVEN" ? C.greenDim : C.redDim,
                  }}>{row.action}</span>
                </td>
                <td style={{ padding: "10px 16px", fontSize: 12, color: C.muted, whiteSpace: "nowrap" }}>{row.ts}</td>
                <td style={{ padding: "10px 16px", fontSize: 12, color: C.muted }}>{row.channel}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── DSR Tab ────────────────────────────────────────────────────────────────
function DSRTab() {
  const [processing, setProcessing] = useState<string | null>(null);
  const [assignee, setAssignee] = useState("");
  const [priority, setPriority] = useState("NORMAL");
  const [notes, setNotes] = useState("");
  const [submitted, setSubmitted] = useState<string[]>([]);
  const [completedOpen, setCompletedOpen] = useState(false);

  function handleSubmit(id: string) {
    setSubmitted(s => [...s, id]);
    setProcessing(null);
    setAssignee(""); setPriority("NORMAL"); setNotes("");
  }

  const pending = INITIAL_DSR.filter(d => !submitted.includes(d.id));

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
        <AlertTriangle size={16} color={C.amber} />
        <span style={{ fontSize: 13, color: C.muted }}>DPDP §12 — Data Subject Requests must be resolved within 72 hours of receipt.</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 28 }}>
        {pending.map(dsr => {
          const tc = DSR_TYPE_COLORS[dsr.type];
          const isOpen = processing === dsr.id;
          const slaColor = dsr.slaH < 48 ? C.red : dsr.slaH < 60 ? C.amber : C.teal;
          const slaPct = Math.min(100, (dsr.slaH / 72) * 100);
          return (
            <div key={dsr.id} style={{ ...card }}>
              <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
                {/* id */}
                <div style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700, color: C.teal, width: 140, flexShrink: 0 }}>{dsr.id}</div>
                {/* student */}
                <div style={{ flex: 1, fontSize: 14, fontWeight: 600, color: C.text }}>{dsr.student}</div>
                {/* type */}
                <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 4, color: tc.color, background: tc.bg }}>{dsr.type}</span>
                {/* submitted */}
                <span style={{ fontSize: 12, color: C.muted }}>{dsr.submitted}</span>
                {/* button */}
                <button onClick={() => setProcessing(isOpen ? null : dsr.id)} style={{
                  padding: "7px 16px", borderRadius: 8, border: "none", background: C.teal, color: "#fff",
                  fontSize: 12, fontWeight: 600, cursor: "pointer", flexShrink: 0,
                }}>
                  {isOpen ? "Cancel" : "Assign & Process"}
                </button>
              </div>

              {/* SLA bar */}
              <div style={{ marginTop: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                  <span style={{ fontSize: 11, color: C.muted }}>SLA Remaining</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: slaColor }}>{dsr.slaH}h</span>
                </div>
                <div style={{ height: 5, background: C.surface2, borderRadius: 3, overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${slaPct}%`, background: slaColor, borderRadius: 3 }} />
                </div>
              </div>

              {/* inline form */}
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
          <span style={{ fontSize: 11, color: C.muted, background: C.surface2, padding: "2px 8px", borderRadius: 10 }}>{COMPLETED_DSR.length + submitted.length}</span>
        </button>
        {completedOpen && (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: C.surface2 }}>
                {["Request ID", "Student", "Type", "Resolved"].map(h => (
                  <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.07em" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {COMPLETED_DSR.map((r, i) => {
                const tc = DSR_TYPE_COLORS[r.type];
                return (
                  <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
                    <td style={{ padding: "10px 16px", fontFamily: "monospace", fontSize: 12, color: C.teal }}>{r.id}</td>
                    <td style={{ padding: "10px 16px", fontSize: 13, color: C.text }}>{r.student}</td>
                    <td style={{ padding: "10px 16px" }}>
                      <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 4, color: tc.color, background: tc.bg }}>{r.type}</span>
                    </td>
                    <td style={{ padding: "10px 16px", fontSize: 12, color: C.muted }}>{r.resolved}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
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

function AuditLogTab() {
  const [toast, setToast] = useState(false);
  const [rows, setRows] = useState<typeof AUDIT_ROWS>([]);
  const [liveLoading, setLiveLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("token") ?? "";
    fetch("/api/v1/audit/logs?entity_type=consent&limit=50", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() as Promise<{ logs?: AuditLogEntry[] }> : null)
      .then(data => {
        const logs = data?.logs ?? [];
        if (logs.length > 0) {
          setRows(logs.map(l => ({
            ts: new Date(l.timestamp).toLocaleString("en-IN", { hour12: false }).replace(",", ""),
            student: String(l.metadata?.student_name ?? l.metadata?.user_name ?? l.entity_id ?? "—"),
            action: l.action.toUpperCase() === "CREATE" ? "GIVEN" : l.action.toUpperCase() === "DELETE" ? "REVOKED" : l.action.toUpperCase(),
            purpose: String(l.metadata?.purpose ?? l.entity_type ?? "—"),
            channel: String(l.metadata?.channel ?? "System"),
            ip: String(l.metadata?.ip_address ?? "—"),
            officer: String(l.metadata?.actor_name ?? l.actor_role ?? "—"),
          })));
        } else {
          setRows(AUDIT_ROWS);
        }
        setLiveLoading(false);
      })
      .catch(() => { setRows(AUDIT_ROWS); setLiveLoading(false); });
  }, []);

  function handleExport() {
    setToast(true);
    setTimeout(() => setToast(false), 2000);
  }

  return (
    <div style={{ position: "relative" }}>
      {/* toast */}
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

      {liveLoading ? (
        <div style={{ textAlign: "center", padding: 40, color: C.muted }}>Loading audit log…</div>
      ) : (
        <div style={{ ...card, padding: 0, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: C.surface2 }}>
                {["Timestamp", "Student", "Action", "Purpose", "Channel", "IP Address", "Officer"].map(h => (
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
  const [tab, setTab] = useState<Tab>("consents");

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "consents", label: "Consents",     icon: <Shield size={14} /> },
    { id: "dsr",      label: "DSR Requests", icon: <FileText size={14} /> },
    { id: "audit",    label: "Audit Log",    icon: <BarChart3 size={14} /> },
  ];

  return (
    <div style={{ minHeight: "100vh", background: C.bg, padding: "32px 40px", fontFamily: "Inter, system-ui, sans-serif" }}>
      {/* header */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
          <Shield size={22} color={C.teal} />
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: C.text }}>Consent Management</h1>
          <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 6, background: C.tealDim, color: C.teal }}>DPDP 2023</span>
        </div>
        <p style={{ margin: 0, fontSize: 13, color: C.muted }}>Manage student consents, data subject requests (DSR), and maintain a full consent audit trail.</p>
      </div>

      {/* tab bar */}
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

      {tab === "consents" && <ConsentsTab />}
      {tab === "dsr"      && <DSRTab />}
      {tab === "audit"    && <AuditLogTab />}
    </div>
  );
}
