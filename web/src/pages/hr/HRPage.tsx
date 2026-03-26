import { useState } from "react";
import {
  Briefcase, Users, Calendar, TrendingUp, Clock,
  CheckCircle2, BarChart3, Star,
  UserCheck, ChevronRight, Activity,
} from "lucide-react";
import {
  useStaff, usePendingLeave, usePayrollSummary,
  usePendingReviews, useDeptAttendance, useHRInsights, useWorkloadAnalytics,
} from "@/hooks/use-hr";
import type { StaffMember, LeaveRequest } from "@/services/hr";

// ── constants ──────────────────────────────────────────────────

type TabId = "overview" | "staff" | "leave" | "payroll" | "performance";

const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: "overview",    label: "Overview",    icon: <BarChart3 className="w-3.5 h-3.5" /> },
  { id: "staff",       label: "Staff",       icon: <Users className="w-3.5 h-3.5" /> },
  { id: "leave",       label: "Leave",       icon: <Calendar className="w-3.5 h-3.5" /> },
  { id: "payroll",     label: "Payroll",     icon: <TrendingUp className="w-3.5 h-3.5" /> },
  { id: "performance", label: "Performance", icon: <Star className="w-3.5 h-3.5" /> },
];

const TEAL = "#1D9E75";
const TEAL_BG = "rgba(29,158,117,0.08)";
const TEAL_BORDER = "rgba(29,158,117,0.2)";

const DEPT_COLORS = ["#818cf8", "#34d399", "#fbbf24", "#fb7185", "#38bdf8", "#a78bfa", "#f97316"];

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  ACTIVE:      { bg: "rgba(52,211,153,0.1)",  text: "#34d399" },
  ON_LEAVE:    { bg: "rgba(251,191,36,0.1)",  text: "#fbbf24" },
  INACTIVE:    { bg: "rgba(100,116,139,0.1)", text: "#64748b" },
  TERMINATED:  { bg: "rgba(251,113,133,0.1)", text: "#fb7185" },
};

const EMP_COLORS: Record<string, string> = {
  FULL_TIME: "#34d399", PART_TIME: "#818cf8", CONTRACT: "#fbbf24", VISITING: "#38bdf8",
};

const fmtLakh = (n?: number) => {
  if (n == null) return "—";
  if (n >= 100_000) return `₹${(n / 100_000).toFixed(2)}L`;
  if (n >= 1000) return `₹${(n / 1000).toFixed(1)}K`;
  return `₹${n}`;
};

// ── Overview Tab ───────────────────────────────────────────────

