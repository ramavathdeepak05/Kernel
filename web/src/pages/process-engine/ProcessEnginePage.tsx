import { useState } from "react";
import {
  GitBranch, Shield, ClipboardList, ChevronDown, ChevronUp, Plus, X,
  ArrowRight, CheckCircle2, Clock, AlertTriangle, FileText, Users,
  Settings, History, Layers,
} from "lucide-react";

// ── theme ──────────────────────────────────────────────────────────────────
const C = {
  bg: "#0f172a",
  surface: "#1e293b",
  surface2: "#253047",
  surface3: "#1a2540",
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

// ── Workflow data ──────────────────────────────────────────────────────────
type WFStep = { name: string; role: string; sla: string };
type WFTemplate = { id: string; label: string; steps: WFStep[] };

const WORKFLOWS: WFTemplate[] = [
  {
    id: "admissions",
    label: "Admissions → Enrollment",
    steps: [
      { name: "Application Submit", role: "Student", sla: "—" },
      { name: "Doc Verification", role: "Registrar", sla: "48h" },
      { name: "Eligibility Check", role: "AI Engine", sla: "2h" },
      { name: "Offer Approval", role: "Dean Acad.", sla: "24h" },
      { name: "Enrollment", role: "System", sla: "1h" },
    ],
  },
  {
    id: "fee-waiver",
    label: "Fee Waiver",
    steps: [
      { name: "Request Submitted", role: "Student", sla: "—" },
      { name: "Finance Review", role: "Finance Head", sla: "24h" },
      { name: "Dean Approval", role: "Dean", sla: "12h" },
      { name: "Disbursement", role: "System", sla: "4h" },
    ],
  },
  {
    id: "grade-override",
    label: "Grade Override",
    steps: [
      { name: "Override Request", role: "Student", sla: "—" },
      { name: "Faculty Review", role: "Faculty", sla: "12h" },
      { name: "HOD Sign-off", role: "HOD", sla: "24h" },
      { name: "Registrar Update", role: "Registrar", sla: "2h" },
    ],
  },
  {
    id: "leave",
    label: "Leave Approval",
    steps: [
      { name: "Leave Application", role: "Student", sla: "—" },
      { name: "Faculty Check", role: "Faculty", sla: "6h" },
      { name: "HOD Approval", role: "HOD", sla: "12h" },
    ],
  },
  {
    id: "doc-reupload",
    label: "Document Re-upload",
    steps: [
      { name: "Re-upload Request", role: "Student", sla: "—" },
      { name: "Doc Review", role: "Registrar", sla: "48h" },
      { name: "Approval / Reject", role: "Admissions", sla: "12h" },
    ],
  },
  {
    id: "hostel",
    label: "Hostel Allocation",
    steps: [
      { name: "Allocation Request", role: "Student", sla: "—" },
      { name: "Warden Review", role: "Warden", sla: "24h" },
      { name: "Dean Admin", role: "Dean Admin", sla: "12h" },
      { name: "Room Assignment", role: "System", sla: "1h" },
    ],
  },
];

// ── Policy data ────────────────────────────────────────────────────────────
const POLICY_CARDS = [
  {
    id: "eligibility",
    title: "Eligibility",
    icon: <CheckCircle2 size={16} />,
    color: C.teal,
    rules: [
      "Minimum 60% aggregate in qualifying exam",
      "Age limit: 17–25 years as on 01-Aug",
      "Category relaxation: SC/ST −5%, OBC −3%",
      "NRI quota: 15% seats reserved",
    ],
  },
  {
    id: "seat",
    title: "Seat Allocation",
    icon: <Layers size={16} />,
    color: C.purple,
    rules: [
      "Merit-based ranking via weighted formula",
      "Seat freeze deadline: 7 days post offer",
      "Waitlist auto-trigger at 80% acceptance",
      "Round-robin allocation for tied ranks",
    ],
  },
  {
    id: "fee",
    title: "Fee Structure",
    icon: <FileText size={16} />,
    color: C.amber,
    rules: [
      "Tuition fee index-linked to CPI annually",
      "Hostel optional — billed per semester",
      "Late payment penalty: 2% per month",
      "Scholarship offset applied before due date",
    ],
  },
];

const RULES_TABLE = [
  { key: "MIN_AGGREGATE_PCT",       value: "60",           version: "v3",  modified: "2026-02-10", author: "Registrar" },
  { key: "AGE_MIN",                 value: "17",           version: "v1",  modified: "2025-07-01", author: "Registrar" },
  { key: "AGE_MAX",                 value: "25",           version: "v1",  modified: "2025-07-01", author: "Registrar" },
  { key: "SC_ST_RELAXATION_PCT",    value: "5",            version: "v2",  modified: "2025-11-20", author: "Dean Acad." },
  { key: "OBC_RELAXATION_PCT",      value: "3",            version: "v2",  modified: "2025-11-20", author: "Dean Acad." },
  { key: "NRI_QUOTA_PCT",           value: "15",           version: "v1",  modified: "2025-07-01", author: "VC Office" },
  { key: "LATE_PAYMENT_PENALTY_PCT","value": "2",          version: "v1",  modified: "2025-07-01", author: "Finance Head" },
  { key: "SEAT_FREEZE_DAYS",        value: "7",            version: "v2",  modified: "2026-01-15", author: "Admissions" },
];

// ── Audit data ─────────────────────────────────────────────────────────────
const AUDIT_EVENTS = [
  { ts: "2026-03-19 10:05", type: "RULE_UPDATED",    by: "Dean Academics",  summary: "MIN_AGGREGATE_PCT changed from 55 → 60" },
  { ts: "2026-03-18 17:30", type: "WORKFLOW_EDITED", by: "Super Admin",     summary: "Fee Waiver: added Dean approval step after Finance review" },
  { ts: "2026-03-18 14:15", type: "POLICY_CREATED",  by: "Registrar",       summary: "New seat-freeze policy added for 2026 intake" },
  { ts: "2026-03-17 11:00", type: "RULE_UPDATED",    by: "Finance Head",    summary: "LATE_PAYMENT_PENALTY_PCT set to 2 (was 1.5)" },
  { ts: "2026-03-16 09:45", type: "WORKFLOW_EDITED", by: "Super Admin",     summary: "Grade Override: SLA on HOD step reduced to 24h" },
  { ts: "2026-03-15 16:20", type: "RULE_UPDATED",    by: "Dean Academics",  summary: "SC_ST_RELAXATION_PCT updated from 3 → 5" },
  { ts: "2026-03-14 13:10", type: "POLICY_ARCHIVED", by: "Registrar",       summary: "Legacy boarding policy v1 archived" },
  { ts: "2026-03-13 10:00", type: "WORKFLOW_CREATED",by: "Super Admin",     summary: "New workflow: Document Re-upload added" },
  { ts: "2026-03-12 08:30", type: "RULE_UPDATED",    by: "VC Office",       summary: "NRI_QUOTA_PCT confirmed at 15 for AY2026-27" },
  { ts: "2026-03-11 15:45", type: "POLICY_CREATED",  by: "Finance Head",    summary: "Fee structure v4 created for 2026-27" },
  { ts: "2026-03-10 12:00", type: "RULE_UPDATED",    by: "Admissions",      summary: "SEAT_FREEZE_DAYS changed from 10 → 7" },
  { ts: "2026-03-09 09:15", type: "WORKFLOW_EDITED", by: "Super Admin",     summary: "Hostel Allocation: Dean Admin step inserted" },
  { ts: "2026-03-08 17:00", type: "POLICY_ARCHIVED", by: "Dean Academics",  summary: "Old entrance exam eligibility policy archived" },
  { ts: "2026-03-07 11:30", type: "RULE_UPDATED",    by: "Registrar",       summary: "AGE_MIN confirmed unchanged for AY2026-27" },
  { ts: "2026-03-06 10:00", type: "WORKFLOW_CREATED",by: "Super Admin",     summary: "Leave Approval workflow created for Ph.D. students" },
];

const AUDIT_TYPE_COLORS: Record<string, { color: string; bg: string }> = {
  RULE_UPDATED:     { color: C.amber,  bg: C.amberDim  },
  WORKFLOW_EDITED:  { color: C.blue,   bg: C.blueDim   },
  POLICY_CREATED:   { color: C.teal,   bg: C.tealDim   },
  POLICY_ARCHIVED:  { color: C.muted,  bg: C.surface2  },
  WORKFLOW_CREATED: { color: C.purple, bg: C.purpleDim },
};

// ── Workflows Tab ──────────────────────────────────────────────────────────
function WorkflowsTab() {
  const [selected, setSelected] = useState("admissions");
  const [showTooltip, setShowTooltip] = useState(false);
  const wf = WORKFLOWS.find(w => w.id === selected) ?? WORKFLOWS[0];

  return (
    <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
      {/* left panel */}
      <div style={{ width: 280, flexShrink: 0, display: "flex", flexDirection: "column", gap: 6 }}>
        {WORKFLOWS.map(w => (
          <button key={w.id} onClick={() => setSelected(w.id)} style={{
            padding: "12px 16px", borderRadius: 10, border: `1px solid ${selected === w.id ? C.teal : C.border}`,
            background: selected === w.id ? C.tealDim : C.surface, color: selected === w.id ? C.teal : C.text,
            textAlign: "left", cursor: "pointer", fontSize: 13, fontWeight: selected === w.id ? 700 : 500,
            display: "flex", alignItems: "center", gap: 10, transition: "all 0.15s",
          }}>
            <GitBranch size={14} color={selected === w.id ? C.teal : C.muted} />
            {w.label}
          </button>
        ))}
      </div>

      {/* right panel */}
      <div style={{ flex: 1 }}>
        <div style={{ ...card, marginBottom: 16 }}>
          <div style={{ fontWeight: 700, color: C.text, fontSize: 16, marginBottom: 6 }}>{wf.label}</div>
          <div style={{ fontSize: 12, color: C.muted, marginBottom: 24 }}>{wf.steps.length} steps &nbsp;·&nbsp; BPMN-lite view</div>

          {/* BPMN diagram */}
          <div style={{ display: "flex", alignItems: "center", gap: 0, overflowX: "auto", paddingBottom: 8 }}>
            {wf.steps.map((step, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
                <div style={{
                  width: 130, height: 72, borderRadius: 10, padding: "10px 12px",
                  border: `2px solid ${i === 1 ? C.teal : C.border}`,
                  background: i === 1 ? C.tealDim : C.surface2,
                  display: "flex", flexDirection: "column", justifyContent: "center", gap: 6,
                }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: i === 1 ? C.teal : C.text, lineHeight: 1.3 }}>{step.name}</div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 10, color: C.muted, background: C.surface, padding: "2px 6px", borderRadius: 4 }}>{step.role}</span>
                    {step.sla !== "—" && <span style={{ fontSize: 10, color: C.amber }}>{step.sla}</span>}
                  </div>
                </div>
                {i < wf.steps.length - 1 && (
                  <div style={{ display: "flex", alignItems: "center", color: C.muted, padding: "0 6px" }}>
                    <ArrowRight size={18} />
                  </div>
                )}
              </div>
            ))}
          </div>

          <div style={{ marginTop: 20, display: "flex", alignItems: "center", gap: 12 }}>
            <div
              style={{ position: "relative", display: "inline-block" }}
              onMouseEnter={() => setShowTooltip(true)}
              onMouseLeave={() => setShowTooltip(false)}
            >
              <button style={{
                padding: "8px 18px", borderRadius: 8, border: `1px solid ${C.border}`,
                background: C.surface2, color: C.muted, fontSize: 12, fontWeight: 600, cursor: "not-allowed",
              }}>
                Edit Workflow
              </button>
              {showTooltip && (
                <div style={{
                  position: "absolute", bottom: "calc(100% + 8px)", left: "50%", transform: "translateX(-50%)",
                  background: "#0f172a", border: `1px solid ${C.border}`, borderRadius: 6, padding: "6px 12px",
                  fontSize: 11, color: C.muted, whiteSpace: "nowrap", zIndex: 10,
                  boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
                }}>
                  Contact Super Admin to edit workflows
                </div>
              )}
            </div>
            <span style={{ fontSize: 11, color: C.muted }}>Workflow editing requires Super Admin role</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Policy Rules Tab ───────────────────────────────────────────────────────
