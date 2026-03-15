import { useState } from "react";
import {
  DollarSign, TrendingUp, TrendingDown, AlertTriangle, CheckCircle2,
  Clock, Users, Percent, Gift, Shield, BarChart3, ChevronRight,
  ArrowUpRight, ArrowDownRight, Landmark,
} from "lucide-react";
import {
  useCollectionReport, useDefaultRisk, useFeeStructures,
  useScholarships, usePendingWaivers, useMonthlyCollection,
} from "@/hooks/use-finance";
import type { FeeStructure, DefaultRisk } from "@/services/finance";

// ── constants ──────────────────────────────────────────────────

const CURRENT_YEAR = "2024-25";

type TabId = "overview" | "fees" | "scholarships" | "waivers" | "risk";

const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: "overview",     label: "Overview",     icon: <BarChart3 className="w-3.5 h-3.5" /> },
  { id: "fees",         label: "Fee Structures", icon: <Landmark className="w-3.5 h-3.5" /> },
  { id: "scholarships", label: "Scholarships",  icon: <Gift className="w-3.5 h-3.5" /> },
  { id: "waivers",      label: "Waivers",       icon: <Shield className="w-3.5 h-3.5" /> },
  { id: "risk",         label: "Default Risk",  icon: <AlertTriangle className="w-3.5 h-3.5" /> },
];

const fmt = (n?: number) =>
  n == null ? "—" : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n);

const fmtShort = (n?: number) => {
  if (n == null) return "—";
  if (n >= 10_000_000) return `₹${(n / 10_000_000).toFixed(1)}Cr`;
  if (n >= 100_000) return `₹${(n / 100_000).toFixed(1)}L`;
  if (n >= 1000) return `₹${(n / 1000).toFixed(1)}K`;
  return `₹${n}`;
};

// ── Overview Tab ───────────────────────────────────────────────

