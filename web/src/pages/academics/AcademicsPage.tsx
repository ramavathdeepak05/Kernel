import { useState } from "react";
import {
  BookOpen,
  Users,
  Clock,
  TrendingUp,
  AlertTriangle,
  CheckCircle,
  Calendar,
  BarChart3,
  GraduationCap,
  Brain,
  Layers,
  ChevronRight,
  RefreshCw,
  Activity,
} from "lucide-react";
import {
  usePrograms,
  useCourses,
  useTimetable,
  useAtRiskStudents,
  useAcademicsInsights,
} from "@/hooks/use-academics";
import { cn, formatDate } from "@/lib/utils";
import type { TimetableSlot } from "@/services/academics";

// ── Helpers ──────────────────────────────────────────────────

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const ACCENT = "#60a5fa";

function Chip({ label, color }: { label: string; color: string }) {
  return (
    <span
      className="text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded"
      style={{ background: `${color}18`, color, border: `1px solid ${color}30` }}
    >
      {label}
    </span>
  );
}

function SkeletonRows({ n = 5 }: { n?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="skeleton-dark h-12 rounded-xl" />
      ))}
    </div>
  );
}

// ── Tab nav ──────────────────────────────────────────────────

type TabId = "overview" | "courses" | "timetable" | "attendance" | "mentorship";

function TabNav({ active, onChange }: { active: TabId; onChange: (t: TabId) => void }) {
  const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: "overview",    label: "Overview",   icon: <BarChart3 className="w-3 h-3" /> },
    { id: "courses",     label: "Courses",    icon: <BookOpen className="w-3 h-3" /> },
    { id: "timetable",   label: "Timetable",  icon: <Calendar className="w-3 h-3" /> },
    { id: "attendance",  label: "Attendance", icon: <Activity className="w-3 h-3" /> },
    { id: "mentorship",  label: "Mentorship", icon: <Brain className="w-3 h-3" /> },
  ];
  return (
    <div className="flex items-center gap-1 mb-5 overflow-x-auto pb-1" style={{ scrollbarWidth: "none" }}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all"
          style={{
            background: active === tab.id ? "rgba(96,165,250,0.12)" : "transparent",
            border: `1px solid ${active === tab.id ? "rgba(96,165,250,0.25)" : "transparent"}`,
            color: active === tab.id ? ACCENT : "#64748b",
          }}
        >
          {tab.icon}
          {tab.label}
        </button>
      ))}
    </div>
  );
}

// ── KPI Card ─────────────────────────────────────────────────

function KpiCard({
  label, value, sub, color, icon,
}: { label: string; value: string | number; sub?: string; color: string; icon: React.ReactNode }) {
  return (
    <div
      className="p-4 rounded-xl"
      style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}
    >
      <div className="flex items-start justify-between mb-2">
        <span className="text-[10px] font-semibold uppercase tracking-[0.12em]" style={{ color: "#475569" }}>
          {label}
        </span>
        <div className="p-1.5 rounded-lg" style={{ background: `${color}15` }}>
          <div style={{ color }}>{icon}</div>
        </div>
      </div>
      <div className="text-2xl font-bold" style={{ color: "#e2e8f0", letterSpacing: "-0.03em" }}>
        {value}
      </div>
      {sub && <div className="text-[11px] mt-0.5" style={{ color: "#475569" }}>{sub}</div>}
    </div>
  );
}

// ── Overview Tab ─────────────────────────────────────────────

