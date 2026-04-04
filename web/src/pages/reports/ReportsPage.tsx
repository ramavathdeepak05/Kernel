import {
  BarChart2, TrendingUp, BookOpen, DollarSign,
  Download, FileText, Cpu, RefreshCw,
} from "lucide-react";
import { ALISTabs, ALISTabsList, ALISTabsTrigger, ALISTabsContent } from "@/components/ui/alis-tabs";
import {
  useDashboardKPIs, useAdmissionsFunnel, useAdmissionsPrograms,
  useAcademicsAttendance, useFacultyWorkload,
  useFinanceYoY, useFinanceAging,
  useSavedReports, useExports, useAISummary,
} from "@/hooks/use-reporting";
import type { SavedReport, ExportRecord, AIInsight } from "@/services/reporting";

// ── Constants ──────────────────────────────────────────────────

type TabId = "overview" | "admissions" | "academics" | "finance" | "saved";

const TEAL        = "#1D9E75";
const TEAL_BG     = "rgba(29,158,117,0.08)";
const TEAL_BORDER = "rgba(29,158,117,0.2)";

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: "overview",   label: "Overview",   icon: <BarChart2 className="w-3.5 h-3.5" /> },
  { id: "admissions", label: "Admissions", icon: <TrendingUp className="w-3.5 h-3.5" /> },
  { id: "academics",  label: "Academics",  icon: <BookOpen className="w-3.5 h-3.5" /> },
  { id: "finance",    label: "Finance",    icon: <DollarSign className="w-3.5 h-3.5" /> },
  { id: "saved",      label: "Saved & exports", icon: <Download className="w-3.5 h-3.5" /> },
];

const SEVERITY_BADGE: Record<string, { bg: string; color: string }> = {
  info:     { bg: "#E6F1FB", color: "#185FA5" },
  warning:  { bg: "#FAEEDA", color: "#854F0B" },
  critical: { bg: "#FCEBEB", color: "#A32D2D" },
};

const EXPORT_STATUS: Record<string, { bg: string; color: string }> = {
  READY:      { bg: "#EAF3DE", color: "#3B6D11" },
  PENDING:    { bg: "#FAEEDA", color: "#854F0B" },
  PROCESSING: { bg: TEAL_BG, color: TEAL },
  FAILED:     { bg: "#FCEBEB", color: "#A32D2D" },
};

function Badge({ s, children }: { s: { bg: string; color: string }; children: React.ReactNode }) {
  return (
    <span style={{
      display: "inline-block", padding: "2px 7px", borderRadius: 20,
      fontSize: 10, fontWeight: 500, background: s.bg, color: s.color,
    }}>
      {children}
    </span>
  );
}

const fmtCr = (n?: number) => {
  if (n == null) return "—";
  if (n >= 1_00_00_000) return `₹${(n / 1_00_00_000).toFixed(2)}Cr`;
  if (n >= 1_00_000) return `₹${(n / 1_00_000).toFixed(1)}L`;
  if (n >= 1000) return `₹${(n / 1000).toFixed(1)}K`;
  return `₹${n}`;
};

const DEPT_COLORS = ["#1D9E75", "#818cf8", "#fbbf24", "#fb7185", "#38bdf8", "#a78bfa", "#f97316"];

// ── Overview tab ───────────────────────────────────────────────