function OverviewTab() {
  const { data: insights, isLoading } = useHRInsights();
  const { data: deptData } = useDeptAttendance();
  const { data: payroll } = usePayrollSummary();
  const { data: leaveData } = usePendingLeave();

  const kpis = [
    { label: "Active Staff",  value: insights?.active_staff ?? "—",     sub: `of ${insights?.total_staff ?? "—"} total`, color: TEAL, bg: TEAL_BG, border: TEAL_BORDER, icon: <UserCheck className="w-5 h-5" /> },
    { label: "Departments",   value: insights?.departments ?? "—",       sub: "faculty + admin",     color: "#818cf8", bg: "rgba(99,102,241,0.08)",   border: "rgba(99,102,241,0.2)",  icon: <Briefcase className="w-5 h-5" /> },
    { label: "Leave Pending", value: leaveData?.total ?? "—",            sub: "awaiting approval",   color: "#fbbf24", bg: "rgba(251,191,36,0.08)",   border: "rgba(251,191,36,0.2)",  icon: <Clock className="w-5 h-5" /> },
    { label: "Net Payroll",   value: fmtLakh(payroll?.total_net),        sub: `${payroll?.paid_count ?? 0}P · ${payroll?.pending_count ?? 0} pend`, color: "#34d399", bg: "rgba(52,211,153,0.08)", border: "rgba(52,211,153,0.2)", icon: <TrendingUp className="w-5 h-5" /> },
  ];

  const depts = deptData?.departments ?? [];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-4 gap-4">
        {kpis.map((k) => (
          <div key={k.label} className="rounded-xl p-4 flex gap-3 items-start"
            style={{ background: k.bg, border: `0.5px solid ${k.border}` }}>
            <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ background: `${k.color}18`, color: k.color }}>{k.icon}</div>
            <div>
              <div className="text-[22px] font-bold leading-none mb-1" style={{ color: k.color }}>
                {isLoading ? <span className="opacity-40">—</span> : k.value}
              </div>
              <div className="text-[11px] font-medium" style={{ color: "#94a3b8" }}>{k.label}</div>
              <div className="text-[10px] mt-0.5" style={{ color: "#475569" }}>{k.sub}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-5 gap-4">
        <div className="col-span-3 rounded-xl p-4"
          style={{ background: "rgba(15,23,42,0.6)", border: "0.5px solid rgba(51,65,85,0.5)" }}>
          <div className="text-[11px] font-semibold uppercase tracking-widest mb-4" style={{ color: "#64748b" }}>
            Today's Attendance by Department
          </div>
          {depts.length === 0 ? (
            <div className="h-32 flex items-center justify-center text-[12px]" style={{ color: "#475569" }}>
              No attendance data for today
            </div>
          ) : (
            <div className="space-y-3">
              {depts.map((d, i) => {
                const color = DEPT_COLORS[i % DEPT_COLORS.length];
                const pct = d.attendance_pct ?? 0;
                return (
                  <div key={d.department} className="space-y-1">
                    <div className="flex justify-between items-center">
                      <span className="text-[12px] font-medium" style={{ color: "#e2e8f0" }}>{d.department}</span>
                      <div className="flex items-center gap-3 text-[11px]">
                        <span style={{ color: "#34d399" }}>{d.present_count}P</span>
                        <span style={{ color: "#fbbf24" }}>{d.leave_count}L</span>
                        <span style={{ color: "#fb7185" }}>{d.absent_count}A</span>
                        <span className="font-bold" style={{ color }}>{pct.toFixed(0)}%</span>
                      </div>
                    </div>
                    <div className="h-1.5 rounded-full" style={{ background: "rgba(30,41,59,0.8)" }}>
                      <div className="h-full rounded-full transition-all duration-700"
                        style={{ width: `${pct}%`, background: color }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="col-span-2 rounded-xl p-4"
          style={{ background: "rgba(15,23,42,0.6)", border: "0.5px solid rgba(51,65,85,0.5)" }}>
          <div className="flex items-center gap-2 mb-4">
            <div className="w-2 h-2 rounded-full" style={{ background: TEAL }} />
            <div className="text-[11px] font-semibold uppercase tracking-widest" style={{ color: "#64748b" }}>
              ALIS Agent — HR Brief
            </div>
          </div>
          {insights?.insights?.length ? (
            <div className="space-y-2.5">
              {insights.insights.map((line, i) => (
                <div key={i} className="flex gap-2 items-start">
                  <ChevronRight className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" style={{ color: TEAL }} />
                  <p className="text-[12px] leading-relaxed" style={{ color: "#94a3b8" }}>{line}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-2.5">
              {["Staff attendance and leave tracked daily by department", "Payroll auto-generated from attendance + leave deduction rules", "Performance reviews triggered annually with 360° feedback"].map((line, i) => (
                <div key={i} className="flex gap-2 items-start opacity-50">
                  <ChevronRight className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" style={{ color: TEAL }} />
                  <p className="text-[12px] leading-relaxed" style={{ color: "#94a3b8" }}>{line}</p>
                </div>
              ))}
            </div>
          )}
          <div className="mt-4 pt-3" style={{ borderTop: "0.5px solid rgba(51,65,85,0.4)" }}>
            <div className="text-[10px] font-semibold uppercase tracking-widest mb-2" style={{ color: "#64748b" }}>Leave Utilization</div>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-2 rounded-full" style={{ background: "rgba(30,41,59,0.8)" }}>
                <div className="h-full rounded-full"
                  style={{ width: `${insights?.avg_leave_utilization ?? 0}%`, background: `linear-gradient(90deg, ${TEAL}, #34d399)` }} />
              </div>
              <span className="text-[11px] font-semibold" style={{ color: TEAL }}>
                {insights?.avg_leave_utilization?.toFixed(0) ?? "—"}%
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Staff Tab ──────────────────────────────────────────────────

function StaffTab() {
  const [status, setStatus] = useState<string>("ACTIVE");
  const { data, isLoading } = useStaff(undefined, status || undefined);
  const staff = data?.staff ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {["", "ACTIVE", "ON_LEAVE", "INACTIVE"].map((s) => (
          <button key={s} onClick={() => setStatus(s)}
            className="px-2.5 py-1 rounded text-[11px] font-medium transition-all"
            style={{
              background: status === s ? TEAL_BG : "rgba(30,41,59,0.6)",
              color: status === s ? TEAL : "#64748b",
              border: `0.5px solid ${status === s ? TEAL_BORDER : "rgba(51,65,85,0.4)"}`,
            }}>
            {s || "All"}
          </button>
        ))}
      </div>
      <div className="rounded-xl overflow-hidden" style={{ border: "0.5px solid rgba(51,65,85,0.5)" }}>
        <table className="w-full">
          <thead>
            <tr style={{ background: "rgba(15,23,42,0.8)" }}>
              {["Employee", "Code", "Department", "Designation", "Type", "Join Date", "Status"].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: "#475569" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? [...Array(5)].map((_, i) => (
              <tr key={i} style={{ borderTop: "0.5px solid rgba(51,65,85,0.3)" }}>
                {[...Array(7)].map((_, j) => (
                  <td key={j} className="px-4 py-3">
                    <div className="h-4 rounded animate-pulse" style={{ background: "rgba(51,65,85,0.4)", width: "75%" }} />
                  </td>
                ))}
              </tr>
            )) : staff.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-10 text-center text-[12px]" style={{ color: "#475569" }}>No staff found</td></tr>
            ) : staff.map((s: StaffMember) => {
              const sc = STATUS_COLORS[s.status] ?? STATUS_COLORS.INACTIVE;
              return (
                <tr key={s.id} style={{ borderTop: "0.5px solid rgba(51,65,85,0.3)" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(30,41,59,0.5)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                  <td className="px-4 py-3">
                    <div className="text-[12px] font-medium" style={{ color: "#e2e8f0" }}>{s.display_name || s.user_id}</div>
                    <div className="text-[10px]" style={{ color: "#64748b" }}>{s.email}</div>
                  </td>
                  <td className="px-4 py-3 text-[11px] font-mono" style={{ color: "#64748b" }}>{s.employee_code}</td>
                  <td className="px-4 py-3 text-[12px]" style={{ color: "#94a3b8" }}>{s.department}</td>
                  <td className="px-4 py-3 text-[11px]" style={{ color: "#94a3b8" }}>{s.designation}</td>
                  <td className="px-4 py-3">
                    <span className="text-[10px] font-semibold"
                      style={{ color: EMP_COLORS[s.employment_type] ?? "#64748b" }}>
                      {s.employment_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-[11px]" style={{ color: "#64748b" }}>{s.join_date}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded text-[10px] font-semibold"
                      style={{ background: sc.bg, color: sc.text }}>{s.status}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!isLoading && <div className="text-[11px]" style={{ color: "#475569" }}>{data?.total ?? 0} staff members</div>}
    </div>
  );
}

// ── Leave Modal ────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

function LeaveModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [form, setForm] = useState({ leave_type: "CASUAL", from_date: "", to_date: "", reason: "" });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const submit = async (e: { preventDefault: () => void }) => {
    e.preventDefault();
    setSaving(true);
    setErr("");
    try {
      const token = localStorage.getItem("token");
      const r = await fetch(`${API_BASE}/hr/leave`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify(form),
      });
      if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || "Failed"); }
      onDone();
      onClose();
    } catch (ex: unknown) { setErr(ex instanceof Error ? ex.message : "Failed to submit"); }
    finally { setSaving(false); }
  };

  const inp: React.CSSProperties = {
    width: "100%", padding: "8px 12px", borderRadius: 8,
    background: "rgba(255,255,255,0.04)", border: "1px solid rgba(51,65,85,0.6)",
    color: "#e2e8f0", fontSize: 13, outline: "none", boxSizing: "border-box",
  };

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 400 }} />
      <div style={{ position: "fixed", top: "50%", left: "50%", transform: "translate(-50%,-50%)", width: 440, background: "#0f172a", border: "1px solid rgba(51,65,85,0.7)", borderRadius: 14, padding: 24, zIndex: 401 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
          <span style={{ fontSize: 15, fontWeight: 600, color: "#e2e8f0" }}>Apply for Leave</span>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "#64748b", cursor: "pointer", fontSize: 18, lineHeight: 1 }}>✕</button>
        </div>
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <label style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", display: "block", marginBottom: 6 }}>Leave Type</label>
            <select value={form.leave_type} onChange={(e) => setForm((f) => ({ ...f, leave_type: e.target.value }))} style={{ ...inp, cursor: "pointer" }}>
              {["CASUAL", "SICK", "EARNED", "MATERNITY", "PATERNITY", "COMPENSATORY"].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", display: "block", marginBottom: 6 }}>From Date</label>
              <input type="date" required value={form.from_date} onChange={(e) => setForm((f) => ({ ...f, from_date: e.target.value }))} style={inp} />
            </div>
            <div>
              <label style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", display: "block", marginBottom: 6 }}>To Date</label>
              <input type="date" required value={form.to_date} onChange={(e) => setForm((f) => ({ ...f, to_date: e.target.value }))} style={inp} />
            </div>
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", display: "block", marginBottom: 6 }}>Reason</label>
            <textarea required rows={3} value={form.reason} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} style={{ ...inp, resize: "vertical" }} placeholder="Brief reason for leave…" />
          </div>
          {err && <div style={{ padding: "8px 12px", borderRadius: 8, background: "rgba(251,113,133,0.08)", border: "1px solid rgba(251,113,133,0.2)", color: "#fb7185", fontSize: 12 }}>{err}</div>}
          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 4 }}>
            <button type="button" onClick={onClose} style={{ padding: "8px 18px", borderRadius: 8, background: "transparent", border: "1px solid rgba(51,65,85,0.6)", color: "#94a3b8", fontSize: 13, cursor: "pointer" }}>Cancel</button>
            <button type="submit" disabled={saving} style={{ padding: "8px 18px", borderRadius: 8, background: TEAL_BG, border: `0.5px solid ${TEAL_BORDER}`, color: TEAL, fontSize: 13, fontWeight: 600, cursor: saving ? "not-allowed" : "pointer" }}>
              {saving ? "Submitting…" : "Submit Request"}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}

// ── Leave Tab ──────────────────────────────────────────────────

function LeaveTab() {
  const { data, isLoading, refetch } = usePendingLeave();
  const [showModal, setShowModal] = useState(false);
  const requests = data?.leave_requests ?? [];
  const statusConfig: Record<string, { bg: string; text: string }> = {
    PENDING:   { bg: "rgba(251,191,36,0.1)",  text: "#fbbf24" },
    APPROVED:  { bg: "rgba(52,211,153,0.1)",  text: "#34d399" },
    REJECTED:  { bg: "rgba(251,113,133,0.1)", text: "#fb7185" },
    CANCELLED: { bg: "rgba(100,116,139,0.1)", text: "#64748b" },
  };
  return (
    <div className="space-y-4">
      {showModal && <LeaveModal onClose={() => setShowModal(false)} onDone={refetch} />}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 px-4 py-2.5 rounded-xl"
          style={{ background: "rgba(251,191,36,0.06)", border: "0.5px solid rgba(251,191,36,0.2)" }}>
          <Clock className="w-4 h-4" style={{ color: "#fbbf24" }} />
          <span className="text-[12px]" style={{ color: "#fbbf24" }}>
            {isLoading ? "..." : `${data?.total ?? 0} pending`} leave requests
          </span>
        </div>
        <button onClick={() => setShowModal(true)}
          style={{ padding: "6px 14px", borderRadius: 8, background: TEAL_BG, border: `0.5px solid ${TEAL_BORDER}`, color: TEAL, fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
          + Apply for Leave
        </button>
      </div>
      <div className="rounded-xl overflow-hidden" style={{ border: "0.5px solid rgba(51,65,85,0.5)" }}>
        <table className="w-full">
          <thead>
            <tr style={{ background: "rgba(15,23,42,0.8)" }}>
              {["Staff Member", "Leave Type", "From", "To", "Days", "Reason", "Applied", "Status"].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: "#475569" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? [...Array(4)].map((_, i) => (
              <tr key={i} style={{ borderTop: "0.5px solid rgba(51,65,85,0.3)" }}>
                {[...Array(8)].map((_, j) => (
                  <td key={j} className="px-4 py-3">
                    <div className="h-4 rounded animate-pulse" style={{ background: "rgba(51,65,85,0.4)", width: "70%" }} />
                  </td>
                ))}
              </tr>
            )) : requests.length === 0 ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-[12px]" style={{ color: "#475569" }}>
                <CheckCircle2 className="w-6 h-6 mx-auto mb-2" style={{ color: TEAL, opacity: 0.5 }} />
                No pending leave requests
              </td></tr>
            ) : requests.map((r: LeaveRequest) => {
              const sc = statusConfig[r.status] ?? statusConfig.PENDING;
              return (
                <tr key={r.id} style={{ borderTop: "0.5px solid rgba(51,65,85,0.3)" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(30,41,59,0.5)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                  <td className="px-4 py-3 text-[12px]" style={{ color: "#e2e8f0" }}>{r.staff_name || r.staff_id}</td>
                  <td className="px-4 py-3 text-[11px]" style={{ color: "#94a3b8" }}>{r.leave_type_name}</td>
                  <td className="px-4 py-3 text-[11px]" style={{ color: "#94a3b8" }}>{r.from_date}</td>
                  <td className="px-4 py-3 text-[11px]" style={{ color: "#94a3b8" }}>{r.to_date}</td>
                  <td className="px-4 py-3 text-[12px] font-semibold" style={{ color: "#e2e8f0" }}>{r.days}</td>
                  <td className="px-4 py-3 text-[11px] max-w-[140px] truncate" style={{ color: "#64748b" }}>{r.reason}</td>
                  <td className="px-4 py-3 text-[11px]" style={{ color: "#64748b" }}>{r.applied_at?.split("T")[0]}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded text-[10px] font-semibold"
                      style={{ background: sc.bg, color: sc.text }}>{r.status}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Payroll Tab ────────────────────────────────────────────────

function PayrollTab() {
  const { data: payroll, isLoading } = usePayrollSummary();
  const cards = [
    { label: "Gross",       value: fmtLakh(payroll?.total_gross),       color: "#818cf8" },
    { label: "Deductions",  value: fmtLakh(payroll?.total_deductions),  color: "#fb7185" },
    { label: "Net",         value: fmtLakh(payroll?.total_net),         color: TEAL      },
    { label: "Paid",        value: payroll?.paid_count ?? "—",          color: "#34d399" },
    { label: "Pending",     value: payroll?.pending_count ?? "—",       color: "#fbbf24" },
  ];
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-5 gap-4">
        {cards.map((c) => (
          <div key={c.label} className="rounded-xl p-4"
            style={{ background: `${c.color}08`, border: `0.5px solid ${c.color}22` }}>
            <div className="text-[20px] font-bold" style={{ color: c.color }}>
              {isLoading ? "—" : c.value}
            </div>
            <div className="text-[11px] mt-0.5" style={{ color: "#94a3b8" }}>{c.label}</div>
          </div>
        ))}
      </div>
      <div className="rounded-xl p-4"
        style={{ background: "rgba(15,23,42,0.6)", border: "0.5px solid rgba(51,65,85,0.5)" }}>
        <div className="text-[11px] font-semibold uppercase tracking-widest mb-4" style={{ color: "#64748b" }}>
          Payroll Pipeline
        </div>
        <div className="grid grid-cols-5 gap-3">
          {[
            { step: "1", title: "Attendance",    desc: "LOP from register",          color: "#818cf8" },
            { step: "2", title: "Leave LOP",     desc: "Unapproved absences",        color: "#38bdf8" },
            { step: "3", title: "CTC Components",desc: "Basic+HRA+TA+allowances",    color: TEAL      },
            { step: "4", title: "Statutory",     desc: "PF+ESI+PT+TDS",             color: "#fbbf24" },
            { step: "5", title: "Disbursement",  desc: "Bank transfer + payslip",    color: "#34d399" },
          ].map((s) => (
            <div key={s.step} className="p-3 rounded-xl"
              style={{ background: `${s.color}08`, border: `0.5px solid ${s.color}20` }}>
              <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold mb-2"
                style={{ background: `${s.color}18`, color: s.color }}>{s.step}</div>
              <div className="text-[12px] font-semibold mb-1" style={{ color: "#e2e8f0" }}>{s.title}</div>
              <div className="text-[10px]" style={{ color: "#64748b" }}>{s.desc}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="rounded-xl p-4"
        style={{ background: "rgba(15,23,42,0.6)", border: "0.5px solid rgba(51,65,85,0.5)" }}>
        <div className="text-[11px] font-semibold uppercase tracking-widest mb-3" style={{ color: "#64748b" }}>Statutory Deductions</div>
        <div className="grid grid-cols-4 gap-3">
          {[
            { name: "EPF",  rule: "12% employee + 13.16% employer of Basic",       color: "#818cf8" },
            { name: "ESI",  rule: "0.75%+3.25% if CTC ≤ ₹21K/mo",                color: "#38bdf8" },
            { name: "PT",   rule: "₹200/mo if salary > ₹15K (state-specific)",    color: "#fbbf24" },
            { name: "TDS",  rule: "Per IT slab after 80C/HRA declarations",        color: "#fb7185" },
          ].map((d) => (
            <div key={d.name} className="p-3 rounded-lg"
              style={{ background: `${d.color}08`, border: `0.5px solid ${d.color}20` }}>
              <div className="text-[13px] font-bold mb-1" style={{ color: d.color }}>{d.name}</div>
              <div className="text-[10px] leading-relaxed" style={{ color: "#64748b" }}>{d.rule}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Performance Tab ────────────────────────────────────────────

function PerformanceTab() {
  const { data: reviewData, isLoading } = usePendingReviews();
  const { data: workloadData } = useWorkloadAnalytics();
  const reviews = reviewData?.reviews ?? [];
  const workload = workloadData?.staff ?? [];
  const ratingColor = (r: number) => r >= 4.5 ? "#34d399" : r >= 3.5 ? TEAL : r >= 2.5 ? "#fbbf24" : "#fb7185";
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-1 rounded-xl p-4"
          style={{ background: TEAL_BG, border: `0.5px solid ${TEAL_BORDER}` }}>
          <div className="flex items-center gap-2 mb-3">
            <Activity className="w-4 h-4" style={{ color: TEAL }} />
            <div className="text-[11px] font-semibold uppercase tracking-widest" style={{ color: "#64748b" }}>CAS Compliance</div>
          </div>
          <div className="space-y-2">
            {["API Score > 75 required for promotion", "Annual 360° review cycle", "PBAS portfolio submission", "Faculty development points tracked"].map((item) => (
              <div key={item} className="flex gap-2 items-start">
                <CheckCircle2 className="w-3 h-3 mt-0.5 flex-shrink-0" style={{ color: TEAL }} />
                <span className="text-[11px]" style={{ color: "#94a3b8" }}>{item}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="col-span-2 rounded-xl p-4"
          style={{ background: "rgba(15,23,42,0.6)", border: "0.5px solid rgba(51,65,85,0.5)" }}>
          <div className="text-[11px] font-semibold uppercase tracking-widest mb-3" style={{ color: "#64748b" }}>
            Pending Reviews ({reviewData?.total ?? 0})
          </div>
          {isLoading ? [...Array(3)].map((_, i) => (
            <div key={i} className="h-12 rounded-lg mb-2 animate-pulse" style={{ background: "rgba(51,65,85,0.3)" }} />
          )) : reviews.length === 0 ? (
            <div className="text-center py-6 text-[12px]" style={{ color: "#475569" }}>No pending reviews</div>
          ) : reviews.slice(0, 5).map((r) => (
            <div key={r.id} className="flex items-center justify-between py-2"
              style={{ borderBottom: "0.5px solid rgba(51,65,85,0.3)" }}>
              <div>
                <div className="text-[12px] font-medium" style={{ color: "#e2e8f0" }}>{r.staff_name || r.staff_id}</div>
                <div className="text-[10px]" style={{ color: "#64748b" }}>
                  {r.review_period} · by {r.reviewer_name || r.reviewer_id}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {r.overall_rating > 0 && (
                  <span className="text-[13px] font-bold" style={{ color: ratingColor(r.overall_rating) }}>
                    {r.overall_rating.toFixed(1)}
                  </span>
                )}
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold"
                  style={{ background: "rgba(251,191,36,0.1)", color: "#fbbf24" }}>{r.status}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
      {workload.length > 0 && (
        <div className="rounded-xl p-4"
          style={{ background: "rgba(15,23,42,0.6)", border: "0.5px solid rgba(51,65,85,0.5)" }}>
          <div className="text-[11px] font-semibold uppercase tracking-widest mb-3" style={{ color: "#64748b" }}>Faculty Workload</div>
          <div className="space-y-2">
            {workload.slice(0, 8).map((s) => (
              <div key={s.staff_id} className="flex items-center gap-3">
                <div className="text-[12px] w-40 flex-shrink-0" style={{ color: "#e2e8f0" }}>{s.staff_name}</div>
                <div className="text-[11px] w-16 flex-shrink-0" style={{ color: "#64748b" }}>{s.courses} courses</div>
                <div className="flex-1 h-2 rounded-full" style={{ background: "rgba(30,41,59,0.8)" }}>
                  <div className="h-full rounded-full"
                    style={{
                      width: `${Math.min(s.workload_score, 100)}%`,
                      background: s.workload_score > 80 ? "#fb7185" : s.workload_score > 60 ? "#fbbf24" : TEAL,
                    }} />
                </div>
                <div className="text-[11px] w-8 text-right" style={{ color: "#64748b" }}>{s.workload_score}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────

export default function HRPage() {
  const [tab, setTab] = useState<TabId>("overview");
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex-shrink-0 px-6 pt-5 pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: "rgba(244,114,182,0.1)", border: "0.5px solid rgba(244,114,182,0.2)" }}>
              <Briefcase className="w-4.5 h-4.5" style={{ color: "#f472b6" }} />
            </div>
            <div>
              <h1 className="text-[18px] font-bold leading-none" style={{ color: "#e2e8f0" }}>HR &amp; Staff</h1>
              <p className="text-[11px] mt-0.5" style={{ color: "#64748b" }}>
                E08 · Attendance · Leave · Payroll · Performance
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-[11px]"
            style={{ background: TEAL_BG, border: `0.5px solid ${TEAL_BORDER}`, color: TEAL }}>
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: TEAL }} />
            ALIS Agent Active
          </div>
        </div>
        <div className="flex items-center gap-1 mt-4">
          {tabs.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all"
              style={{
                background: tab === t.id ? TEAL_BG : "transparent",
                color: tab === t.id ? TEAL : "#64748b",
                border: `0.5px solid ${tab === t.id ? TEAL_BORDER : "transparent"}`,
              }}>
              {t.icon}{t.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        {tab === "overview"    && <OverviewTab />}
        {tab === "staff"       && <StaffTab />}
        {tab === "leave"       && <LeaveTab />}
        {tab === "payroll"     && <PayrollTab />}
        {tab === "performance" && <PerformanceTab />}
      </div>
    </div>
  );
}
