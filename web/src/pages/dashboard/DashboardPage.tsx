import { Users, FileText, AlertTriangle, TrendingUp, CheckCircle, Clock, Sparkles } from "lucide-react";

const MODULES = [
  { name: "Admissions", badge: "E04", path: "/admissions", status: "ACTIVE", color: "#818cf8", count: 147, label: "active applications" },
  { name: "Academics", badge: "E05", path: "/academics", status: "ACTIVE", color: "#60a5fa", count: 24, label: "courses running" },
  { name: "Examinations", badge: "E06", path: "/examinations", status: "IDLE", color: "#34d399", count: 0, label: "exams scheduled" },
  { name: "Finance", badge: "E07", path: "/finance", status: "ACTIVE", color: "#fbbf24", count: 8, label: "pending reconciliations" },
  { name: "HR & Staff", badge: "E08", path: "/hr", status: "IDLE", color: "#f472b6", count: 0, label: "open actions" },
  { name: "Communication", badge: "E10", path: "/communications", status: "ACTIVE", color: "#22d3ee", count: 127, label: "emails sent today" },
];

const RECENT_ACTIVITY = [
  { time: "09:42", icon: CheckCircle, color: "#34d399", text: "Merit list published — B.Tech CSE (General)" },
  { time: "09:31", icon: Sparkles, color: "#a78bfa", text: "AI ran eligibility check on 124 applications" },
  { time: "09:18", icon: FileText, color: "#818cf8", text: "38 offer letters generated and dispatched" },
  { time: "08:55", icon: AlertTriangle, color: "#fbbf24", text: "Plagiarism flag raised — 1 essay requires review" },
  { time: "08:30", icon: Users, color: "#60a5fa", text: "14 new leads captured from website inquiry form" },
];

export default function DashboardPage() {
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
        {[
          { icon: Users, label: "Total Students", value: "3,284", color: "#818cf8", delta: "+142 this month" },
          { icon: FileText, label: "Active Applications", value: "147", color: "#60a5fa", delta: "+23 this week" },
          { icon: AlertTriangle, label: "Pending Reviews", value: "12", color: "#fbbf24", delta: "Action required", alert: true },
          { icon: TrendingUp, label: "Revenue MTD", value: "₹48.2L", color: "#34d399", delta: "+8.4% vs last month" },
        ].map((kpi) => {
          const Icon = kpi.icon;
          return (
            <div
              key={kpi.label}
              className="p-5 rounded-xl"
              style={{
                background: "rgba(255,255,255,0.03)",
                border: `1px solid ${kpi.alert ? "rgba(251,191,36,0.15)" : "rgba(255,255,255,0.06)"}`,
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
              <div className="text-[10px] mt-1.5" style={{ color: kpi.alert ? "#fbbf24" : "#475569" }}>{kpi.delta}</div>
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
            {MODULES.map((mod) => (
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
                  <span className={`text-[9px] font-semibold uppercase ${mod.status === "ACTIVE" ? "" : ""}`}
                    style={{ color: mod.status === "ACTIVE" ? "#34d399" : "#475569" }}>
                    {mod.status}
                  </span>
                </div>
                <div className="text-[12px] font-semibold mb-1" style={{ color: "#cbd5e1" }}>{mod.name}</div>
                <div className="text-[11px]" style={{ color: "#475569" }}>
                  <span style={{ color: mod.color }}>{mod.count}</span> {mod.label}
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
          <div className="space-y-3">
            {RECENT_ACTIVITY.map((item, i) => {
              const Icon = item.icon;
              return (
                <div key={i} className="flex items-start gap-3">
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: `${item.color}12`, border: `1px solid ${item.color}25` }}>
                    <Icon className="w-3.5 h-3.5" style={{ color: item.color }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[11px] leading-relaxed" style={{ color: "#94a3b8" }}>{item.text}</p>
                    <p className="text-[10px] mt-0.5" style={{ color: "#475569" }}>{item.time}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