function OverviewTab() {
  const insights = useAcademicsInsights();
  const programs = usePrograms();
  const atRisk = useAtRiskStudents();

  const d = insights.data;

  return (
    <div className="space-y-5">
      {/* KPI grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard
          label="Programs" value={programs.data?.total ?? "—"}
          sub="Active degree programs" color="#60a5fa"
          icon={<GraduationCap className="w-4 h-4" />}
        />
        <KpiCard
          label="Courses Active" value={d?.total_courses ?? "—"}
          sub="This semester" color="#34d399"
          icon={<BookOpen className="w-4 h-4" />}
        />
        <KpiCard
          label="Avg Attendance" value={d ? `${Math.round(d.avg_attendance_pct ?? 0)}%` : "—"}
          sub="Across all courses" color="#fbbf24"
          icon={<Activity className="w-4 h-4" />}
        />
        <KpiCard
          label="At-Risk Students" value={atRisk.data?.total ?? "—"}
          sub={`${d?.critical_count ?? 0} critical`} color="#f87171"
          icon={<AlertTriangle className="w-4 h-4" />}
        />
      </div>

      {/* Workflow pipeline */}
      <div
        className="p-4 rounded-xl"
        style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)" }}
      >
        <div className="flex items-center gap-2 mb-4">
          <Layers className="w-3.5 h-3.5" style={{ color: ACCENT }} />
          <span className="text-[10px] font-bold uppercase tracking-[0.14em]" style={{ color: "#475569" }}>
            Academic Pipeline · Semester Lifecycle
          </span>
        </div>
        <div className="grid grid-cols-5 gap-2">
          {[
            { step: "01", label: "Calendar", sub: "Registrar approves", status: "done", color: "#34d399" },
            { step: "02", label: "Course Mapping", sub: "HOD approves", status: "done", color: "#34d399" },
            { step: "03", label: "Content Gen", sub: "Faculty reviews", status: "active", color: ACCENT },
            { step: "04", label: "Assessments", sub: "IA papers + rubrics", status: "pending", color: "#64748b" },
            { step: "05", label: "Timetable", sub: "Registrar publishes", status: "pending", color: "#64748b" },
          ].map((s) => (
            <div key={s.step} className="relative">
              <div
                className="p-3 rounded-xl text-center"
                style={{
                  background: s.status === "active" ? "rgba(96,165,250,0.08)" : "rgba(255,255,255,0.02)",
                  border: `1px solid ${s.status === "active" ? "rgba(96,165,250,0.2)" : "rgba(255,255,255,0.05)"}`,
                }}
              >
                <div className="text-[9px] font-mono mb-1" style={{ color: s.color }}>{s.step}</div>
                <div className="text-[11px] font-semibold mb-0.5" style={{ color: s.status === "pending" ? "#334155" : "#e2e8f0" }}>
                  {s.label}
                </div>
                <div className="text-[10px]" style={{ color: "#475569" }}>{s.sub}</div>
                {s.status === "done" && (
                  <CheckCircle className="w-3 h-3 mx-auto mt-1.5" style={{ color: "#34d399" }} />
                )}
                {s.status === "active" && (
                  <div className="w-1.5 h-1.5 rounded-full mx-auto mt-1.5 animate-pulse" style={{ background: ACCENT }} />
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* AI Insights */}
      {d?.insights && d.insights.length > 0 && (
        <div
          className="p-4 rounded-xl"
          style={{ background: "rgba(96,165,250,0.04)", border: "1px solid rgba(96,165,250,0.1)" }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Brain className="w-3.5 h-3.5" style={{ color: ACCENT }} />
            <span className="text-[10px] font-bold uppercase tracking-[0.14em]" style={{ color: "#475569" }}>
              AI Insights
            </span>
          </div>
          <ul className="space-y-1.5">
            {d.insights.map((insight, i) => (
              <li key={i} className="flex items-start gap-2">
                <ChevronRight className="w-3 h-3 mt-0.5 flex-shrink-0" style={{ color: ACCENT }} />
                <span className="text-[12px]" style={{ color: "#94a3b8" }}>{insight}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Programs list */}
      <div>
        <div className="section-header mb-3">
          <GraduationCap className="w-3 h-3" style={{ color: "#475569" }} />
          Active Programs
        </div>
        {programs.isLoading ? (
          <SkeletonRows n={3} />
        ) : (programs.data?.programs ?? []).length === 0 ? (
          <div className="text-center py-8 text-[12px]" style={{ color: "#334155" }}>
            No programs found. Seed academic data first.
          </div>
        ) : (
          <div className="space-y-2">
            {(programs.data?.programs ?? []).map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between px-4 py-3 rounded-xl"
                style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}
              >
                <div>
                  <div className="text-[13px] font-semibold" style={{ color: "#e2e8f0" }}>{p.name}</div>
                  <div className="text-[11px] mt-0.5" style={{ color: "#475569" }}>
                    {p.code} · {p.degree_type} · {p.duration_years} years · {p.total_credits} credits
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-mono" style={{ color: "#475569" }}>
                    {p.total_semesters} sem
                  </span>
                  <Chip
                    label={p.status}
                    color={p.status === "ACTIVE" ? "#34d399" : "#f87171"}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Courses Tab ──────────────────────────────────────────────

function CoursesTab() {
  const courses = useCourses();
  const programs = usePrograms();

  const [filterProgram, setFilterProgram] = useState("");

  const filtered = (courses.data?.courses ?? []).filter(
    (c) => !filterProgram || c.program_id === filterProgram
  );

  const COURSE_TYPE_COLORS: Record<string, string> = {
    THEORY: "#60a5fa",
    LAB: "#34d399",
    ELECTIVE: "#fbbf24",
    PROJECT: "#a78bfa",
  };

  return (
    <div className="space-y-4">
      {/* Filter */}
      <div className="flex items-center gap-2">
        <select
          value={filterProgram}
          onChange={(e) => setFilterProgram(e.target.value)}
          className="text-[11px] px-3 py-1.5 rounded-lg"
          style={{
            background: "rgba(255,255,255,0.05)",
            border: "1px solid rgba(255,255,255,0.1)",
            color: "#94a3b8",
          }}
        >
          <option value="">All Programs</option>
          {(programs.data?.programs ?? []).map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <span className="text-[11px]" style={{ color: "#475569" }}>
          {filtered.length} course{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      {courses.isLoading ? (
        <SkeletonRows />
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-[13px]" style={{ color: "#334155" }}>
          No courses found. Create programs and add courses to get started.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                {["Code", "Course Name", "Sem", "Credits", "L-T-P", "Type", "Faculty"].map((h) => (
                  <th key={h} className="text-left pb-3 pr-4 text-[10px] font-semibold uppercase tracking-wide"
                    style={{ color: "#475569" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr key={c.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <td className="py-3 pr-4 font-mono text-[11px]" style={{ color: ACCENT }}>{c.code}</td>
                  <td className="py-3 pr-4 font-semibold" style={{ color: "#e2e8f0" }}>{c.name}</td>
                  <td className="py-3 pr-4" style={{ color: "#64748b" }}>Sem {c.semester}</td>
                  <td className="py-3 pr-4 font-semibold" style={{ color: "#94a3b8" }}>{c.credits}</td>
                  <td className="py-3 pr-4 font-mono text-[11px]" style={{ color: "#475569" }}>
                    {c.lecture_hours}-{c.tutorial_hours}-{c.practical_hours}
                  </td>
                  <td className="py-3 pr-4">
                    <Chip label={c.course_type} color={COURSE_TYPE_COLORS[c.course_type] ?? "#94a3b8"} />
                  </td>
                  <td className="py-3 pr-4 text-[11px]" style={{ color: "#475569" }}>
                    {c.faculty_name ?? <span style={{ color: "#334155" }}>Unassigned</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Timetable Tab ────────────────────────────────────────────

function TimetableTab() {
  const timetable = useTimetable();
  const slots = timetable.data?.slots ?? [];

  // Group by day
  const byDay: Record<number, TimetableSlot[]> = {};
  slots.forEach((s) => {
    (byDay[s.day_of_week] ??= []).push(s);
  });

  const SLOT_COLORS = ["#60a5fa", "#34d399", "#fbbf24", "#a78bfa", "#f97316", "#f87171", "#06b6d4"];

  if (timetable.isLoading) return <SkeletonRows n={6} />;

  if (slots.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <Calendar className="w-10 h-10 mb-3 opacity-20" style={{ color: ACCENT }} />
        <p className="text-[13px] font-medium" style={{ color: "#64748b" }}>No timetable slots configured</p>
        <p className="text-[11px] mt-1" style={{ color: "#334155" }}>
          Add courses and assign faculty to generate a timetable
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {DAYS.map((day, idx) => {
        const daySlots = (byDay[idx + 1] ?? []).sort((a, b) => a.start_time.localeCompare(b.start_time));
        return (
          <div key={day}>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] font-bold uppercase tracking-[0.14em] w-8" style={{ color: "#475569" }}>
                {day}
              </span>
              <div className="flex-1 flex items-center gap-1.5 overflow-x-auto pb-1" style={{ scrollbarWidth: "none" }}>
                {daySlots.length === 0 ? (
                  <span className="text-[10px]" style={{ color: "#1e293b" }}>—</span>
                ) : daySlots.map((slot, i) => (
                  <div
                    key={slot.id}
                    className="flex-shrink-0 px-3 py-2 rounded-xl"
                    style={{
                      background: `${SLOT_COLORS[i % SLOT_COLORS.length]}12`,
                      border: `1px solid ${SLOT_COLORS[i % SLOT_COLORS.length]}25`,
                      minWidth: 140,
                    }}
                  >
                    <div className="text-[11px] font-semibold" style={{ color: "#e2e8f0" }}>
                      {slot.course_name ?? slot.course_id}
                    </div>
                    <div className="text-[10px] mt-0.5" style={{ color: "#475569" }}>
                      {slot.start_time}–{slot.end_time} · {slot.room}
                    </div>
                    <div className="flex items-center gap-1.5 mt-1">
                      <Chip label={slot.slot_type} color={SLOT_COLORS[i % SLOT_COLORS.length]} />
                      <span className="text-[10px]" style={{ color: "#334155" }}>Sec {slot.section}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Attendance Tab ───────────────────────────────────────────

function AttendanceTab() {
  const atRisk = useAtRiskStudents();
  const insights = useAcademicsInsights();
  const d = insights.data;

  const RISK_COLORS: Record<string, string> = {
    GREEN: "#34d399",
    AMBER: "#fbbf24",
    RED: "#f87171",
  };

  return (
    <div className="space-y-5">
      {/* Summary bar */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Below 85%", value: d?.courses_below_75 ?? "—", color: "#fbbf24", desc: "Need monitoring" },
          { label: "Below 75%", value: d?.at_risk_count ?? "—", color: "#f97316", desc: "At-risk threshold" },
          { label: "Below 65%", value: d?.critical_count ?? "—", color: "#f87171", desc: "Critical / ineligible" },
        ].map((stat) => (
          <div key={stat.label} className="p-3 rounded-xl text-center"
            style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}>
            <div className="text-xl font-bold" style={{ color: stat.color }}>{stat.value}</div>
            <div className="text-[10px] font-semibold mt-0.5" style={{ color: "#94a3b8" }}>{stat.label}</div>
            <div className="text-[10px]" style={{ color: "#334155" }}>{stat.desc}</div>
          </div>
        ))}
      </div>

      {/* Alert thresholds info */}
      <div className="p-3 rounded-xl" style={{ background: "rgba(251,191,36,0.04)", border: "1px solid rgba(251,191,36,0.1)" }}>
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle className="w-3.5 h-3.5" style={{ color: "#fbbf24" }} />
          <span className="text-[10px] font-bold uppercase tracking-wide" style={{ color: "#475569" }}>
            Automated Alert Rules (Policy Engine)
          </span>
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1">
          {[
            ["< 85% any course", "Student → Portal + SMS"],
            ["< 80% any course", "Student + Parent → Email + SMS"],
            ["< 75% any course", "Student + Parent + Mentor"],
            ["< 65% critical", "Student + Parent + HOD + Registrar"],
            ["3 consecutive absences", "Mentor → Portal notification"],
          ].map(([trigger, target]) => (
            <div key={trigger} className="flex items-center gap-1.5">
              <div className="w-1 h-1 rounded-full flex-shrink-0" style={{ background: "#fbbf24" }} />
              <span className="text-[10px]" style={{ color: "#64748b" }}>
                <span style={{ color: "#94a3b8" }}>{trigger}</span> → {target}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* At-risk students */}
      <div>
        <div className="section-header mb-3">
          <AlertTriangle className="w-3 h-3" style={{ color: "#f87171" }} />
          At-Risk Students
          {atRisk.data && (
            <span className="ml-1 px-1.5 py-0.5 rounded text-[9px] font-bold"
              style={{ background: "rgba(248,113,113,0.12)", color: "#f87171", border: "1px solid rgba(248,113,113,0.2)" }}>
              {atRisk.data.total}
            </span>
          )}
        </div>

        {atRisk.isLoading ? (
          <SkeletonRows />
        ) : (atRisk.data?.at_risk ?? []).length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10">
            <CheckCircle className="w-8 h-8 mb-2" style={{ color: "#34d399" }} />
            <p className="text-[13px]" style={{ color: "#34d399" }}>All students on track</p>
            <p className="text-[11px] mt-0.5" style={{ color: "#475569" }}>No attendance alerts triggered</p>
          </div>
        ) : (
          <div className="space-y-2">
            {(atRisk.data?.at_risk ?? []).map((s) => (
              <div
                key={s.student_id}
                className="flex items-center justify-between px-4 py-3 rounded-xl"
                style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)" }}
              >
                <div className="flex items-center gap-3">
                  <div
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ background: RISK_COLORS[s.risk_level] ?? "#64748b" }}
                  />
                  <div>
                    <div className="text-[12px] font-semibold" style={{ color: "#e2e8f0" }}>
                      {s.student_name}
                    </div>
                    <div className="text-[10px] mt-0.5" style={{ color: "#475569" }}>
                      {s.program ?? "—"} · Mentor: {s.mentor_name ?? "Unassigned"}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <div className="text-right">
                    <div className="text-[13px] font-bold" style={{ color: RISK_COLORS[s.risk_level] }}>
                      {Math.round(s.attendance_pct)}%
                    </div>
                    <div className="text-[10px]" style={{ color: "#475569" }}>
                      {s.courses_at_risk} course{s.courses_at_risk !== 1 ? "s" : ""} flagged
                    </div>
                  </div>
                  <Chip label={s.risk_level} color={RISK_COLORS[s.risk_level]} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Mentorship Tab ───────────────────────────────────────────

function MentorshipTab() {
  const atRisk = useAtRiskStudents();

  const riskStudents = atRisk.data?.at_risk ?? [];
  const redStudents  = riskStudents.filter((s) => s.risk_level === "RED");
  const amberStudents = riskStudents.filter((s) => s.risk_level === "AMBER");

  const RISK_COLORS: Record<string, string> = {
    GREEN: "#34d399", AMBER: "#fbbf24", RED: "#f87171",
  };

  return (
    <div className="space-y-5">
      {/* Risk model */}
      <div className="p-4 rounded-xl"
        style={{ background: "rgba(167,139,250,0.04)", border: "1px solid rgba(167,139,250,0.1)" }}>
        <div className="flex items-center gap-2 mb-3">
          <Brain className="w-3.5 h-3.5" style={{ color: "#a78bfa" }} />
          <span className="text-[10px] font-bold uppercase tracking-[0.14em]" style={{ color: "#475569" }}>
            AI Risk Score Inputs
          </span>
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
          {[
            { signal: "Attendance < 75% any course", weight: "High",   source: "Module 6" },
            { signal: "IA score < 40% any course",   weight: "High",   source: "Module 8" },
            { signal: "3+ consecutive absences",     weight: "Medium", source: "Module 6" },
            { signal: "Low entrance / 12th marks",   weight: "Medium", source: "Admissions" },
            { signal: "2+ assignment non-submissions",weight: "Medium", source: "LMS" },
            { signal: "7+ days without LMS login",   weight: "Low",    source: "LMS" },
            { signal: "First-gen college student",   weight: "Low",    source: "Admissions" },
            { signal: "Hostel resident",             weight: "Low",    source: "Admissions" },
          ].map((r) => (
            <div key={r.signal} className="flex items-start gap-2">
              <div className="w-1 h-1 rounded-full mt-1.5 flex-shrink-0"
                style={{ background: r.weight === "High" ? "#f87171" : r.weight === "Medium" ? "#fbbf24" : "#94a3b8" }} />
              <span className="text-[11px]" style={{ color: "#64748b" }}>
                {r.signal}
                <span className="ml-1 text-[10px]" style={{ color: "#334155" }}>({r.source})</span>
              </span>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-3 mt-3 pt-3" style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}>
          {[
            { level: "Green", desc: "On track", color: "#34d399" },
            { level: "Amber", desc: "Needs monitoring", color: "#fbbf24" },
            { level: "Red",   desc: "Urgent intervention", color: "#f87171" },
          ].map((l) => (
            <div key={l.level} className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full" style={{ background: l.color }} />
              <span className="text-[11px]" style={{ color: "#64748b" }}>
                <span style={{ color: l.color }}>{l.level}</span> — {l.desc}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* SLA reminder */}
      <div className="p-3 rounded-xl"
        style={{ background: "rgba(251,191,36,0.04)", border: "1px solid rgba(251,191,36,0.08)" }}>
        <div className="flex items-center gap-2 mb-2">
          <Clock className="w-3.5 h-3.5" style={{ color: "#fbbf24" }} />
          <span className="text-[10px] font-bold uppercase tracking-wide" style={{ color: "#475569" }}>
            SLA Enforcement
          </span>
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-[11px]">
          {[
            ["Mentor meeting log", "24 hrs after meeting → HOD notified"],
            ["Parent communication", "48 hrs after AI draft → HOD sends directly"],
            ["Red-level no intervention", "7 days → HOD + Dean auto-escalated"],
            ["Mentor misses meeting", "HOD notified immediately"],
          ].map(([gate, action]) => (
            <div key={gate}>
              <span style={{ color: "#94a3b8" }}>{gate}:</span>{" "}
              <span style={{ color: "#475569" }}>{action}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Red-level students */}
      {redStudents.length > 0 && (
        <div>
          <div className="section-header mb-3" style={{ color: "#f87171" }}>
            <AlertTriangle className="w-3 h-3" />
            Red Alert — Urgent Intervention Required ({redStudents.length})
          </div>
          <div className="space-y-2">
            {redStudents.map((s) => (
              <div key={s.student_id} className="px-4 py-3 rounded-xl"
                style={{ background: "rgba(248,113,113,0.06)", border: "1px solid rgba(248,113,113,0.15)" }}>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-[13px] font-semibold" style={{ color: "#e2e8f0" }}>{s.student_name}</div>
                    <div className="text-[11px] mt-0.5" style={{ color: "#64748b" }}>
                      {s.program} · Mentor: {s.mentor_name ?? "Unassigned"}
                      {s.last_alert && ` · Last alert: ${formatDate(s.last_alert)}`}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="text-[14px] font-bold" style={{ color: "#f87171" }}>
                      {Math.round(s.attendance_pct)}%
                    </div>
                    <button className="px-2.5 py-1 rounded-lg text-[11px] font-semibold"
                      style={{ background: "rgba(248,113,113,0.12)", color: "#f87171", border: "1px solid rgba(248,113,113,0.2)" }}>
                      Intervene
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Amber students */}
      {amberStudents.length > 0 && (
        <div>
          <div className="section-header mb-3">
            <Clock className="w-3 h-3" style={{ color: "#fbbf24" }} />
            Amber — Needs Monitoring ({amberStudents.length})
          </div>
          <div className="space-y-2">
            {amberStudents.map((s) => (
              <div key={s.student_id} className="flex items-center justify-between px-4 py-3 rounded-xl"
                style={{ background: "rgba(251,191,36,0.04)", border: "1px solid rgba(251,191,36,0.1)" }}>
                <div>
                  <span className="text-[12px] font-semibold" style={{ color: "#e2e8f0" }}>{s.student_name}</span>
                  <span className="text-[11px] ml-2" style={{ color: "#64748b" }}>{s.program}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-bold" style={{ color: "#fbbf24" }}>{Math.round(s.attendance_pct)}%</span>
                  <Chip label="AMBER" color="#fbbf24" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {riskStudents.length === 0 && !atRisk.isLoading && (
        <div className="flex flex-col items-center justify-center py-12">
          <CheckCircle className="w-10 h-10 mb-3" style={{ color: "#34d399" }} />
          <p className="text-[13px] font-medium" style={{ color: "#34d399" }}>All students on track</p>
          <p className="text-[11px] mt-1" style={{ color: "#475569" }}>No mentorship interventions required at this time</p>
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────

export default function AcademicsPage() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const insights = useAcademicsInsights();
  const atRisk = useAtRiskStudents();

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 mb-5 px-1">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[9px] font-bold uppercase tracking-[0.18em] mb-1.5 flex items-center gap-2"
              style={{ color: ACCENT }}>
              <span className="module-tag">E05</span>
              Academics Module
            </div>
            <h1 className="text-2xl font-bold leading-tight"
              style={{ fontFamily: "var(--font-family-sans)", color: "#e2e8f0", letterSpacing: "-0.02em" }}>
              Academic Operations
            </h1>
            <p className="text-[12px] mt-0.5" style={{ color: "#64748b" }}>
              AI-driven lifecycle · Calendar → Courses → Timetable → Attendance → Exams
            </p>
          </div>
          <div className="flex items-center gap-2">
            {atRisk.data && atRisk.data.total > 0 && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg"
                style={{ background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.15)" }}>
                <AlertTriangle className="w-3 h-3" style={{ color: "#f87171" }} />
                <span className="text-[11px] font-semibold" style={{ color: "#f87171" }}>
                  {atRisk.data.total} at-risk
                </span>
              </div>
            )}
            <button
              className="btn-ghost flex items-center gap-1.5"
              onClick={() => { insights.refetch(); atRisk.refetch(); }}
            >
              <RefreshCw className={cn("w-3.5 h-3.5", insights.isFetching && "animate-spin")} />
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto pr-1">
        <TabNav active={activeTab} onChange={setActiveTab} />
        {activeTab === "overview"   && <OverviewTab />}
        {activeTab === "courses"    && <CoursesTab />}
        {activeTab === "timetable"  && <TimetableTab />}
        {activeTab === "attendance" && <AttendanceTab />}
        {activeTab === "mentorship" && <MentorshipTab />}
      </div>
    </div>
  );
}
