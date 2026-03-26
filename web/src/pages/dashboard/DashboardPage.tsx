import { useState, useEffect } from "react";
import { Users, FileText, AlertTriangle, TrendingUp, CheckCircle, Clock, Sparkles } from "lucide-react";

// ── Types ──────────────────────────────────────────────────────────────────

interface DashboardKpis {
  admissions?: {
    total_applications?: number;
    enrolled?: number;
    offers_pending?: number;
    under_review?: number;
  };
  academics?: {
    total_enrolled?: number;
    active_courses?: number;
  };
  finance?: {
    pending_reconciliations?: number;
    revenue_mtd?: number;
  };
  hr?: {
    open_leave_requests?: number;
  };
}

interface AuditEntry {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  actor_role: string;
  metadata: Record<string, unknown>;
  timestamp: string;
}

// ── API helpers ────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string): Promise<T | null> {
  try {
    const token = localStorage.getItem("token") ?? "";
    const res = await fetch(`/api/v1${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    return res.json() as Promise<T>;
  } catch {
    return null;
  }
}

// ── Activity label mapping ─────────────────────────────────────────────────

function describeAuditEntry(entry: AuditEntry): { text: string; icon: typeof CheckCircle; color: string } {
  const { action, entity_type, metadata } = entry;
  const meta = metadata ?? {};

  const entityLabel = String(meta.entity_id ?? meta.action_type ?? entity_type ?? "").replace(/_/g, " ");

  if (action === "create" && entity_type === "application")
    return { text: `New application submitted${entityLabel ? ` — ${entityLabel}` : ""}`, icon: FileText, color: "#818cf8" };
  if (action === "create" && entity_type === "approval_request")
    return { text: `Approval requested: ${entityLabel || entity_type}`, icon: AlertTriangle, color: "#fbbf24" };
  if (entity_type === "approval_request" && (action === "approve" || action === "approved"))
    return { text: `Approved: ${entityLabel || entity_type}`, icon: CheckCircle, color: "#34d399" };
  if (action === "login")
    return { text: `User signed in (${String(meta.username ?? entry.actor_role ?? "")})`, icon: Users, color: "#60a5fa" };
  if (entity_type === "merit_list")
    return { text: "Merit list generated", icon: Sparkles, color: "#a78bfa" };

  return {
    text: `${action.replace(/_/g, " ")} · ${entity_type.replace(/_/g, " ")}`,
    icon: Clock,
    color: "#475569",
  };
}

function formatActivityTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
}

// ── Module config ──────────────────────────────────────────────────────────

const MODULE_BASE = [
  { name: "Admissions",    badge: "E04", path: "/admissions",    color: "#818cf8", label: "active applications",      kpiKey: "admissions.total_applications" },
  { name: "Academics",     badge: "E05", path: "/academics",     color: "#60a5fa", label: "courses running",           kpiKey: "academics.active_courses" },
  { name: "Examinations",  badge: "E06", path: "/examinations",  color: "#34d399", label: "exams scheduled",           kpiKey: null },
  { name: "Finance",       badge: "E07", path: "/finance",       color: "#fbbf24", label: "pending reconciliations",   kpiKey: "finance.pending_reconciliations" },
  { name: "HR & Staff",    badge: "E08", path: "/hr",            color: "#f472b6", label: "open leave requests",       kpiKey: "hr.open_leave_requests" },
  { name: "Communication", badge: "E10", path: "/communications",color: "#22d3ee", label: "enrolled students",         kpiKey: "academics.total_enrolled" },
];

function resolveKpi(kpis: DashboardKpis | null, key: string | null): number {
  if (!kpis || !key) return 0;
  const [section, field] = key.split(".") as [keyof DashboardKpis, string];
  return Number((kpis[section] as Record<string, unknown>)?.[field] ?? 0);
}

// ── Component ──────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [kpis, setKpis] = useState<DashboardKpis | null>(null);
  const [activity, setActivity] = useState<AuditEntry[]>([]);

  const currentYear = new Date().getFullYear();
  const academicYear = `${currentYear}-${String(currentYear + 1).slice(-2)}`;

  useEffect(() => {
    apiFetch<DashboardKpis>(`/reports/dashboard/kpis?academic_year=${academicYear}`).then(d => {
      if (d) setKpis(d);
    });
    apiFetch<AuditEntry[]>(`/audit/logs?limit=5`).then(d => {
      if (d) setActivity(d);
    });
  }, [academicYear]);

  const totalStudents = resolveKpi(kpis, "academics.total_enrolled");
  const activeApps    = resolveKpi(kpis, "admissions.total_applications");
  const pendingReview = resolveKpi(kpis, "admissions.under_review");
  const revenueMtd    = resolveKpi(kpis, "finance.revenue_mtd");

  const modules = MODULE_BASE.map(m => ({
    ...m,
    count: resolveKpi(kpis, m.kpiKey),
    status: resolveKpi(kpis, m.kpiKey) > 0 ? "ACTIVE" : "IDLE",
  }));

  const kpiRow = [
    {
      icon: Users,
      label: "Total Students",
      value: totalStudents > 0 ? totalStudents.toLocaleString("en-IN") : "—",
      color: "#818cf8",
      delta: "enrolled this year",
    },
    {
      icon: FileText,
      label: "Active Applications",
      value: activeApps > 0 ? activeApps.toLocaleString("en-IN") : "—",
      color: "#60a5fa",
      delta: `intake ${academicYear}`,
    },
    {
      icon: AlertTriangle,
      label: "Pending Reviews",
      value: pendingReview > 0 ? pendingReview.toLocaleString("en-IN") : "—",
      color: "#fbbf24",
      delta: "Action required",
      alert: pendingReview > 0,
    },
    {
      icon: TrendingUp,
      label: "Revenue MTD",
      value: revenueMtd > 0 ? `₹${(revenueMtd / 100000).toFixed(1)}L` : "—",
      color: "#34d399",
      delta: "month to date",
    },
  ];

  return (
    <div className="space-y-6 fade-up-1">
      {/* Header */}
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.15em] mb-1" style={{ color: "#818cf8" }}>
          Overview
        </p>
        <h1 className="text-2xl font-bold" style={{ fontFamily: "var(--font-family-sans)", color: "#e2e8f0", letterSpacing: "-0.02em" }}>
          System Dashboard
        </h1>
        <p className="text-[12px] mt-0.5" style={{ color: "#64748b" }}>
          All epics operational · {new Date().toLocaleDateString("en-IN", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
        </p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-4 gap-4 fade-up-2">
        {kpiRow.map((kpi) => {
          const Icon = kpi.icon;
          return (
            <div
              key={kpi.label}
              className="p-5 rounded-xl"
              style={{
                background: "rgba(255,255,255,0.03)",
                border: `1px solid ${"alert" in kpi && kpi.alert ? "rgba(251,191,36,0.15)" : "rgba(255,255,255,0.06)"}`,
              }}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center"
                  style={{ background: `${kpi.color}18`, border: `1px solid ${kpi.color}30` }}>
                  <Icon className="w-4 h-4" style={{ color: kpi.color }} />
                </div>
              </div>
              <div className="text-2xl font-bold mb-0.5" style={{ fontFamily: "var(--font-family-sans)", color: "#e2e8f0" }}>
                {kpi.value}
              </div>
              <div className="text-[11px] font-medium" style={{ color: "#64748b" }}>{kpi.label}</div>
              <div className="text-[10px] mt-1.5" style={{ color: "alert" in kpi && kpi.alert ? "#fbbf24" : "#475569" }}>{kpi.delta}</div>
            </div>
          );
        })}
      </div>

      {/* Module grid + Activity */}
      <div className="grid grid-cols-3 gap-5 fade-up-3">
        {/* Modules */}
        <div className="col-span-2">
          <div className="section-header mb-4">
            <Sparkles className="w-3 h-3" style={{ color: "#475569" }} />
            Module Status
          </div>
          <div className="grid grid-cols-3 gap-3">
            {modules.map((mod) => (
              <div
                key={mod.name}
                className="p-4 rounded-xl cursor-pointer transition-all"
                style={{
                  background: "rgba(255,255,255,0.025)",
                  border: "1px solid rgba(255,255,255,0.055)",
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.045)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.025)"; }}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[9px] font-bold px-1.5 py-0.5 rounded"
                    style={{ background: `${mod.color}18`, color: mod.color, border: `1px solid ${mod.color}30` }}>
                    {mod.badge}
                  </span>
                  <span className="text-[9px] font-semibold uppercase"
                    style={{ color: mod.status === "ACTIVE" ? "#34d399" : "#475569" }}>
                    {mod.status}
                  </span>
                </div>
                <div className="text-[12px] font-semibold mb-1" style={{ color: "#cbd5e1" }}>{mod.name}</div>
                <div className="text-[11px]" style={{ color: "#475569" }}>
                  <span style={{ color: mod.color }}>{mod.count > 0 ? mod.count : "—"}</span> {mod.label}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Activity feed */}
        <div>
          <div className="section-header mb-4">
            <Clock className="w-3 h-3" style={{ color: "#475569" }} />
            Recent Activity
          </div>
          {activity.length === 0 ? (
            <p className="text-[11px]" style={{ color: "#475569" }}>No recent activity.</p>
          ) : (
            <div className="space-y-3">
              {activity.map((entry) => {
                const { text, icon: Icon, color } = describeAuditEntry(entry);
                return (
                  <div key={entry.id} className="flex items-start gap-3">
                    <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={{ background: `${color}12`, border: `1px solid ${color}25` }}>
                      <Icon className="w-3.5 h-3.5" style={{ color }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[11px] leading-relaxed" style={{ color: "#94a3b8" }}>{text}</p>
                      <p className="text-[10px] mt-0.5" style={{ color: "#475569" }}>{formatActivityTime(entry.timestamp)}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