function PolicyRulesTab() {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formKey, setFormKey] = useState("");
  const [formValue, setFormValue] = useState("");
  const [formJustification, setFormJustification] = useState("");
  const [saved, setSaved] = useState(false);

  function handleSave() {
    setSaved(true);
    setTimeout(() => { setSaved(false); setShowForm(false); setFormKey(""); setFormValue(""); setFormJustification(""); }, 1500);
  }

  return (
    <div>
      {/* policy cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 16, marginBottom: 28 }}>
        {POLICY_CARDS.map(pc => (
          <div key={pc.id} style={{ ...card }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
              <div style={{ width: 36, height: 36, borderRadius: 8, background: `${pc.color}22`, display: "flex", alignItems: "center", justifyContent: "center", color: pc.color }}>
                {pc.icon}
              </div>
              <span style={{ fontWeight: 700, color: C.text, fontSize: 14 }}>{pc.title}</span>
            </div>
            <button onClick={() => setExpanded(expanded === pc.id ? null : pc.id)} style={{
              background: "none", border: "none", color: C.teal, fontSize: 12, cursor: "pointer",
              display: "flex", alignItems: "center", gap: 4, padding: 0, fontWeight: 600,
            }}>
              {expanded === pc.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              {expanded === pc.id ? "Hide Rules" : "View Rules"}
            </button>
            {expanded === pc.id && (
              <ul style={{ margin: "12px 0 0 0", padding: "0 0 0 16px", display: "flex", flexDirection: "column", gap: 6 }}>
                {pc.rules.map((r, i) => (
                  <li key={i} style={{ fontSize: 12, color: C.muted, lineHeight: 1.5 }}>{r}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>

      {/* add rule button / form */}
      <div style={{ marginBottom: 24 }}>
        {!showForm ? (
          <button onClick={() => setShowForm(true)} style={{
            display: "flex", alignItems: "center", gap: 8, padding: "9px 18px", borderRadius: 8,
            border: `1px dashed ${C.teal}88`, background: C.tealDim, color: C.teal, fontSize: 13,
            fontWeight: 600, cursor: "pointer",
          }}>
            <Plus size={14} /> Add Rule
          </button>
        ) : (
          <div style={{ ...card, maxWidth: 560 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <span style={{ fontWeight: 700, color: C.text, fontSize: 14 }}>New Policy Rule</span>
              <button onClick={() => setShowForm(false)} style={{ background: "none", border: "none", color: C.muted, cursor: "pointer" }}><X size={16} /></button>
            </div>
            <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
              <div style={{ flex: 1 }}>
                <label style={{ fontSize: 11, color: C.muted, display: "block", marginBottom: 4 }}>Key</label>
                <input value={formKey} onChange={e => setFormKey(e.target.value)} placeholder="RULE_KEY_NAME"
                  style={{ width: "100%", padding: "8px 12px", borderRadius: 7, border: `1px solid ${C.border}`, background: C.surface2, color: C.text, fontSize: 13, outline: "none", boxSizing: "border-box" }} />
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ fontSize: 11, color: C.muted, display: "block", marginBottom: 4 }}>Value</label>
                <input value={formValue} onChange={e => setFormValue(e.target.value)} placeholder="e.g. 60 or true"
                  style={{ width: "100%", padding: "8px 12px", borderRadius: 7, border: `1px solid ${C.border}`, background: C.surface2, color: C.text, fontSize: 13, outline: "none", boxSizing: "border-box" }} />
              </div>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 11, color: C.muted, display: "block", marginBottom: 4 }}>Justification</label>
              <textarea value={formJustification} onChange={e => setFormJustification(e.target.value)} placeholder="Reason for adding this rule…" rows={3}
                style={{ width: "100%", padding: "8px 12px", borderRadius: 7, border: `1px solid ${C.border}`, background: C.surface2, color: C.text, fontSize: 13, outline: "none", resize: "vertical", boxSizing: "border-box" }} />
            </div>
            <button onClick={handleSave} style={{
              padding: "8px 20px", borderRadius: 8, border: "none", background: saved ? C.green : C.teal,
              color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer", transition: "background 0.2s",
            }}>
              {saved ? "✓ Saved!" : "Save Rule"}
            </button>
          </div>
        )}
      </div>

      {/* rules table */}
      <div style={{ ...card, padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "14px 20px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 8 }}>
          <Settings size={14} color={C.teal} />
          <span style={{ fontWeight: 700, fontSize: 13, color: C.text }}>Active Policy Rules</span>
          <span style={{ fontSize: 11, color: C.muted, background: C.surface2, padding: "2px 8px", borderRadius: 10 }}>{RULES_TABLE.length}</span>
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: C.surface2 }}>
              {["Key", "Value", "Version", "Last Modified", "Author"].map(h => (
                <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.07em" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {RULES_TABLE.map((r, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${C.border}`, background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.01)" }}>
                <td style={{ padding: "10px 16px", fontSize: 12, fontWeight: 600, color: C.teal, fontFamily: "monospace" }}>{r.key}</td>
                <td style={{ padding: "10px 16px", fontSize: 13, color: C.text }}>{r.value}</td>
                <td style={{ padding: "10px 16px" }}>
                  <span style={{ fontSize: 11, color: C.purple, background: C.purpleDim, padding: "2px 8px", borderRadius: 4 }}>{r.version}</span>
                </td>
                <td style={{ padding: "10px 16px", fontSize: 12, color: C.muted }}>{r.modified}</td>
                <td style={{ padding: "10px 16px", fontSize: 12, color: C.muted }}>{r.author}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Audit Tab ──────────────────────────────────────────────────────────────
function AuditTab() {
  const allTypes = ["All", ...Array.from(new Set(AUDIT_EVENTS.map(e => e.type)))];
  const [filter, setFilter] = useState("All");
  const visible = filter === "All" ? AUDIT_EVENTS : AUDIT_EVENTS.filter(e => e.type === filter);

  return (
    <div>
      {/* filter pills */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 24 }}>
        {allTypes.map(t => {
          const cfg = AUDIT_TYPE_COLORS[t];
          const isActive = filter === t;
          return (
            <button key={t} onClick={() => setFilter(t)} style={{
              padding: "5px 14px", borderRadius: 20, fontSize: 11, fontWeight: 700, cursor: "pointer", border: "none",
              background: isActive ? (cfg?.bg ?? C.tealDim) : C.surface2,
              color: isActive ? (cfg?.color ?? C.teal) : C.muted,
              transition: "all 0.15s",
            }}>
              {t}
            </button>
          );
        })}
      </div>

      {/* timeline */}
      <div style={{ position: "relative", paddingLeft: 32 }}>
        {/* vertical line */}
        <div style={{ position: "absolute", left: 8, top: 0, bottom: 0, width: 2, background: C.border }} />
        <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
          {visible.map((ev, i) => {
            const cfg = AUDIT_TYPE_COLORS[ev.type] ?? { color: C.muted, bg: C.surface2 };
            return (
              <div key={i} style={{ position: "relative", paddingBottom: 24 }}>
                {/* dot */}
                <div style={{
                  position: "absolute", left: -28, top: 4, width: 12, height: 12, borderRadius: "50%",
                  background: cfg.color, border: `2px solid ${C.bg}`, boxShadow: `0 0 0 2px ${cfg.color}44`,
                }} />
                <div style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
                  {/* timestamp */}
                  <div style={{ width: 140, flexShrink: 0, fontSize: 11, color: C.teal, paddingTop: 2, fontFamily: "monospace" }}>
                    {ev.ts}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: cfg.color, background: cfg.bg, padding: "3px 8px", borderRadius: 4 }}>{ev.type}</span>
                      <span style={{ fontSize: 12, color: C.muted }}>by {ev.by}</span>
                    </div>
                    <div style={{ fontSize: 13, color: C.text }}>{ev.summary}</div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────
type Tab = "workflows" | "policy" | "audit";

export function ProcessEnginePage() {
  const [tab, setTab] = useState<Tab>("workflows");

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "workflows", label: "Workflows",    icon: <GitBranch size={14} /> },
    { id: "policy",    label: "Policy Rules", icon: <ClipboardList size={14} /> },
    { id: "audit",     label: "Audit",        icon: <History size={14} /> },
  ];

  return (
    <div style={{ minHeight: "100vh", background: C.bg, padding: "32px 40px", fontFamily: "Inter, system-ui, sans-serif" }}>
      {/* header */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
          <Settings size={22} color={C.teal} />
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: C.text }}>Process Engine</h1>
        </div>
        <p style={{ margin: 0, fontSize: 13, color: C.muted }}>Configure workflows, manage policy rules, and audit all process changes.</p>
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

      {tab === "workflows" && <WorkflowsTab />}
      {tab === "policy"    && <PolicyRulesTab />}
      {tab === "audit"     && <AuditTab />}
    </div>
  );
}
