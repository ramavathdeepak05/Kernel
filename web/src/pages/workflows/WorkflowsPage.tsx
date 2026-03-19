import { useState } from "react";
import {
  Clock, CheckCircle2, AlertTriangle, Users, ChevronUp, ChevronDown,
  Search, Filter, RotateCcw, ThumbsUp, ThumbsDown, ArrowUp,
  CalendarCheck, Shield, FileText, GraduationCap, DollarSign,
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

// ── mock data ──────────────────────────────────────────────────────────────
const INITIAL_QUEUE = [
  { id: "1", dot: C.amber,   badge: "FEE_WAIVER",     role: "Finance",    student: "Priya Sharma",     desc: "Requesting 50% tuition waiver citing financial hardship — income certificate attached",        submitted: "2h ago" },
  { id: "2", dot: C.teal,    badge: "OFFER_LETTER",   role: "Registrar",  student: "Arjun Mehta",      desc: "Conditional offer requires HOD countersign before dispatch to candidate",                    submitted: "3h ago" },
  { id: "3", dot: C.red,     badge: "GRADE_OVERRIDE", role: "HOD",        student: "Sneha Patel",      desc: "Lab component re-evaluation requested after equipment failure during exam",                   submitted: "5h ago" },
  { id: "4", dot: C.blue,    badge: "DOCUMENT_REUP",  role: "Registrar",  student: "Rohan Nair",       desc: "Original marksheet rejected (low scan quality), student re-uploaded clearer version",         submitted: "6h ago" },
  { id: "5", dot: C.amber,   badge: "FEE_WAIVER",     role: "Finance",    student: "Kavya Reddy",      desc: "Sports scholarship top-up request — state level achievement certificate provided",            submitted: "8h ago" },
  { id: "6", dot: C.teal,    badge: "HOSTEL_ALLOC",   role: "Dean",       student: "Vikram Iyer",      desc: "Room change request citing medical reason — doctor certificate attached by warden",           submitted: "10h ago" },
  { id: "7", dot: C.red,     badge: "GRADE_OVERRIDE", role: "HOD",        student: "Ananya Singh",     desc: "Internal mark revision after OMR scanning error identified in batch 2024-B",                 submitted: "12h ago" },
  { id: "8", dot: C.blue,    badge: "LEAVE_APPROVAL", role: "HOD",        student: "Rahul Gupta",      desc: "Medical leave extension for 14 days — hospital discharge summary submitted",                  submitted: "1d ago" },
];

const ESCALATIONS = [
  { id: "e1", title: "FEE_WAIVER — Priya Sharma", reason: "Primary approver (Finance Head) inactive for 48h", original: "Dr. Ramesh Nair (Finance Head)", escalatedTo: "Dean — Prof. Aisha Patel", since: "6h ago", slaRemaining: 45 },
  { id: "e2", title: "GRADE_OVERRIDE — Ananya Singh", reason: "HOD did not respond within SLA window (24h)", original: "Dr. K. Krishnamurthy (HOD CSE)", escalatedTo: "Academic Registrar", since: "2h ago", slaRemaining: 180 },
  { id: "e3", title: "OFFER_LETTER — Batch 2024-B", reason: "System escalation — quorum not met in 36h", original: "Admissions Committee", escalatedTo: "Vice Chancellor", since: "30m ago", slaRemaining: 18 },
];

const QUORUM = [
  { id: "q1", title: "Merit List Final Approval — CSE 2025", required: ["Dean Academics", "HOD CSE", "Finance Controller"], approved: [true, true, false], votes: 2, total: 3, voted: false },
  { id: "q2", title: "Bulk Fee Waiver — EWS Category Q3", required: ["Finance Head", "Registrar", "Dean Student Welfare"], approved: [true, false, false], votes: 1, total: 3, voted: false },
  { id: "q3", title: "Hostel Block-D Reallocation Policy", required: ["Chief Warden", "Dean Admin", "Registrar", "Student Rep"], approved: [true, true, true, false], votes: 3, total: 4, voted: false },
];

const HISTORY = [
  { date: "2026-03-19 09:12", event: "FEE_WAIVER",     student: "Mithun Das",       approvedBy: "Dr. Priya Nair",       outcome: "APPROVED",  duration: "1.2h" },
  { date: "2026-03-19 08:47", event: "GRADE_OVERRIDE",  student: "Sonal Mehta",      approvedBy: "Prof. R. Sharma",      outcome: "REJECTED",  duration: "0.8h" },
  { date: "2026-03-19 07:30", event: "OFFER_LETTER",    student: "Kiran Bose",       approvedBy: "Registrar Office",     outcome: "APPROVED",  duration: "2.1h" },
  { date: "2026-03-18 22:15", event: "LEAVE_APPROVAL",  student: "Aarav Patel",      approvedBy: "Dr. Sunita Rao",       outcome: "APPROVED",  duration: "0.5h" },
  { date: "2026-03-18 20:00", event: "DOCUMENT_REUP",   student: "Deepika Kumar",    approvedBy: "Admissions Desk",      outcome: "APPROVED",  duration: "3.0h" },
  { date: "2026-03-18 18:45", event: "FEE_WAIVER",      student: "Nikhil Joshi",     approvedBy: "Finance Head",         outcome: "ESCALATED", duration: "6.2h" },
  { date: "2026-03-18 17:10", event: "HOSTEL_ALLOC",    student: "Preeti Singh",     approvedBy: "Chief Warden",         outcome: "APPROVED",  duration: "1.8h" },
  { date: "2026-03-18 15:50", event: "GRADE_OVERRIDE",  student: "Tanmay Roy",       approvedBy: "HOD Mech",             outcome: "APPROVED",  duration: "4.5h" },
  { date: "2026-03-18 14:20", event: "FEE_WAIVER",      student: "Anjali Verma",     approvedBy: "Dean Student Affairs", outcome: "REJECTED",  duration: "2.3h" },
  { date: "2026-03-18 12:00", event: "LEAVE_APPROVAL",  student: "Siddharth Rao",    approvedBy: "Dr. K. Pillai",        outcome: "APPROVED",  duration: "0.3h" },
  { date: "2026-03-18 10:45", event: "OFFER_LETTER",    student: "Nandini Krishnan", approvedBy: "Registrar Office",     outcome: "APPROVED",  duration: "1.1h" },
  { date: "2026-03-17 09:00", event: "HOSTEL_ALLOC",    student: "Farhan Shaikh",    approvedBy: "Chief Warden",         outcome: "ESCALATED", duration: "9.0h" },
];

const ROLES = ["All", "Finance", "Registrar", "HOD", "Dean"];

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
    <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", color, background: bg, padding: "3px 8px", borderRadius: 4 }}>
      {label}
    </span>
  );
}

