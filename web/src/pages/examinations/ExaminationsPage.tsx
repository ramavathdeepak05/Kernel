import { useState } from "react";
import {
  FileText, Calendar, BarChart3, RefreshCw, Award, Clock,
  CheckCircle2, XCircle, AlertTriangle, TrendingUp, Users,
  BookOpen, Layers, ChevronRight, Star,
} from "lucide-react";
import {
  useExamSchedules,
  useSemesterAnalytics,
  useExamAiInsights,
  usePendingReeval,
} from "@/hooks/use-examinations";
import type { ExamSchedule } from "@/services/examinations";

// ── helpers ────────────────────────────────────────────────────

const CURRENT_YEAR = "2024-25";
const CURRENT_SEM = 4;

type TabId = "overview" | "schedules" | "grades" | "results" | "reeval";

const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: "overview",   label: "Overview",   icon: <BarChart3 className="w-3.5 h-3.5" /> },
  { id: "schedules",  label: "Schedules",  icon: <Calendar className="w-3.5 h-3.5" /> },
  { id: "grades",     label: "Grades",     icon: <BookOpen className="w-3.5 h-3.5" /> },
  { id: "results",    label: "Results",    icon: <Award className="w-3.5 h-3.5" /> },
  { id: "reeval",     label: "Re-Eval",    icon: <RefreshCw className="w-3.5 h-3.5" /> },
];

const EXAM_TYPE_COLORS: Record<string, string> = {
  INTERNAL: "rgba(251,191,36,0.15)",
  MID_TERM: "rgba(99,102,241,0.15)",
  SEMESTER_END: "rgba(52,211,153,0.15)",
  SUPPLEMENTARY: "rgba(251,113,133,0.15)",
  REAPPEAR: "rgba(251,113,133,0.15)",
};
const EXAM_TYPE_TEXT: Record<string, string> = {
  INTERNAL: "#fbbf24",
  MID_TERM: "#818cf8",
  SEMESTER_END: "#34d399",
  SUPPLEMENTARY: "#fb7185",
  REAPPEAR: "#fb7185",
};

const STATUS_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  DRAFT:     { bg: "rgba(100,116,139,0.15)", text: "#64748b", label: "Draft" },
  PUBLISHED: { bg: "rgba(99,102,241,0.15)",  text: "#818cf8", label: "Published" },
  ONGOING:   { bg: "rgba(251,191,36,0.15)",  text: "#fbbf24", label: "Ongoing" },
  COMPLETED: { bg: "rgba(52,211,153,0.15)",  text: "#34d399", label: "Completed" },
  CANCELLED: { bg: "rgba(251,113,133,0.15)", text: "#fb7185", label: "Cancelled" },
};

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_BADGE[status] ?? STATUS_BADGE.DRAFT;
  return (
    <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide"
      style={{ background: s.bg, color: s.text }}>
      {s.label}
    </span>
  );
}

// ── Overview Tab ───────────────────────────────────────────────