function OverviewTab() {
  const { data: kpis } = useDashboardKPIs();
  const { data: ai } = useAISummary();

  const stats = [
    { label: "Total students",    value: kpis?.total_students ?? "—",      sub: "enrolled", color: TEAL,     bg: TEAL_BG,                  border: TEAL_BORDER, icon: <BookOpen className="w-5 h-5" /> },
    { label: "Active faculty",    value: kpis?.active_faculty ?? "—",      sub: "staff",    color: "#818cf8", bg: "rgba(99,102,241,0.08)",  border: "rgba(99,102,241,0.2)", icon: <FileText className="w-5 h-5" /> },
    { label: "Avg attendance",    value: kpis?.avg_attendance_pct != null ? `${kpis.avg_attendance_pct.toFixed(1)}%` : "—", sub: "institution-wide", color: "#34d399", bg: "rgba(52,211,153,0.08)", border: "rgba(52,211,153,0.2)", icon: <TrendingUp className="w-5 h-5" /> },
    { label: "Pending approvals", value: kpis?.pending_approvals ?? "—",   sub: "in queue", color: "#fbbf24", bg: "rgba(251,191,36,0.08)", border: "rgba(251,191,36,0.2)", icon: <BarChart2 className="w-5 h-5" /> },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* KPIs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 8 }}>
        {stats.map(k => (
          <div key={k.label} style={{
            background: "var(--color-background-secondary, #0f1c2e)",
            border: `0.5px solid ${k.border}`, borderRadius: 8, padding: "10px 12px",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)", fontWeight: 500 }}>{k.label}</p>
              <span style={{ color: k.color, opacity: 0.7 }}>{k.icon}</span>
            </div>
            <p style={{ fontSize: 22, fontWeight: 500, color: k.color }}>{k.value}</p>
            <p style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)", marginTop: 2 }}>{k.sub}</p>
          </div>
        ))}
      </div>

      {/* Additional KPIs row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 8 }}>
        {[
          { label: "Fee collected (month)", value: fmtCr(kpis?.fee_collected_month),       color: "#34d399" },
          { label: "Fee collected (YTD)",   value: fmtCr(kpis?.fee_collected_ytd),         color: "#34d399" },
          { label: "At-risk students",      value: kpis?.at_risk_students ?? "—",          color: "#fb7185" },
          { label: "Exams this week",       value: kpis?.exams_this_week ?? "—",           color: "#fbbf24" },
        ].map(k => (
          <div key={k.label} style={{
            background: "var(--color-background-secondary, #0f1c2e)",
            border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))",
            borderRadius: 8, padding: "10px 12px",
          }}>
            <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)", fontWeight: 500, marginBottom: 4 }}>{k.label}</p>
            <p style={{ fontSize: 20, fontWeight: 500, color: k.color }}>{k.value}</p>
          </div>
        ))}
      </div>

      {/* AI insights */}
      <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
        <div style={{ padding: "9px 12px", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", background: "var(--color-background-secondary, #0f1c2e)", display: "flex", gap: 6, alignItems: "center" }}>
          <Cpu className="w-3.5 h-3.5" style={{ color: TEAL }} />
          <p style={{ fontSize: 11, fontWeight: 500 }}>Institution-wide AI insights</p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
          {(ai ?? []).map((insight: AIInsight, i, arr) => {
            const bs = SEVERITY_BADGE[insight.severity] ?? SEVERITY_BADGE.info;
            return (
              <div key={i} style={{
                padding: "10px 12px",
                borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
                borderLeft: insight.severity === "critical" ? "2.5px solid #E24B4A" : insight.severity === "warning" ? "2.5px solid #EF9F27" : "2.5px solid transparent",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <p style={{ fontSize: 12, fontWeight: 500, marginBottom: 2 }}>{insight.category}</p>
                    <p style={{ fontSize: 11, color: "var(--color-text-secondary, #94a3b8)", lineHeight: 1.5 }}>{insight.insight}</p>
                    {insight.suggested_action && (
                      <p style={{ fontSize: 10, color: TEAL, marginTop: 4 }}>→ {insight.suggested_action}</p>
                    )}
                  </div>
                  <Badge s={bs}>{insight.severity}</Badge>
                </div>
              </div>
            );
          })}
          {!ai?.length && (
            <div style={{ padding: "16px 12px", textAlign: "center", fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>
              AI summary loading…
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Admissions reports tab ─────────────────────────────────────

function AdmissionsTab() {
  const { data: funnel } = useAdmissionsFunnel();
  const { data: programs } = useAdmissionsPrograms();

  const maxFunnelCount = Math.max(...(funnel ?? []).map(f => f.count), 1);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Funnel */}
      <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
        <div style={{ padding: "9px 12px", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", background: "var(--color-background-secondary, #0f1c2e)" }}>
          <p style={{ fontSize: 11, fontWeight: 500 }}>Admissions funnel</p>
        </div>
        <div style={{ padding: "12px", display: "flex", flexDirection: "column", gap: 8 }}>
          {(funnel ?? []).map(f => (
            <div key={f.stage}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                <span style={{ fontSize: 11, fontWeight: 500 }}>{f.stage}</span>
                <div style={{ display: "flex", gap: 8 }}>
                  <span style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>{f.count}</span>
                  <span style={{ fontSize: 11, fontWeight: 500, color: f.conversion_rate >= 50 ? TEAL : "#fbbf24" }}>{f.conversion_rate.toFixed(1)}%</span>
                </div>
              </div>
              <div style={{ height: 6, borderRadius: 3, background: "rgba(255,255,255,0.06)" }}>
                <div style={{ width: `${(f.count / maxFunnelCount) * 100}%`, height: "100%", borderRadius: 3, background: TEAL }} />
              </div>
            </div>
          ))}
          {!funnel?.length && <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>No funnel data</p>}
        </div>
      </div>

      {/* Program breakdown */}
      <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
        <div style={{ padding: "9px 12px", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", background: "var(--color-background-secondary, #0f1c2e)" }}>
          <p style={{ fontSize: 11, fontWeight: 500 }}>Program-wise enrollment vs target</p>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 80px 80px 80px", padding: "6px 12px", background: "var(--color-background-secondary, #0f1c2e)", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" }}>
          {["Program", "Applied", "Enrolled", "Target"].map(h => (
            <span key={h} style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary, #64748b)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{h}</span>
          ))}
        </div>
        {(programs ?? []).map((p, i, arr) => {
          const fillPct = p.target > 0 ? Math.round((p.enrolled / p.target) * 100) : 0;
          const fillColor = fillPct >= 90 ? TEAL : fillPct >= 60 ? "#fbbf24" : "#fb7185";
          return (
            <div key={p.program} style={{
              display: "grid", gridTemplateColumns: "2fr 80px 80px 80px", padding: "8px 12px", alignItems: "center",
              borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
            }}>
              <p style={{ fontSize: 12, fontWeight: 500 }}>{p.program}</p>
              <p style={{ fontSize: 12 }}>{p.applied}</p>
              <p style={{ fontSize: 12, fontWeight: 500, color: fillColor }}>{p.enrolled}</p>
              <p style={{ fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>{p.target}</p>
            </div>
          );
        })}
        {!programs?.length && (
          <div style={{ padding: "16px 12px", textAlign: "center", fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>No program data</div>
        )}
      </div>
    </div>
  );
}

// ── Academics reports tab ──────────────────────────────────────

function AcademicsTab() {
  const { data: attendance } = useAcademicsAttendance();
  const { data: workload } = useFacultyWorkload();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Attendance by dept */}
      <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
        <div style={{ padding: "9px 12px", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", background: "var(--color-background-secondary, #0f1c2e)" }}>
          <p style={{ fontSize: 11, fontWeight: 500 }}>Department attendance</p>
        </div>
        <div style={{ padding: "12px", display: "flex", flexDirection: "column", gap: 8 }}>
          {(attendance ?? []).map((d, idx) => {
            const pct = d.avg_attendance;
            const color = pct >= 75 ? TEAL : pct >= 60 ? "#fbbf24" : "#fb7185";
            const riskColor = d.below_75_count > 20 ? "#fb7185" : d.below_75_count > 10 ? "#fbbf24" : "var(--color-text-secondary, #64748b)";
            return (
              <div key={d.department}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: DEPT_COLORS[idx % DEPT_COLORS.length], display: "inline-block" }} />
                    <span style={{ fontSize: 11, fontWeight: 500 }}>{d.department}</span>
                  </div>
                  <div style={{ display: "flex", gap: 12 }}>
                    <span style={{ fontSize: 10, color: riskColor }}>{d.below_75_count} at risk</span>
                    <span style={{ fontSize: 11, fontWeight: 500, color }}>{pct.toFixed(1)}%</span>
                  </div>
                </div>
                <div style={{ height: 4, borderRadius: 2, background: "rgba(255,255,255,0.06)" }}>
                  <div style={{ width: `${pct}%`, height: "100%", borderRadius: 2, background: color }} />
                </div>
              </div>
            );
          })}
          {!attendance?.length && <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>No attendance data</p>}
        </div>
      </div>

      {/* Faculty workload */}
      <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
        <div style={{ padding: "9px 12px", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", background: "var(--color-background-secondary, #0f1c2e)" }}>
          <p style={{ fontSize: 11, fontWeight: 500 }}>Faculty workload</p>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 60px 70px 80px", padding: "6px 12px", background: "var(--color-background-secondary, #0f1c2e)", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" }}>
          {["Faculty", "Courses", "Students", "Hrs/week"].map(h => (
            <span key={h} style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary, #64748b)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{h}</span>
          ))}
        </div>
        {(workload ?? []).slice(0, 10).map((f, i, arr) => {
          const overload = f.hours_per_week > 20;
          return (
            <div key={f.name} style={{
              display: "grid", gridTemplateColumns: "2fr 60px 70px 80px", padding: "8px 12px", alignItems: "center",
              borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
            }}>
              <p style={{ fontSize: 12, fontWeight: 500 }}>{f.name}</p>
              <p style={{ fontSize: 12 }}>{f.courses}</p>
              <p style={{ fontSize: 12 }}>{f.students}</p>
              <p style={{ fontSize: 12, fontWeight: 500, color: overload ? "#fb7185" : "var(--color-text-primary, #e2e8f0)" }}>{f.hours_per_week}h</p>
            </div>
          );
        })}
        {!workload?.length && (
          <div style={{ padding: "16px 12px", textAlign: "center", fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>No workload data</div>
        )}
      </div>
    </div>
  );
}

// ── Finance reports tab ────────────────────────────────────────

function FinanceTab() {
  const { data: yoy } = useFinanceYoY();
  const { data: aging } = useFinanceAging();

  const maxYoy = Math.max(...(yoy ?? []).map(y => y.target), 1);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Year-over-year */}
      <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
        <div style={{ padding: "9px 12px", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", background: "var(--color-background-secondary, #0f1c2e)" }}>
          <p style={{ fontSize: 11, fontWeight: 500 }}>Fee collection — year over year</p>
        </div>
        <div style={{ padding: "12px 12px 8px", display: "flex", flexDirection: "column", gap: 12 }}>
          {(yoy ?? []).map((y, idx) => {
            const collectedPct = y.target > 0 ? (y.collected / y.target) * 100 : 0;
            const barColor = DEPT_COLORS[idx % DEPT_COLORS.length];
            return (
              <div key={y.year}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontSize: 11, fontWeight: 500 }}>{y.year}</span>
                  <div style={{ display: "flex", gap: 12 }}>
                    <span style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>Target: {fmtCr(y.target)}</span>
                    <span style={{ fontSize: 11, fontWeight: 500, color: collectedPct >= 90 ? TEAL : "#fbbf24" }}>
                      {fmtCr(y.collected)} ({collectedPct.toFixed(1)}%)
                    </span>
                    {y.defaulters > 0 && (
                      <span style={{ fontSize: 10, color: "#fb7185" }}>{y.defaulters} defaulters</span>
                    )}
                  </div>
                </div>
                <div style={{ display: "flex", height: 8, gap: 1, borderRadius: 4, overflow: "hidden" }}>
                  <div style={{ flex: y.collected, background: barColor, minWidth: 2 }} />
                  <div style={{ flex: Math.max(0, y.target - y.collected), background: "rgba(255,255,255,0.06)" }} />
                </div>
              </div>
            );
          })}
          {!yoy?.length && <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>No year-over-year data</p>}
        </div>
      </div>

      {/* Aging analysis */}
      <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
        <div style={{ padding: "9px 12px", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", background: "var(--color-background-secondary, #0f1c2e)" }}>
          <p style={{ fontSize: 11, fontWeight: 500 }}>Dues aging analysis</p>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 80px 1fr", padding: "6px 12px", background: "var(--color-background-secondary, #0f1c2e)", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" }}>
          {["Overdue bucket", "Count", "Amount due"].map(h => (
            <span key={h} style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary, #64748b)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{h}</span>
          ))}
        </div>
        {(aging ?? []).map((a, i, arr) => {
          const isOld = a.bucket.includes("90") || a.bucket.includes("180+");
          return (
            <div key={a.bucket} style={{
              display: "grid", gridTemplateColumns: "2fr 80px 1fr", padding: "8px 12px", alignItems: "center",
              borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
            }}>
              <p style={{ fontSize: 12, fontWeight: 500 }}>{a.bucket}</p>
              <p style={{ fontSize: 12 }}>{a.count}</p>
              <p style={{ fontSize: 12, fontWeight: 500, color: isOld ? "#fb7185" : "var(--color-text-primary, #e2e8f0)" }}>{fmtCr(a.amount)}</p>
            </div>
          );
        })}
        {!aging?.length && (
          <div style={{ padding: "16px 12px", textAlign: "center", fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>No aging data</div>
        )}
      </div>
    </div>
  );
}

// ── Saved & exports tab ────────────────────────────────────────

function SavedTab() {
  const { data: saved } = useSavedReports();
  const { data: exports, refetch } = useExports();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Saved reports */}
      <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
        <div style={{ padding: "9px 12px", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", background: "var(--color-background-secondary, #0f1c2e)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <p style={{ fontSize: 11, fontWeight: 500 }}>Saved reports</p>
          <span style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)" }}>{saved?.length ?? 0} reports</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr auto", padding: "6px 12px", background: "var(--color-background-secondary, #0f1c2e)", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" }}>
          {["Report name", "Module", "Last run", ""].map(h => (
            <span key={h} style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary, #64748b)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{h}</span>
          ))}
        </div>
        {(saved ?? []).map((r: SavedReport, i, arr) => (
          <div key={r.id} style={{
            display: "grid", gridTemplateColumns: "2fr 1fr 1fr auto", padding: "8px 12px", alignItems: "center",
            borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
          }}>
            <p style={{ fontSize: 12, fontWeight: 500 }}>{r.name}</p>
            <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 20, background: TEAL_BG, color: TEAL, fontWeight: 500, display: "inline-block" }}>{r.module}</span>
            <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>
              {r.last_run_at ? new Date(r.last_run_at).toLocaleDateString() : "Never"}
            </p>
            <button style={{ fontSize: 10, padding: "3px 8px", borderRadius: 5, border: "0.5px solid rgba(255,255,255,0.1)", background: "transparent", cursor: "pointer", color: TEAL }}>
              Run
            </button>
          </div>
        ))}
        {!saved?.length && (
          <div style={{ padding: "16px 12px", textAlign: "center", fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>No saved reports yet</div>
        )}
      </div>

      {/* Export queue */}
      <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
        <div style={{ padding: "9px 12px", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", background: "var(--color-background-secondary, #0f1c2e)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <p style={{ fontSize: 11, fontWeight: 500 }}>Export queue</p>
          <button onClick={() => refetch()} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "var(--color-text-secondary, #64748b)", background: "transparent", border: "none", cursor: "pointer" }}>
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
        </div>
        {(exports ?? []).map((e: ExportRecord, i, arr) => {
          const es = EXPORT_STATUS[e.status] ?? EXPORT_STATUS.PENDING;
          return (
            <div key={e.id} style={{
              display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px",
              borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
            }}>
              <div>
                <p style={{ fontSize: 12, fontWeight: 500 }}>{e.report_name}</p>
                <p style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)", marginTop: 1 }}>
                  {e.format} · {e.rows_exported != null ? `${e.rows_exported} rows` : "—"} · {new Date(e.created_at).toLocaleString()}
                </p>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <Badge s={es}>{e.status}</Badge>
                {e.status === "READY" && e.file_url && (
                  <a href={e.file_url} style={{ fontSize: 11, color: TEAL, display: "flex", alignItems: "center", gap: 3 }}>
                    <Download className="w-3 h-3" /> Download
                  </a>
                )}
              </div>
            </div>
          );
        })}
        {!exports?.length && (
          <div style={{ padding: "16px 12px", textAlign: "center", fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>No exports yet</div>
        )}
      </div>
    </div>
  );
}

// ── Page root ──────────────────────────────────────────────────

export default function ReportsPage() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ fontSize: 16, fontWeight: 500 }}>Reports & analytics</h1>
          <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)", marginTop: 2 }}>
            Institution-wide insights across admissions, academics, finance, and HR
          </p>
        </div>
        <span style={{ fontSize: 10, fontWeight: 500, padding: "3px 8px", borderRadius: 20, background: TEAL_BG, color: TEAL, border: `0.5px solid ${TEAL_BORDER}` }}>
          E11
        </span>
      </div>

      <ALISTabs defaultValue="overview">
        <ALISTabsList>
          {TABS.map(t => (
            <ALISTabsTrigger key={t.id} value={t.id}>{t.icon} {t.label}</ALISTabsTrigger>
          ))}
        </ALISTabsList>
        <ALISTabsContent value="overview"><OverviewTab /></ALISTabsContent>
        <ALISTabsContent value="admissions"><AdmissionsTab /></ALISTabsContent>
        <ALISTabsContent value="academics"><AcademicsTab /></ALISTabsContent>
        <ALISTabsContent value="finance"><FinanceTab /></ALISTabsContent>
        <ALISTabsContent value="saved"><SavedTab /></ALISTabsContent>
      </ALISTabs>
    </div>
  );
}