// ── Queue Tab ──────────────────────────────────────────────────────────────
function QueueTab() {
  const [queue, setQueue] = useState(INITIAL_QUEUE);
  const [flash, setFlash] = useState<string | null>(null);
  const [roleFilter, setRoleFilter] = useState("All");
  const [search, setSearch] = useState("");

  function handleAction(id: string, action: "approve" | "reject") {
    setFlash(id + action);
    setTimeout(() => {
      setQueue(q => q.filter(r => r.id !== id));
      setFlash(null);
    }, 700);
  }

  const visible = queue.filter(r =>
    (roleFilter === "All" || r.role === roleFilter) &&
    (search === "" || r.student.toLowerCase().includes(search.toLowerCase()) || r.badge.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div>
      <StatStrip items={[
        { label: "Pending Approvals", value: queue.length, icon: <Clock size={20} />, color: C.amber },
        { label: "Avg Wait", value: "4.2h", icon: <RotateCcw size={20} />, color: C.blue },
        { label: "Escalated", value: 3, icon: <ArrowUp size={20} />, color: C.red },
        { label: "Resolved Today", value: 28, icon: <CheckCircle2 size={20} />, color: C.teal },
      ]} />

      {/* filter bar */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 6 }}>
          {ROLES.map(r => (
            <button key={r} onClick={() => setRoleFilter(r)} style={{
              padding: "6px 14px", borderRadius: 20, fontSize: 12, fontWeight: 600, cursor: "pointer", border: "none",
              background: roleFilter === r ? C.teal : C.surface2,
              color: roleFilter === r ? "#fff" : C.muted,
              transition: "all 0.15s",
            }}>{r}</button>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 8, padding: "6px 12px", flex: 1, maxWidth: 320 }}>
          <Search size={14} color={C.muted} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search student or event type…"
            style={{ background: "none", border: "none", outline: "none", color: C.text, fontSize: 13, flex: 1 }} />
        </div>
      </div>

      {/* list */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {visible.length === 0 && (
          <div style={{ ...card, textAlign: "center", padding: "48px 24px" }}>
            <CheckCircle2 size={40} color={C.teal} style={{ margin: "0 auto 12px" }} />
            <div style={{ color: C.text, fontWeight: 600, fontSize: 16 }}>All caught up!</div>
            <div style={{ color: C.muted, fontSize: 13, marginTop: 6 }}>No pending approvals in this queue.</div>
          </div>
        )}
        {visible.map(row => {
          const isFlashing = flash === row.id + "approve" || flash === row.id + "reject";
          return (
            <div key={row.id} style={{
              ...card, display: "flex", alignItems: "center", gap: 16, padding: "14px 20px",
              opacity: isFlashing ? 0.5 : 1, transition: "opacity 0.3s",
              position: "relative", overflow: "hidden",
            }}>
              {isFlashing && (
                <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(29,158,117,0.08)", fontSize: 18, fontWeight: 700, color: C.teal }}>
                  ✓ Done
                </div>
              )}
              {/* status dot */}
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: row.dot, flexShrink: 0 }} />
              {/* badge */}
              <BadgePill label={row.badge} color={row.dot} bg={`${row.dot}22`} />
              {/* center */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ fontWeight: 600, color: C.text, fontSize: 14 }}>{row.student}</span>
                  <span style={{ fontSize: 11, color: C.muted, background: C.surface2, padding: "2px 8px", borderRadius: 4 }}>{row.role}</span>
                  <span style={{ fontSize: 11, color: C.muted }}>{row.submitted}</span>
                </div>
                <div style={{ fontSize: 12, color: C.muted, marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {row.desc}
                </div>
              </div>
              {/* actions */}
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
                <button onClick={() => handleAction(row.id, "approve")} style={{
                  padding: "7px 16px", borderRadius: 8, border: "none", background: C.teal, color: "#fff",
                  fontSize: 12, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                }}>
                  <ThumbsUp size={12} /> Approve
                </button>
                <button onClick={() => handleAction(row.id, "reject")} style={{
                  padding: "7px 16px", borderRadius: 8, border: `1px solid ${C.red}55`, background: C.redDim, color: C.red,
                  fontSize: 12, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                }}>
                  <ThumbsDown size={12} /> Reject
                </button>
                <button style={{ background: "none", border: "none", color: C.muted, fontSize: 12, cursor: "pointer", textDecoration: "underline", padding: "7px 4px" }}>
                  Escalate
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Escalations Tab ────────────────────────────────────────────────────────
function EscalationsTab() {
  const [resolved, setResolved] = useState<string[]>([]);
  const items = ESCALATIONS.filter(e => !resolved.includes(e.id));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {items.map(e => {
        const slaColor = e.slaRemaining < 60 ? C.red : e.slaRemaining < 120 ? C.amber : C.teal;
        const slaPct = Math.min(100, (e.slaRemaining / 240) * 100);
        return (
          <div key={e.id} style={{ ...card }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                  <AlertTriangle size={16} color={C.red} />
                  <span style={{ fontWeight: 700, color: C.text, fontSize: 15 }}>{e.title}</span>
                </div>
                <div style={{ fontSize: 12, color: C.muted }}>
                  <span style={{ color: C.amber }}>Reason:</span> {e.reason}
                </div>
              </div>
              <span style={{ fontSize: 11, color: C.muted }}>{e.since}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
              <div style={{ background: C.surface2, borderRadius: 8, padding: "10px 14px" }}>
                <div style={{ fontSize: 10, color: C.muted, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.08em" }}>Original Approver</div>
                <div style={{ fontSize: 13, color: C.text }}>{e.original}</div>
              </div>
              <div style={{ background: C.surface2, borderRadius: 8, padding: "10px 14px" }}>
                <div style={{ fontSize: 10, color: C.muted, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.08em" }}>Escalated To</div>
                <div style={{ fontSize: 13, color: C.teal }}>{e.escalatedTo}</div>
              </div>
            </div>
            {/* SLA bar */}
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span style={{ fontSize: 11, color: C.muted }}>SLA Remaining</span>
                <span style={{ fontSize: 11, fontWeight: 700, color: slaColor }}>{e.slaRemaining < 60 ? `${e.slaRemaining}m` : `${Math.floor(e.slaRemaining / 60)}h ${e.slaRemaining % 60}m`}</span>
              </div>
              <div style={{ height: 6, background: C.surface2, borderRadius: 3, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${slaPct}%`, background: slaColor, borderRadius: 3, transition: "width 0.3s" }} />
              </div>
            </div>
            <button onClick={() => setResolved(r => [...r, e.id])} style={{
              padding: "8px 18px", borderRadius: 8, border: `1px solid ${C.red}55`, background: C.redDim,
              color: C.red, fontSize: 12, fontWeight: 600, cursor: "pointer",
            }}>
              Force Resolve
            </button>
          </div>
        );
      })}
      {items.length === 0 && (
        <div style={{ ...card, textAlign: "center", padding: "48px 24px" }}>
          <Shield size={36} color={C.teal} style={{ margin: "0 auto 12px" }} />
          <div style={{ color: C.text, fontWeight: 600 }}>No active escalations</div>
        </div>
      )}
    </div>
  );
}

// ── Quorum Tab ─────────────────────────────────────────────────────────────
function QuorumTab() {
  const [quorum, setQuorum] = useState(QUORUM);

  function castVote(id: string) {
    setQuorum(q => q.map(item => item.id !== id ? item : {
      ...item,
      voted: true,
      votes: item.votes + 1,
      approved: item.approved.map((v, i) => i === item.approved.indexOf(false) ? true : v),
    }));
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {quorum.map(q => {
        const pct = (q.votes / q.total) * 100;
        const allApproved = q.votes === q.total;
        return (
          <div key={q.id} style={{ ...card }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
              <div style={{ fontWeight: 700, color: C.text, fontSize: 15 }}>{q.title}</div>
              <span style={{ fontSize: 13, fontWeight: 700, color: allApproved ? C.teal : C.amber }}>
                {q.votes}/{q.total} approved
              </span>
            </div>
            {/* signatories */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
              {q.required.map((name, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{ width: 20, height: 20, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", background: q.approved[i] ? C.greenDim : C.surface2, border: `1px solid ${q.approved[i] ? C.green : C.border}` }}>
                    {q.approved[i]
                      ? <CheckCircle2 size={12} color={C.green} />
                      : <Clock size={10} color={C.muted} />}
                  </div>
                  <span style={{ fontSize: 13, color: q.approved[i] ? C.text : C.muted }}>{name}</span>
                  {q.approved[i] && <span style={{ fontSize: 10, color: C.green, background: C.greenDim, padding: "2px 6px", borderRadius: 4 }}>VOTED</span>}
                </div>
              ))}
            </div>
            {/* progress bar */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ height: 8, background: C.surface2, borderRadius: 4, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${pct}%`, background: allApproved ? C.teal : C.amber, borderRadius: 4, transition: "width 0.4s" }} />
              </div>
            </div>
            <button onClick={() => !q.voted && castVote(q.id)} disabled={q.voted || allApproved} style={{
              padding: "8px 20px", borderRadius: 8, border: "none", cursor: q.voted || allApproved ? "default" : "pointer",
              background: q.voted || allApproved ? C.surface2 : C.teal,
              color: q.voted || allApproved ? C.muted : "#fff",
              fontSize: 13, fontWeight: 600,
            }}>
              {allApproved ? "✓ Quorum Reached" : q.voted ? "Vote Recorded" : "Cast Your Vote"}
            </button>
          </div>
        );
      })}
    </div>
  );
}

// ── History Tab ────────────────────────────────────────────────────────────
function HistoryTab() {
  const outcomeCfg: Record<string, { color: string; bg: string }> = {
    APPROVED:  { color: C.green,  bg: C.greenDim  },
    REJECTED:  { color: C.red,    bg: C.redDim    },
    ESCALATED: { color: C.amber,  bg: C.amberDim  },
  };

  return (
    <div style={{ ...card, padding: 0, overflow: "hidden" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: C.surface2, borderBottom: `1px solid ${C.border}` }}>
            {["Date", "Event", "Student", "Approved By", "Outcome", "Duration"].map(h => (
              <th key={h} style={{ padding: "12px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.07em" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {HISTORY.map((row, i) => {
            const oc = outcomeCfg[row.outcome] ?? { color: C.muted, bg: C.surface2 };
            return (
              <tr key={i} style={{ borderBottom: `1px solid ${C.border}`, background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.01)" }}>
                <td style={{ padding: "12px 16px", fontSize: 12, color: C.muted, whiteSpace: "nowrap" }}>{row.date}</td>
                <td style={{ padding: "12px 16px" }}>
                  <BadgePill label={row.event} color={C.blue} bg={C.blueDim} />
                </td>
                <td style={{ padding: "12px 16px", fontSize: 13, color: C.text }}>{row.student}</td>
                <td style={{ padding: "12px 16px", fontSize: 12, color: C.muted }}>{row.approvedBy}</td>
                <td style={{ padding: "12px 16px" }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: oc.color, background: oc.bg, padding: "3px 8px", borderRadius: 4 }}>{row.outcome}</span>
                </td>
                <td style={{ padding: "12px 16px", fontSize: 12, color: C.muted }}>{row.duration}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────
type Tab = "queue" | "escalations" | "quorum" | "history";

export function WorkflowsPage() {
  const [tab, setTab] = useState<Tab>("queue");

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "queue",       label: "Queue",       icon: <Clock size={14} /> },
    { id: "escalations", label: "Escalations", icon: <AlertTriangle size={14} /> },
    { id: "quorum",      label: "Quorum",      icon: <Users size={14} /> },
    { id: "history",     label: "History",     icon: <CalendarCheck size={14} /> },
  ];

  return (
    <div style={{ minHeight: "100vh", background: C.bg, padding: "32px 40px", fontFamily: "Inter, system-ui, sans-serif" }}>
      {/* header */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
          <Shield size={22} color={C.teal} />
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: C.text }}>Approval Workflows</h1>
        </div>
        <p style={{ margin: 0, fontSize: 13, color: C.muted }}>Manage pending approvals, escalations, quorum decisions, and review history.</p>
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

      {/* content */}
      {tab === "queue"       && <QueueTab />}
      {tab === "escalations" && <EscalationsTab />}
      {tab === "quorum"      && <QuorumTab />}
      {tab === "history"     && <HistoryTab />}
    </div>
  );
}