function OverviewTab() {
  const { data: collection, isLoading } = useCollectionReport(CURRENT_YEAR);
  const { data: monthly } = useMonthlyCollection(CURRENT_YEAR);
  const { data: riskData } = useDefaultRisk(CURRENT_YEAR);

  const months = monthly?.months ?? [];
  const maxMonthly = Math.max(...months.map((m) => m.invoiced || 0), 1);

  const kpis = [
    {
      label: "Total Invoiced",
      value: fmtShort(collection?.total_invoiced),
      sub: CURRENT_YEAR,
      icon: <DollarSign className="w-5 h-5" />,
      color: "#818cf8",
      bg: "rgba(99,102,241,0.08)",
      trend: null,
    },
    {
      label: "Collected",
      value: fmtShort(collection?.total_collected),
      sub: `Rate: ${collection?.collection_rate?.toFixed(1) ?? "—"}%`,
      icon: <TrendingUp className="w-5 h-5" />,
      color: "#34d399",
      bg: "rgba(52,211,153,0.08)",
      trend: "up",
    },
    {
      label: "Pending",
      value: fmtShort(collection?.total_pending),
      sub: `${collection?.overdue_count ?? 0} overdue invoices`,
      icon: <Clock className="w-5 h-5" />,
      color: "#fbbf24",
      bg: "rgba(251,191,36,0.08)",
      trend: null,
    },
    {
      label: "Default Risk",
      value: riskData?.total ?? "—",
      sub: "Students at risk",
      icon: <AlertTriangle className="w-5 h-5" />,
      color: "#fb7185",
      bg: "rgba(251,113,133,0.08)",
      trend: null,
    },
  ];

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
            <div className="min-w-0">
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
        {/* Monthly Collection Chart */}
        <div className="col-span-3 rounded-xl p-4"
          style={{ background: "rgba(15,23,42,0.6)", border: "1px solid rgba(51,65,85,0.5)" }}>
          <div className="text-[11px] font-semibold uppercase tracking-widest mb-4" style={{ color: "#64748b" }}>
            Monthly Collection — {CURRENT_YEAR}
          </div>
          {months.length === 0 ? (
            <div className="h-40 flex items-center justify-center text-[12px]" style={{ color: "#475569" }}>
              No monthly data available
            </div>
          ) : (
            <div className="flex items-end gap-2 h-32">
              {months.map((m) => {
                const collectedPct = Math.round((m.collected / maxMonthly) * 100);
                const invoicedPct = Math.round((m.invoiced / maxMonthly) * 100);
                return (
                  <div key={m.month} className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full flex items-end gap-0.5 h-24">
                      <div className="flex-1 rounded-t transition-all duration-700"
                        style={{ height: `${invoicedPct}%`, background: "rgba(129,140,248,0.3)", minHeight: 2 }} />
                      <div className="flex-1 rounded-t transition-all duration-700"
                        style={{ height: `${collectedPct}%`, background: "rgba(52,211,153,0.6)", minHeight: 2 }} />
                    </div>
                    <div className="text-[9px] text-center" style={{ color: "#475569" }}>
                      {m.month.slice(0, 3)}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          <div className="flex gap-4 mt-3">
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm" style={{ background: "rgba(129,140,248,0.6)" }} />
              <span className="text-[10px]" style={{ color: "#64748b" }}>Invoiced</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm" style={{ background: "rgba(52,211,153,0.6)" }} />
              <span className="text-[10px]" style={{ color: "#64748b" }}>Collected</span>
            </div>
          </div>
        </div>

        {/* Summary panel */}
        <div className="col-span-2 space-y-3">
          {/* Collection rate gauge */}
          <div className="rounded-xl p-4"
            style={{ background: "rgba(15,23,42,0.6)", border: "1px solid rgba(51,65,85,0.5)" }}>
            <div className="text-[11px] font-semibold uppercase tracking-widest mb-3" style={{ color: "#64748b" }}>
              Collection Rate
            </div>
            <div className="relative h-3 rounded-full overflow-hidden"
              style={{ background: "rgba(30,41,59,0.8)" }}>
              <div className="absolute inset-y-0 left-0 rounded-full transition-all duration-1000"
                style={{
                  width: `${collection?.collection_rate ?? 0}%`,
                  background: (collection?.collection_rate ?? 0) >= 80
                    ? "linear-gradient(90deg, #34d399, #4ade80)"
                    : (collection?.collection_rate ?? 0) >= 60
                    ? "linear-gradient(90deg, #fbbf24, #f59e0b)"
                    : "linear-gradient(90deg, #fb7185, #f43f5e)",
                }} />
            </div>
            <div className="flex justify-between mt-2">
              <span className="text-[10px]" style={{ color: "#475569" }}>0%</span>
              <span className="text-[13px] font-bold" style={{ color: "#34d399" }}>
                {collection?.collection_rate?.toFixed(1) ?? "—"}%
              </span>
              <span className="text-[10px]" style={{ color: "#475569" }}>100%</span>
            </div>
          </div>

          {/* Overdue summary */}
          <div className="rounded-xl p-4"
            style={{ background: "rgba(251,113,133,0.05)", border: "1px solid rgba(251,113,133,0.15)" }}>
            <div className="flex items-center gap-2 mb-2">
              <TrendingDown className="w-4 h-4" style={{ color: "#fb7185" }} />
              <span className="text-[11px] font-semibold uppercase tracking-widest" style={{ color: "#64748b" }}>
                Overdue
              </span>
            </div>
            <div className="text-[20px] font-bold" style={{ color: "#fb7185" }}>
              {fmtShort(collection?.overdue_amount)}
            </div>
            <div className="text-[11px] mt-0.5" style={{ color: "#94a3b8" }}>
              {collection?.overdue_count ?? 0} invoices past due date
            </div>
          </div>

          {/* Payment methods */}
          <div className="rounded-xl p-3"
            style={{ background: "rgba(15,23,42,0.6)", border: "1px solid rgba(51,65,85,0.5)" }}>
            <div className="text-[10px] font-semibold uppercase tracking-widest mb-2" style={{ color: "#64748b" }}>
              Accepted Methods
            </div>
            <div className="flex flex-wrap gap-1.5">
              {["Razorpay", "UPI", "NEFT", "DD", "Cash", "Cheque"].map((m) => (
                <span key={m} className="px-2 py-0.5 rounded text-[10px] font-medium"
                  style={{ background: "rgba(52,211,153,0.08)", color: "#34d399", border: "1px solid rgba(52,211,153,0.15)" }}>
                  {m}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Finance flow */}
      <div className="rounded-xl p-4"
        style={{ background: "rgba(15,23,42,0.6)", border: "1px solid rgba(51,65,85,0.5)" }}>
        <div className="text-[11px] font-semibold uppercase tracking-widest mb-4" style={{ color: "#64748b" }}>
          Finance Lifecycle
        </div>
        <div className="flex items-center gap-0">
          {[
            { label: "Fee Structure", color: "#818cf8", desc: "Defined per program/semester" },
            { label: "Invoice Generation", color: "#38bdf8", desc: "Bulk auto-generated" },
            { label: "Scholarship/Waiver", color: "#fbbf24", desc: "Discount applied" },
            { label: "Payment Collection", color: "#34d399", desc: "Online + offline modes" },
            { label: "Reconciliation", color: "#4ade80", desc: "Gateway settlement" },
            { label: "Defaulter Action", color: "#fb7185", desc: "Holds + escalation" },
          ].map((s, i) => (
            <div key={s.label} className="flex items-center flex-1">
              <div className="flex-1 p-3 rounded-xl text-center"
                style={{ background: `${s.color}10`, border: `1px solid ${s.color}25` }}>
                <div className="text-[9px] font-bold uppercase tracking-wider mb-1" style={{ color: s.color }}>
                  Step {i + 1}
                </div>
                <div className="text-[11px] font-semibold" style={{ color: "#e2e8f0" }}>{s.label}</div>
                <div className="text-[10px] mt-0.5" style={{ color: "#64748b" }}>{s.desc}</div>
              </div>
              {i < 5 && <ChevronRight className="w-4 h-4 flex-shrink-0 mx-1" style={{ color: "#334155" }} />}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Fee Structures Tab ─────────────────────────────────────────

function FeesTab() {
  const { data, isLoading } = useFeeStructures(CURRENT_YEAR);
  const structures = data?.fee_structures ?? [];

  return (
    <div className="space-y-4">
      <div className="rounded-xl overflow-hidden"
        style={{ border: "1px solid rgba(51,65,85,0.5)" }}>
        <table className="w-full">
          <thead>
            <tr style={{ background: "rgba(15,23,42,0.8)" }}>
              {["Program", "Semester", "Tuition", "Lab", "Exam", "Misc", "Total", "Due Date"].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: "#475569" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              [...Array(4)].map((_, i) => (
                <tr key={i} style={{ borderTop: "1px solid rgba(51,65,85,0.3)" }}>
                  {[...Array(8)].map((_, j) => (
                    <td key={j} className="px-4 py-3">
                      <div className="h-4 rounded animate-pulse" style={{ background: "rgba(51,65,85,0.4)", width: "70%" }} />
                    </td>
                  ))}
                </tr>
              ))
            ) : structures.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-[12px]" style={{ color: "#475569" }}>
                  No fee structures for {CURRENT_YEAR}
                </td>
              </tr>
            ) : structures.map((s: FeeStructure) => (
              <tr key={s.id}
                style={{ borderTop: "1px solid rgba(51,65,85,0.3)" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(30,41,59,0.5)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                <td className="px-4 py-3 text-[12px] font-medium" style={{ color: "#e2e8f0" }}>
                  {s.program_name || s.program_id}
                </td>
                <td className="px-4 py-3 text-[12px]" style={{ color: "#94a3b8" }}>Sem {s.semester}</td>
                <td className="px-4 py-3 text-[12px]" style={{ color: "#94a3b8" }}>{fmtShort(s.tuition_fee)}</td>
                <td className="px-4 py-3 text-[12px]" style={{ color: "#94a3b8" }}>{fmtShort(s.lab_fee)}</td>
                <td className="px-4 py-3 text-[12px]" style={{ color: "#94a3b8" }}>{fmtShort(s.exam_fee)}</td>
                <td className="px-4 py-3 text-[12px]" style={{ color: "#94a3b8" }}>{fmtShort(s.misc_fee)}</td>
                <td className="px-4 py-3 text-[13px] font-bold" style={{ color: "#fbbf24" }}>
                  {fmtShort(s.total_fee)}
                </td>
                <td className="px-4 py-3 text-[11px]" style={{ color: "#64748b" }}>{s.due_date}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Scholarships Tab ───────────────────────────────────────────

function ScholarshipsTab() {
  const { data, isLoading } = useScholarships();
  const scholarships = data?.scholarships ?? [];

  const typeColors: Record<string, string> = {
    MERIT: "#34d399",
    NEED: "#38bdf8",
    SPORTS: "#fbbf24",
    GOVERNMENT: "#818cf8",
    MANAGEMENT: "#fb7185",
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        {isLoading
          ? [...Array(3)].map((_, i) => (
              <div key={i} className="h-28 rounded-xl animate-pulse"
                style={{ background: "rgba(30,41,59,0.5)" }} />
            ))
          : scholarships.slice(0, 6).map((s) => {
              const color = typeColors[s.type] ?? "#64748b";
              return (
                <div key={s.id} className="rounded-xl p-4"
                  style={{ background: `${color}08`, border: `1px solid ${color}20` }}>
                  <div className="flex items-start justify-between mb-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded"
                      style={{ background: `${color}15`, color }}>
                      {s.type}
                    </span>
                    {s.is_active && (
                      <span className="flex items-center gap-1 text-[10px]" style={{ color: "#34d399" }}>
                        <CheckCircle2 className="w-3 h-3" />Active
                      </span>
                    )}
                  </div>
                  <div className="text-[13px] font-semibold mt-2" style={{ color: "#e2e8f0" }}>{s.name}</div>
                  <div className="text-[12px] font-bold mt-1" style={{ color }}>
                    {s.discount_type === "PERCENTAGE" ? `${s.discount_value}%` : fmt(s.discount_value)} off
                  </div>
                </div>
              );
            })}
        {!isLoading && scholarships.length === 0 && (
          <div className="col-span-3 text-center py-10 text-[12px]" style={{ color: "#475569" }}>
            No scholarships configured
          </div>
        )}
      </div>

      {/* Scholarship types info */}
      <div className="rounded-xl p-4"
        style={{ background: "rgba(15,23,42,0.6)", border: "1px solid rgba(51,65,85,0.5)" }}>
        <div className="text-[11px] font-semibold uppercase tracking-widest mb-3" style={{ color: "#64748b" }}>
          Scholarship Categories
        </div>
        <div className="grid grid-cols-5 gap-3">
          {Object.entries(typeColors).map(([type, color]) => (
            <div key={type} className="p-3 rounded-lg text-center"
              style={{ background: `${color}08`, border: `1px solid ${color}20` }}>
              <div className="text-[11px] font-bold" style={{ color }}>{type}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Waivers Tab ────────────────────────────────────────────────

function WaiversTab() {
  const { data, isLoading } = usePendingWaivers();
  const waivers = data?.waivers ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="px-3 py-1.5 rounded-lg flex items-center gap-2 text-[12px]"
          style={{ background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.2)", color: "#fbbf24" }}>
          <Clock className="w-3.5 h-3.5" />
          {isLoading ? "..." : `${data?.total ?? 0} pending`} waiver requests
        </div>
      </div>

      <div className="rounded-xl overflow-hidden"
        style={{ border: "1px solid rgba(51,65,85,0.5)" }}>
        <table className="w-full">
          <thead>
            <tr style={{ background: "rgba(15,23,42,0.8)" }}>
              {["Student", "Requested Amount", "Reason", "Submitted", "Status"].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: "#475569" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              [...Array(3)].map((_, i) => (
                <tr key={i} style={{ borderTop: "1px solid rgba(51,65,85,0.3)" }}>
                  {[...Array(5)].map((_, j) => (
                    <td key={j} className="px-4 py-3">
                      <div className="h-4 rounded animate-pulse" style={{ background: "rgba(51,65,85,0.4)", width: "80%" }} />
                    </td>
                  ))}
                </tr>
              ))
            ) : waivers.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-[12px]" style={{ color: "#475569" }}>
                  No pending waiver requests
                </td>
              </tr>
            ) : waivers.map((w) => (
              <tr key={w.id}
                style={{ borderTop: "1px solid rgba(51,65,85,0.3)" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(30,41,59,0.5)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                <td className="px-4 py-3 text-[12px]" style={{ color: "#e2e8f0" }}>
                  {w.student_name || w.student_id}
                </td>
                <td className="px-4 py-3 text-[12px] font-semibold" style={{ color: "#fbbf24" }}>
                  {fmt(w.requested_amount)}
                </td>
                <td className="px-4 py-3 text-[11px] max-w-[200px] truncate" style={{ color: "#94a3b8" }}>
                  {w.reason}
                </td>
                <td className="px-4 py-3 text-[11px]" style={{ color: "#64748b" }}>
                  {w.requested_at?.split("T")[0]}
                </td>
                <td className="px-4 py-3">
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold"
                    style={{
                      background: w.status === "PENDING" ? "rgba(251,191,36,0.12)" : "rgba(52,211,153,0.12)",
                      color: w.status === "PENDING" ? "#fbbf24" : "#34d399",
                    }}>
                    {w.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Default Risk Tab ───────────────────────────────────────────

function DefaultRiskTab() {
  const { data, isLoading } = useDefaultRisk(CURRENT_YEAR);
  const students = data?.students ?? [];

  const riskConfig = {
    LOW:      { color: "#34d399", bg: "rgba(52,211,153,0.1)" },
    MEDIUM:   { color: "#fbbf24", bg: "rgba(251,191,36,0.1)" },
    HIGH:     { color: "#fb923c", bg: "rgba(251,146,60,0.1)" },
    CRITICAL: { color: "#fb7185", bg: "rgba(251,113,133,0.1)" },
  };

  const summary = ["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((level) => ({
    level,
    count: students.filter((s) => s.risk_level === level).length,
    ...riskConfig[level as keyof typeof riskConfig],
  }));

  return (
    <div className="space-y-4">
      {/* Risk summary row */}
      <div className="grid grid-cols-4 gap-4">
        {summary.map((s) => (
          <div key={s.level} className="rounded-xl p-4"
            style={{ background: s.bg, border: `1px solid ${s.color}25` }}>
            <div className="text-[24px] font-bold" style={{ color: s.color }}>
              {isLoading ? "—" : s.count}
            </div>
            <div className="text-[11px] font-semibold" style={{ color: s.color }}>{s.level}</div>
            <div className="text-[10px]" style={{ color: "#64748b" }}>risk students</div>
          </div>
        ))}
      </div>

      {/* Risk table */}
      <div className="rounded-xl overflow-hidden"
        style={{ border: "1px solid rgba(51,65,85,0.5)" }}>
        <table className="w-full">
          <thead>
            <tr style={{ background: "rgba(15,23,42,0.8)" }}>
              {["Student", "Roll No", "Balance Due", "Days Overdue", "Risk Level"].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: "#475569" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i} style={{ borderTop: "1px solid rgba(51,65,85,0.3)" }}>
                  {[...Array(5)].map((_, j) => (
                    <td key={j} className="px-4 py-3">
                      <div className="h-4 rounded animate-pulse" style={{ background: "rgba(51,65,85,0.4)", width: "75%" }} />
                    </td>
                  ))}
                </tr>
              ))
            ) : students.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-[12px]" style={{ color: "#475569" }}>
                  <CheckCircle2 className="w-6 h-6 mx-auto mb-2" style={{ color: "#34d399", opacity: 0.5 }} />
                  No students at default risk
                </td>
              </tr>
            ) : students.map((s: DefaultRisk) => {
              const rc = riskConfig[s.risk_level] ?? riskConfig.LOW;
              return (
                <tr key={s.student_id}
                  style={{ borderTop: "1px solid rgba(51,65,85,0.3)" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(30,41,59,0.5)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                  <td className="px-4 py-3 text-[12px]" style={{ color: "#e2e8f0" }}>{s.student_name}</td>
                  <td className="px-4 py-3 text-[11px]" style={{ color: "#64748b" }}>{s.roll_number || "—"}</td>
                  <td className="px-4 py-3 text-[12px] font-semibold" style={{ color: "#fb7185" }}>
                    {fmt(s.balance)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <div className="w-1.5 h-1.5 rounded-full" style={{ background: rc.color }} />
                      <span className="text-[12px]" style={{ color: s.days_overdue > 30 ? "#fb7185" : "#94a3b8" }}>
                        {s.days_overdue} days
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded text-[10px] font-semibold"
                      style={{ background: rc.bg, color: rc.color }}>
                      {s.risk_level}
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

export default function FinancePage() {
  const [tab, setTab] = useState<TabId>("overview");

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 px-6 pt-5 pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: "rgba(251,191,36,0.1)", border: "1px solid rgba(251,191,36,0.2)" }}>
              <DollarSign className="w-4.5 h-4.5" style={{ color: "#fbbf24" }} />
            </div>
            <div>
              <h1 className="text-[18px] font-bold leading-none" style={{ color: "#e2e8f0" }}>
                Finance
              </h1>
              <p className="text-[11px] mt-0.5" style={{ color: "#64748b" }}>
                E07 · Fee Collection · Scholarships · Waivers · Default Risk
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-[11px]"
            style={{ background: "rgba(251,191,36,0.06)", border: "1px solid rgba(251,191,36,0.15)", color: "#fbbf24" }}>
            <CheckCircle2 className="w-3.5 h-3.5" />
            {CURRENT_YEAR}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 mt-4">
          {tabs.map((t) => (
            <button key={t.id}
              onClick={() => setTab(t.id)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all"
              style={{
                background: tab === t.id ? "rgba(251,191,36,0.12)" : "transparent",
                color: tab === t.id ? "#fbbf24" : "#64748b",
                border: `1px solid ${tab === t.id ? "rgba(251,191,36,0.25)" : "transparent"}`,
              }}>
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        {tab === "overview"     && <OverviewTab />}
        {tab === "fees"         && <FeesTab />}
        {tab === "scholarships" && <ScholarshipsTab />}
        {tab === "waivers"      && <WaiversTab />}
        {tab === "risk"         && <DefaultRiskTab />}
      </div>
    </div>
  );
}