function OverviewTab() {
  const { data: analytics, isLoading } = useSemesterAnalytics(CURRENT_YEAR, CURRENT_SEM);
  const { data: insights } = useExamAiInsights(CURRENT_YEAR, CURRENT_SEM);
  const { data: reevalData } = usePendingReeval();

  const pending = reevalData?.total ?? 0;

  // KPI cards
  const kpis = [
    {
      label: "Pass Rate",
      value: analytics ? `${analytics.pass_percentage?.toFixed(1) ?? 0}%` : "—",
      sub: `${analytics?.pass_count ?? 0} / ${analytics?.total_students ?? 0} students`,
      icon: <CheckCircle2 className="w-5 h-5" />,
      color: "#34d399",
      bg: "rgba(52,211,153,0.08)",
    },
    {
      label: "Avg SGPA",
      value: analytics?.avg_sgpa?.toFixed(2) ?? "—",
      sub: `Top: ${analytics?.top_sgpa?.toFixed(2) ?? "—"}`,
      icon: <TrendingUp className="w-5 h-5" />,
      color: "#818cf8",
      bg: "rgba(99,102,241,0.08)",
    },
    {
      label: "Total Students",
      value: analytics?.total_students ?? "—",
      sub: `${analytics?.total_courses ?? 0} courses examined`,
      icon: <Users className="w-5 h-5" />,
      color: "#38bdf8",
      bg: "rgba(56,189,248,0.08)",
    },
    {
      label: "Re-Eval Pending",
      value: pending,
      sub: "Awaiting decision",
      icon: <RefreshCw className="w-5 h-5" />,
      color: "#fbbf24",
      bg: "rgba(251,191,36,0.08)",
    },
  ];

  const gradeColors: Record<string, string> = {
    O: "#34d399", "A+": "#4ade80", A: "#86efac",
    "B+": "#818cf8", B: "#a5b4fc",
    C: "#fbbf24", F: "#fb7185",
  };

  return (
    <div className="space-y-5">
      {/* KPI row */}
      <div className="grid grid-cols-4 gap-4">
        {kpis.map((k) => (
          <div key={k.label} className="rounded-xl p-4 flex gap-3 items-start"
            style={{ background: k.bg, border: `1px solid ${k.color}22` }}>
            <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ background: `${k.color}18`, color: k.color }}>
              {k.icon}
            </div>
            <div>
              <div className="text-[22px] font-bold leading-none mb-1"
                style={{ color: k.color }}>
                {isLoading ? <span className="opacity-40">—</span> : k.value}
              </div>
              <div className="text-[11px] font-medium" style={{ color: "#94a3b8" }}>{k.label}</div>
              <div className="text-[10px] mt-0.5" style={{ color: "#475569" }}>{k.sub}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-5 gap-4">
        {/* Grade Distribution */}
        <div className="col-span-2 rounded-xl p-4"
          style={{ background: "rgba(15,23,42,0.6)", border: "1px solid rgba(51,65,85,0.5)" }}>
          <div className="text-[11px] font-semibold uppercase tracking-widest mb-4"
            style={{ color: "#64748b" }}>Grade Distribution</div>
          {isLoading ? (
            <div className="space-y-2">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="h-6 rounded animate-pulse" style={{ background: "rgba(51,65,85,0.4)" }} />
              ))}
            </div>
          ) : analytics?.grade_distribution ? (
            <div className="space-y-2">
              {Object.entries(analytics.grade_distribution).map(([grade, count]) => {
                const total = analytics.total_students || 1;
                const pct = Math.round((count / total) * 100);
                const color = gradeColors[grade] ?? "#64748b";
                return (
                  <div key={grade} className="flex items-center gap-2">
                    <div className="text-[11px] font-bold w-5 text-right" style={{ color }}>{grade}</div>
                    <div className="flex-1 h-4 rounded overflow-hidden" style={{ background: "rgba(30,41,59,0.8)" }}>
                      <div className="h-full rounded transition-all duration-700"
                        style={{ width: `${pct}%`, background: color, opacity: 0.8 }} />
                    </div>
                    <div className="text-[10px] w-8 text-right" style={{ color: "#64748b" }}>{count}</div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-[12px] text-center py-6" style={{ color: "#475569" }}>
              No grade data for {CURRENT_YEAR} Sem {CURRENT_SEM}
            </div>
          )}
        </div>

        {/* AI Insights */}
        <div className="col-span-3 rounded-xl p-4"
          style={{ background: "rgba(15,23,42,0.6)", border: "1px solid rgba(51,65,85,0.5)" }}>
          <div className="flex items-center gap-2 mb-4">
            <div className="w-5 h-5 rounded flex items-center justify-center"
              style={{ background: "rgba(129,140,248,0.15)" }}>
              <Star className="w-3 h-3" style={{ color: "#818cf8" }} />
            </div>
            <div className="text-[11px] font-semibold uppercase tracking-widest" style={{ color: "#64748b" }}>
              AI Insights — {CURRENT_YEAR} Sem {CURRENT_SEM}
            </div>
          </div>

          {insights?.insights?.length ? (
            <div className="space-y-2.5">
              {insights.insights.map((line, i) => (
                <div key={i} className="flex gap-2.5 items-start">
                  <ChevronRight className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" style={{ color: "#818cf8" }} />
                  <p className="text-[12px] leading-relaxed" style={{ color: "#94a3b8" }}>{line}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-2.5">
              {[
                "Compute semester results first to generate AI insights",
                "AI analysis covers grade distribution, SGPA trends, and at-risk identification",
                "Insights are refreshed after each result publication cycle",
              ].map((line, i) => (
                <div key={i} className="flex gap-2.5 items-start opacity-50">
                  <ChevronRight className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" style={{ color: "#818cf8" }} />
                  <p className="text-[12px] leading-relaxed" style={{ color: "#94a3b8" }}>{line}</p>
                </div>
              ))}
            </div>
          )}

          {/* Fail summary */}
          {analytics && analytics.fail_count > 0 && (
            <div className="mt-4 p-3 rounded-lg flex gap-3 items-center"
              style={{ background: "rgba(251,113,133,0.06)", border: "1px solid rgba(251,113,133,0.15)" }}>
              <AlertTriangle className="w-4 h-4 flex-shrink-0" style={{ color: "#fb7185" }} />
              <span className="text-[12px]" style={{ color: "#fca5a5" }}>
                <strong>{analytics.fail_count}</strong> students failed this semester —
                supplementary examination may be required.
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Exam type pipeline */}
      <div className="rounded-xl p-4"
        style={{ background: "rgba(15,23,42,0.6)", border: "1px solid rgba(51,65,85,0.5)" }}>
        <div className="text-[11px] font-semibold uppercase tracking-widest mb-4" style={{ color: "#64748b" }}>
          Examination Pipeline
        </div>
        <div className="flex items-center gap-0">
          {[
            { label: "Internal Assessment", type: "INTERNAL", desc: "CA/Assignments/Quiz" },
            { label: "Mid-Term", type: "MID_TERM", desc: "Conducted Week 8" },
            { label: "Semester End", type: "SEMESTER_END", desc: "Final examination" },
            { label: "Result Processing", type: "RESULT", desc: "GPA computation" },
            { label: "Revaluation", type: "REEVAL", desc: "Student appeal window" },
            { label: "Transcripts", type: "TRANSCRIPT", desc: "Issued post finalization" },
          ].map((step, i) => {
            const color = EXAM_TYPE_TEXT[step.type] ?? "#64748b";
            const bg = EXAM_TYPE_COLORS[step.type] ?? "rgba(100,116,139,0.1)";
            return (
              <div key={step.type} className="flex items-center flex-1">
                <div className="flex-1 p-3 rounded-xl text-center"
                  style={{ background: bg, border: `1px solid ${color}25` }}>
                  <div className="text-[9px] font-bold uppercase tracking-wider mb-1" style={{ color }}>
                    Stage {i + 1}
                  </div>
                  <div className="text-[11px] font-semibold" style={{ color: "#e2e8f0" }}>{step.label}</div>
                  <div className="text-[10px] mt-0.5" style={{ color: "#64748b" }}>{step.desc}</div>
                </div>
                {i < 5 && (
                  <ChevronRight className="w-4 h-4 flex-shrink-0 mx-1" style={{ color: "#334155" }} />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Schedules Tab ──────────────────────────────────────────────

function SchedulesTab() {
  const [examType, setExamType] = useState<string>("");
  const [semester, setSemester] = useState<number | undefined>(CURRENT_SEM);

  const { data, isLoading } = useExamSchedules(CURRENT_YEAR, semester, examType || undefined);
  const schedules = data?.schedules ?? [];

  const examTypes = ["", "INTERNAL", "MID_TERM", "SEMESTER_END", "SUPPLEMENTARY"];

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="text-[11px]" style={{ color: "#64748b" }}>Filter:</div>
        <div className="flex gap-2">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((s) => (
            <button key={s}
              onClick={() => setSemester(semester === s ? undefined : s)}
              className="px-2.5 py-1 rounded text-[11px] font-medium transition-all"
              style={{
                background: semester === s ? "rgba(52,211,153,0.15)" : "rgba(30,41,59,0.6)",
                color: semester === s ? "#34d399" : "#64748b",
                border: `1px solid ${semester === s ? "rgba(52,211,153,0.3)" : "rgba(51,65,85,0.4)"}`,
              }}>
              Sem {s}
            </button>
          ))}
        </div>
        <div className="flex gap-2 ml-2">
          {examTypes.map((t) => (
            <button key={t}
              onClick={() => setExamType(t)}
              className="px-2.5 py-1 rounded text-[11px] font-medium transition-all"
              style={{
                background: examType === t ? "rgba(129,140,248,0.15)" : "rgba(30,41,59,0.6)",
                color: examType === t ? "#818cf8" : "#64748b",
                border: `1px solid ${examType === t ? "rgba(129,140,248,0.3)" : "rgba(51,65,85,0.4)"}`,
              }}>
              {t || "All Types"}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="rounded-xl overflow-hidden"
        style={{ border: "1px solid rgba(51,65,85,0.5)" }}>
        <table className="w-full">
          <thead>
            <tr style={{ background: "rgba(15,23,42,0.8)" }}>
              {["Course", "Type", "Date", "Time", "Venue", "Marks", "Status"].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: "#475569" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i} style={{ borderTop: "1px solid rgba(51,65,85,0.3)" }}>
                  {[...Array(7)].map((_, j) => (
                    <td key={j} className="px-4 py-3">
                      <div className="h-4 rounded animate-pulse" style={{ background: "rgba(51,65,85,0.4)", width: "80%" }} />
                    </td>
                  ))}
                </tr>
              ))
            ) : schedules.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-[12px]" style={{ color: "#475569" }}>
                  No exam schedules for the selected filters
                </td>
              </tr>
            ) : schedules.map((s: ExamSchedule) => (
              <tr key={s.id}
                className="transition-colors"
                style={{ borderTop: "1px solid rgba(51,65,85,0.3)" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(30,41,59,0.5)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                <td className="px-4 py-3">
                  <div className="text-[12px] font-medium" style={{ color: "#e2e8f0" }}>{s.course_name || s.course_id}</div>
                  <div className="text-[10px]" style={{ color: "#64748b" }}>{s.course_code}</div>
                </td>
                <td className="px-4 py-3">
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold"
                    style={{
                      background: EXAM_TYPE_COLORS[s.exam_type] ?? "rgba(100,116,139,0.1)",
                      color: EXAM_TYPE_TEXT[s.exam_type] ?? "#64748b",
                    }}>
                    {s.exam_type.replace(/_/g, " ")}
                  </span>
                </td>
                <td className="px-4 py-3 text-[12px]" style={{ color: "#94a3b8" }}>{s.exam_date}</td>
                <td className="px-4 py-3 text-[11px]" style={{ color: "#64748b" }}>
                  {s.start_time} – {s.end_time}
                </td>
                <td className="px-4 py-3 text-[12px]" style={{ color: "#94a3b8" }}>{s.venue}</td>
                <td className="px-4 py-3 text-[12px]" style={{ color: "#94a3b8" }}>
                  {s.pass_marks} / {s.max_marks}
                </td>
                <td className="px-4 py-3"><StatusBadge status={s.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!isLoading && schedules.length > 0 && (
        <div className="text-[11px]" style={{ color: "#475569" }}>
          Showing {schedules.length} schedule{schedules.length !== 1 ? "s" : ""} · {CURRENT_YEAR}
        </div>
      )}
    </div>
  );
}

// ── Grades Tab ────────────────────────────────────────────────

function GradesTab() {
  return (
    <div className="rounded-xl p-6 text-center" style={{ background: "rgba(15,23,42,0.6)", border: "1px solid rgba(51,65,85,0.5)" }}>
      <BookOpen className="w-10 h-10 mx-auto mb-3" style={{ color: "#818cf8", opacity: 0.5 }} />
      <div className="text-[13px] font-semibold mb-1" style={{ color: "#e2e8f0" }}>Grade Entry Portal</div>
      <div className="text-[12px] mb-4" style={{ color: "#64748b" }}>
        Bulk grade entry is performed via the Evaluation workflow by assigned faculty
      </div>
      <div className="grid grid-cols-3 gap-4 text-left mt-6">
        {[
          { step: "1", title: "Faculty submits marks", desc: "Via bulk grade entry API after evaluation" },
          { step: "2", title: "Auto-grade computation", desc: "System computes grade & grade-points per grading scheme" },
          { step: "3", title: "Controller verification", desc: "ExamController reviews anomalies before finalizing" },
        ].map((s) => (
          <div key={s.step} className="p-4 rounded-xl"
            style={{ background: "rgba(30,41,59,0.5)", border: "1px solid rgba(51,65,85,0.4)" }}>
            <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold mb-2"
              style={{ background: "rgba(129,140,248,0.15)", color: "#818cf8" }}>
              {s.step}
            </div>
            <div className="text-[12px] font-semibold mb-1" style={{ color: "#e2e8f0" }}>{s.title}</div>
            <div className="text-[11px]" style={{ color: "#64748b" }}>{s.desc}</div>
          </div>
        ))}
      </div>
      <div className="mt-5 p-3 rounded-lg inline-flex items-center gap-2"
        style={{ background: "rgba(52,211,153,0.06)", border: "1px solid rgba(52,211,153,0.15)" }}>
        <CheckCircle2 className="w-4 h-4" style={{ color: "#34d399" }} />
        <span className="text-[11px]" style={{ color: "#34d399" }}>
          Grading scheme: O(10) A+(9) A(8) B+(7) B(6) C(5) F(0) · Pass ≥ 50%
        </span>
      </div>
    </div>
  );
}

// ── Results Tab ────────────────────────────────────────────────

function ResultsTab() {
  const { data: analytics } = useSemesterAnalytics(CURRENT_YEAR, CURRENT_SEM);

  const statusCards = [
    {
      label: "Passed",
      value: analytics?.pass_count ?? "—",
      icon: <CheckCircle2 className="w-5 h-5" />,
      color: "#34d399",
      bg: "rgba(52,211,153,0.08)",
    },
    {
      label: "Failed",
      value: analytics?.fail_count ?? "—",
      icon: <XCircle className="w-5 h-5" />,
      color: "#fb7185",
      bg: "rgba(251,113,133,0.08)",
    },
    {
      label: "Avg SGPA",
      value: analytics?.avg_sgpa?.toFixed(2) ?? "—",
      icon: <TrendingUp className="w-5 h-5" />,
      color: "#818cf8",
      bg: "rgba(99,102,241,0.08)",
    },
    {
      label: "Highest SGPA",
      value: analytics?.top_sgpa?.toFixed(2) ?? "—",
      icon: <Star className="w-5 h-5" />,
      color: "#fbbf24",
      bg: "rgba(251,191,36,0.08)",
    },
  ];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-4 gap-4">
        {statusCards.map((c) => (
          <div key={c.label} className="rounded-xl p-4 flex gap-3 items-center"
            style={{ background: c.bg, border: `1px solid ${c.color}22` }}>
            <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ background: `${c.color}18`, color: c.color }}>
              {c.icon}
            </div>
            <div>
              <div className="text-[22px] font-bold leading-none" style={{ color: c.color }}>{c.value}</div>
              <div className="text-[11px] mt-0.5" style={{ color: "#94a3b8" }}>{c.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Result lifecycle */}
      <div className="rounded-xl p-4"
        style={{ background: "rgba(15,23,42,0.6)", border: "1px solid rgba(51,65,85,0.5)" }}>
        <div className="text-[11px] font-semibold uppercase tracking-widest mb-4" style={{ color: "#64748b" }}>
          Result Publication Lifecycle
        </div>
        <div className="grid grid-cols-4 gap-3">
          {[
            { icon: <Layers className="w-4 h-4" />, title: "Compute GPA", desc: "POST /exams/results/compute · Calculates SGPA/CGPA per student per semester", color: "#38bdf8" },
            { icon: <CheckCircle2 className="w-4 h-4" />, title: "Controller Review", desc: "Exam controller verifies outliers and withheld results before publish", color: "#818cf8" },
            { icon: <FileText className="w-4 h-4" />, title: "Publish Results", desc: "POST /exams/results/publish · Batch publish for entire semester cohort", color: "#34d399" },
            { icon: <Award className="w-4 h-4" />, title: "Generate Transcripts", desc: "Official transcripts with digital signature issued after publication", color: "#fbbf24" },
          ].map((step) => (
            <div key={step.title} className="p-3 rounded-xl"
              style={{ background: "rgba(30,41,59,0.5)", border: `1px solid ${step.color}20` }}>
              <div className="w-8 h-8 rounded-lg flex items-center justify-center mb-2"
                style={{ background: `${step.color}15`, color: step.color }}>
                {step.icon}
              </div>
              <div className="text-[12px] font-semibold mb-1" style={{ color: "#e2e8f0" }}>{step.title}</div>
              <div className="text-[10px] leading-relaxed" style={{ color: "#64748b" }}>{step.desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Result status rules */}
      <div className="rounded-xl p-4"
        style={{ background: "rgba(15,23,42,0.6)", border: "1px solid rgba(51,65,85,0.5)" }}>
        <div className="text-[11px] font-semibold uppercase tracking-widest mb-3" style={{ color: "#64748b" }}>
          Result Status Rules
        </div>
        <div className="grid grid-cols-2 gap-3">
          {[
            { status: "PASS", rule: "All subjects ≥ pass marks AND earned credits = total credits", color: "#34d399" },
            { status: "FAIL", rule: "One or more subjects below pass marks threshold", color: "#fb7185" },
            { status: "DETAINED", rule: "Attendance < minimum required (default 75%)", color: "#fbbf24" },
            { status: "WITHHELD", rule: "Dues pending / disciplinary hold / document incomplete", color: "#64748b" },
          ].map((r) => (
            <div key={r.status} className="flex gap-3 items-start p-3 rounded-lg"
              style={{ background: `${r.color}08`, border: `1px solid ${r.color}18` }}>
              <div className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded flex-shrink-0 mt-0.5"
                style={{ background: `${r.color}18`, color: r.color }}>
                {r.status}
              </div>
              <div className="text-[11px]" style={{ color: "#94a3b8" }}>{r.rule}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Re-Eval Tab ────────────────────────────────────────────────

function ReEvalTab() {
  const { data, isLoading } = usePendingReeval();
  const requests = data?.reeval_requests ?? [];

  const statusConfig = {
    PENDING:      { color: "#fbbf24", bg: "rgba(251,191,36,0.1)" },
    UNDER_REVIEW: { color: "#818cf8", bg: "rgba(129,140,248,0.1)" },
    REVISED:      { color: "#34d399", bg: "rgba(52,211,153,0.1)" },
    REJECTED:     { color: "#fb7185", bg: "rgba(251,113,133,0.1)" },
    CLOSED:       { color: "#64748b", bg: "rgba(100,116,139,0.1)" },
  };

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-xl p-4"
          style={{ background: "rgba(251,191,36,0.06)", border: "1px solid rgba(251,191,36,0.15)" }}>
          <div className="text-[24px] font-bold" style={{ color: "#fbbf24" }}>
            {isLoading ? "—" : data?.total ?? 0}
          </div>
          <div className="text-[11px]" style={{ color: "#94a3b8" }}>Pending Re-evaluations</div>
        </div>
        <div className="rounded-xl p-4"
          style={{ background: "rgba(15,23,42,0.6)", border: "1px solid rgba(51,65,85,0.4)" }}>
          <div className="text-[13px] font-semibold mb-1" style={{ color: "#e2e8f0" }}>SLA Deadline</div>
          <div className="text-[12px]" style={{ color: "#64748b" }}>
            Re-evaluations must be decided within 21 days of submission per UGC norms
          </div>
        </div>
        <div className="rounded-xl p-4"
          style={{ background: "rgba(15,23,42,0.6)", border: "1px solid rgba(51,65,85,0.4)" }}>
          <div className="text-[13px] font-semibold mb-1" style={{ color: "#e2e8f0" }}>Fee Policy</div>
          <div className="text-[12px]" style={{ color: "#64748b" }}>
            ₹500 per subject · Refundable if marks revised upward by ≥5 marks
          </div>
        </div>
      </div>

      {/* Pending queue */}
      <div className="rounded-xl overflow-hidden"
        style={{ border: "1px solid rgba(51,65,85,0.5)" }}>
        <div className="px-4 py-3"
          style={{ background: "rgba(15,23,42,0.8)", borderBottom: "1px solid rgba(51,65,85,0.4)" }}>
          <div className="text-[11px] font-semibold uppercase tracking-widest" style={{ color: "#64748b" }}>
            Pending Re-evaluation Queue
          </div>
        </div>
        <table className="w-full">
          <thead>
            <tr style={{ background: "rgba(15,23,42,0.5)" }}>
              {["Student", "Course", "Exam Type", "Semester", "Reason", "Submitted", "Status"].map((h) => (
                <th key={h} className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: "#475569" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              [...Array(3)].map((_, i) => (
                <tr key={i} style={{ borderTop: "1px solid rgba(51,65,85,0.3)" }}>
                  {[...Array(7)].map((_, j) => (
                    <td key={j} className="px-4 py-3">
                      <div className="h-4 rounded animate-pulse" style={{ background: "rgba(51,65,85,0.4)", width: "75%" }} />
                    </td>
                  ))}
                </tr>
              ))
            ) : requests.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-[12px]" style={{ color: "#475569" }}>
                  <Clock className="w-6 h-6 mx-auto mb-2 opacity-30" />
                  No pending re-evaluation requests
                </td>
              </tr>
            ) : requests.map((r) => {
              const sc = statusConfig[r.status as keyof typeof statusConfig] ?? statusConfig.PENDING;
              return (
                <tr key={r.id} style={{ borderTop: "1px solid rgba(51,65,85,0.3)" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(30,41,59,0.5)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                  <td className="px-4 py-3 text-[12px]" style={{ color: "#e2e8f0" }}>
                    {r.student_name || r.student_id}
                  </td>
                  <td className="px-4 py-3 text-[12px]" style={{ color: "#94a3b8" }}>{r.course_name || r.course_id}</td>
                  <td className="px-4 py-3 text-[11px]" style={{ color: "#64748b" }}>{r.exam_type}</td>
                  <td className="px-4 py-3 text-[12px]" style={{ color: "#94a3b8" }}>Sem {r.semester}</td>
                  <td className="px-4 py-3 text-[11px] max-w-[160px] truncate" style={{ color: "#64748b" }}>
                    {r.reason}
                  </td>
                  <td className="px-4 py-3 text-[11px]" style={{ color: "#64748b" }}>
                    {r.submitted_at?.split("T")[0]}
                  </td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded text-[10px] font-semibold"
                      style={{ background: sc.bg, color: sc.color }}>
                      {r.status}
                    </span>
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

// ── Main Page ──────────────────────────────────────────────────

export default function ExaminationsPage() {
  const [tab, setTab] = useState<TabId>("overview");

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: "transparent" }}>
      {/* Header */}
      <div className="flex-shrink-0 px-6 pt-5 pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: "rgba(52,211,153,0.1)", border: "1px solid rgba(52,211,153,0.2)" }}>
              <FileText className="w-4.5 h-4.5" style={{ color: "#34d399" }} />
            </div>
            <div>
              <h1 className="text-[18px] font-bold leading-none" style={{ color: "#e2e8f0" }}>
                Examinations &amp; Grades
              </h1>
              <p className="text-[11px] mt-0.5" style={{ color: "#64748b" }}>
                E06 · {CURRENT_YEAR} · Semester {CURRENT_SEM}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-[11px]"
            style={{ background: "rgba(52,211,153,0.06)", border: "1px solid rgba(52,211,153,0.12)", color: "#34d399" }}>
            <CheckCircle2 className="w-3.5 h-3.5" />
            Backend Active
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 mt-4">
          {tabs.map((t) => (
            <button key={t.id}
              onClick={() => setTab(t.id)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all"
              style={{
                background: tab === t.id ? "rgba(52,211,153,0.12)" : "transparent",
                color: tab === t.id ? "#34d399" : "#64748b",
                border: `1px solid ${tab === t.id ? "rgba(52,211,153,0.25)" : "transparent"}`,
              }}>
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        {tab === "overview"  && <OverviewTab />}
        {tab === "schedules" && <SchedulesTab />}
        {tab === "grades"    && <GradesTab />}
        {tab === "results"   && <ResultsTab />}
        {tab === "reeval"    && <ReEvalTab />}
      </div>
    </div>
  );
}
