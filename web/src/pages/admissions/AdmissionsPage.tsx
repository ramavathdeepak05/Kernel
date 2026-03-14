import { useState, useEffect } from "react";
import {
  AlertTriangle,
  Bot,
  CheckCircle,
  Clock,
  FileText,
  Loader2,
  RefreshCw,
  Sparkles,
  TrendingUp,
  Users,
  XCircle,
  ChevronRight,
  Filter,
  Settings,
  Save,
  RotateCcw,
  Info,
} from "lucide-react";
import { useReviewQueue, usePipelineSummary, useDocumentReviewQueue, useEntranceTests, useMeritLists, useOffers, useLeads, useApplications } from "@/hooks/use-admissions";
import { STATUS_LABELS, STATUS_COLORS } from "@/types/admissions";
import { cn, formatDate } from "@/lib/utils";
import { policiesApi, type InstitutionPolicy } from "@/services/admissions";

// ── Sparkline component ──────────────────────────────────────

const SPARKLINE_DATA = [14, 18, 22, 16, 28, 32, 24, 38, 42, 36, 44, 47, 52, 48, 55, 60, 58, 65, 62, 71];

function SparklineChart({ data, color }: { data: number[]; color: string }) {
  const max = Math.max(...data);
  return (
    <div className="sparkline-track">
      {data.map((v, i) => (
        <div
          key={i}
          className="sparkline-bar"
          style={{
            height: `${(v / max) * 100}%`,
            background: i === data.length - 1
              ? color
              : `${color}60`,
            opacity: 0.6 + (i / data.length) * 0.4,
          }}
        />
      ))}
    </div>
  );
}

// ── Analytics bar ────────────────────────────────────────────

function AnalyticsBar() {
  const pipeline = usePipelineSummary();

  const stats = pipeline.data ?? [
    { name: "LEAD", count: 284 },
    { name: "APPLIED", count: 147 },
    { name: "ELIGIBLE", count: 98 },
    { name: "ADMITTED", count: 42 },
    { name: "ENROLLED", count: 19 },
  ];

  return (
    <div className="mb-6 p-4 rounded-xl" style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-3.5 h-3.5" style={{ color: "#818cf8" }} />
          <span className="text-[10px] font-semibold uppercase tracking-[0.12em]" style={{ color: "#64748b" }}>
            Admissions Pace · Intake 2025
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="status-dot-live" />
          <span className="text-[10px]" style={{ color: "#475569" }}>Live</span>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-3">
        {stats.map((stage, idx) => {
          const colors = ["#818cf8", "#60a5fa", "#34d399", "#fbbf24", "#a78bfa"];
          const color = colors[idx % colors.length];
          const sparkData = SPARKLINE_DATA.slice(-12).map((v, i) =>
            Math.max(2, Math.round(v * (0.3 + idx * 0.15) * (0.8 + i * 0.02)))
          );

          return (
            <div key={stage.name} className="flex flex-col gap-1">
              <div className="flex items-end justify-between">
                <span className="text-[9px] uppercase tracking-widest font-semibold" style={{ color: "#475569" }}>
                  {stage.name}
                </span>
                <span className="text-[14px] font-bold" style={{ color, fontFamily: "var(--font-family-mono)" }}>
                  {stage.count}
                </span>
              </div>
              <SparklineChart data={sparkData} color={color} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Review inbox card ────────────────────────────────────────

interface InboxItem {
  id: string;
  type: "ai_review" | "alert" | "approval" | "exception";
  title: string;
  subtitle: string;
  confidence?: number;
  applicationId?: string;
  priority: "high" | "medium" | "low";
  age: string;
  actions: { label: string; variant: "approve" | "review" | "reject" | "ghost" }[];
}

const MOCK_INBOX: InboxItem[] = [
  {
    id: "1",
    type: "approval",
    title: "Approve Conditional Offer: Sarah Jenkins",
    subtitle: "B.Tech Computer Engineering · APP-2025-000089",
    confidence: 88,
    applicationId: "APP-2025-000089",
    priority: "high",
    age: "23m ago",
    actions: [
      { label: "Approve Offer", variant: "approve" },
      { label: "Review", variant: "ghost" },
    ],
  },
  {
    id: "2",
    type: "alert",
    title: "Review: Essay Plagiarism Score High",
    subtitle: "Rohan Desai · MBA · Turnitin: 41% match",
    priority: "high",
    age: "1h ago",
    actions: [
      { label: "Review Essay", variant: "review" },
      { label: "Flag & Hold", variant: "ghost" },
    ],
  },
  {
    id: "3",
    type: "ai_review",
    title: "Borderline Eligibility: Priya Sharma",
    subtitle: "12th marks: 59.8% (threshold 60.0%) · 0.2% gap",
    confidence: 72,
    applicationId: "APP-2025-000134",
    priority: "medium",
    age: "2h ago",
    actions: [
      { label: "Grant Override", variant: "approve" },
      { label: "Decline", variant: "reject" },
    ],
  },
  {
    id: "4",
    type: "exception",
    title: "Payment Gateway Timeout: 3 Applicants",
    subtitle: "Razorpay ORDER_IDs: RPY-8831, RPY-8832, RPY-8834",
    priority: "medium",
    age: "3h ago",
    actions: [
      { label: "Reconcile", variant: "review" },
    ],
  },
];

function InboxCard({ item }: { item: InboxItem }) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  const isAI = item.type === "ai_review" || item.type === "approval";
  const isAlert = item.type === "alert";

  return (
    <div className={cn("queue-card p-4 mb-3", item.priority === "high" && "queue-card-urgent")}>
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
          style={{
            background: isAI
              ? "rgba(167,139,250,0.12)"
              : isAlert
              ? "rgba(251,191,36,0.1)"
              : "rgba(251,113,133,0.1)",
            border: `1px solid ${isAI ? "rgba(167,139,250,0.22)" : isAlert ? "rgba(251,191,36,0.22)" : "rgba(251,113,133,0.22)"}`,
          }}>
          {isAI ? (
            <Bot className="w-4 h-4" style={{ color: "#a78bfa" }} />
          ) : isAlert ? (
            <AlertTriangle className="w-4 h-4" style={{ color: "#fbbf24" }} />
          ) : (
            <XCircle className="w-4 h-4" style={{ color: "#fb7185" }} />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <p className="text-[13px] font-semibold leading-tight" style={{ color: "#e2e8f0" }}>
              {item.title}
            </p>
            <span className="text-[10px] flex-shrink-0" style={{ color: "#475569" }}>{item.age}</span>
          </div>
          <p className="text-[11px] mt-1 leading-relaxed" style={{ color: "#64748b" }}>
            {item.subtitle}
          </p>

          {/* AI confidence */}
          {item.confidence !== undefined && (
            <div className="flex items-center gap-2 mt-2">
              <Sparkles className="w-3 h-3" style={{ color: "#64748b" }} />
              <span className="text-[10px]" style={{ color: "#64748b" }}>
                AI Confidence:
              </span>
              <span
                className={cn(
                  "text-[10px] font-bold px-1.5 py-0.5 rounded",
                  item.confidence >= 80 ? "confidence-high" : item.confidence >= 60 ? "confidence-medium" : "confidence-low"
                )}
              >
                {item.confidence}%
              </span>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-2 mt-3">
            {item.actions.map((action) => (
              <button
                key={action.label}
                onClick={() => setDismissed(true)}
                className={cn(
                  action.variant === "approve" && "btn-approve",
                  action.variant === "review" && "btn-review",
                  action.variant === "reject" && "btn-ghost",
                  action.variant === "ghost" && "btn-ghost"
                )}
              >
                {action.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Future items ─────────────────────────────────────────────

const MOCK_FUTURE_ITEMS = [
  { id: "f1", label: "Batch eligibility check", detail: "124 applications · ~3 min", status: "running" },
  { id: "f2", label: "NTA score import", detail: "JEE Mains 2025 · queued", status: "queued" },
  { id: "f3", label: "Offer letter generation", detail: "38 admitted students · ready", status: "ready" },
  { id: "f4", label: "DigiLocker verification", detail: "12 applicants · pending API", status: "queued" },
];

function FutureItemsSection() {
  return (
    <div className="mt-6">
      <div className="section-header">
        <RefreshCw className="w-3 h-3" style={{ color: "#475569" }} />
        Future Items (Processing)
      </div>
      <div className="space-y-2">
        {MOCK_FUTURE_ITEMS.map((item) => (
          <div key={item.id} className="processing-card">
            <div
              className={item.status === "running" ? "status-dot-processing" : "w-1.5 h-1.5 rounded-full flex-shrink-0"}
              style={item.status !== "running" ? {
                background: item.status === "ready" ? "#34d399" : "#334155",
              } : undefined}
            />
            <div className="flex-1 min-w-0">
              <div className="text-[12px] font-medium" style={{ color: "#94a3b8" }}>{item.label}</div>
              <div className="text-[10px] mt-0.5" style={{ color: "#475569" }}>{item.detail}</div>
            </div>
            <div className="text-[10px] font-semibold uppercase tracking-wider flex-shrink-0"
              style={{
                color: item.status === "running" ? "#fbbf24"
                  : item.status === "ready" ? "#34d399"
                  : "#475569",
              }}>
              {item.status}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Tab content views ────────────────────────────────────────

type TabId = "inbox" | "leads" | "applications" | "documents" | "tests" | "merit" | "offers" | "enrollment" | "settings";

function TabNav({ active, onChange }: { active: TabId; onChange: (t: TabId) => void }) {
  const tabs: { id: TabId; label: string }[] = [
    { id: "inbox", label: "Inbox" },
    { id: "leads", label: "Leads" },
    { id: "applications", label: "Applications" },
    { id: "documents", label: "Documents" },
    { id: "tests", label: "Tests" },
    { id: "merit", label: "Merit List" },
    { id: "offers", label: "Offers" },
    { id: "enrollment", label: "Enrollment" },
    { id: "settings", label: "Policy Rules" },
  ];

  return (
    <div className="flex items-center gap-1 mb-5 overflow-x-auto pb-1"
      style={{ scrollbarWidth: "none" }}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className="flex-shrink-0 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all"
          style={{
            background: active === tab.id ? "rgba(129,140,248,0.12)" : "transparent",
            border: `1px solid ${active === tab.id ? "rgba(129,140,248,0.25)" : "transparent"}`,
            color: active === tab.id ? "#818cf8" : "#64748b",
          }}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function DataTable({ columns, rows, isLoading }: {
  columns: string[];
  rows: (string | JSX.Element)[][];
  isLoading?: boolean;
}) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="skeleton-dark h-10 rounded-lg" />
        ))}
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12" style={{ color: "#334155" }}>
        <CheckCircle className="w-8 h-8 mb-3" />
        <p className="text-[13px] font-medium">All clear</p>
        <p className="text-[11px] mt-1">No items to review</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
            {columns.map((col) => (
              <th key={col} className="text-left pb-3 px-2 text-[9px] font-semibold uppercase tracking-[0.12em]"
                style={{ color: "#475569" }}>
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className="group cursor-pointer transition-colors"
              style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.02)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              {row.map((cell, j) => (
                <td key={j} className="py-3 px-2 text-[12px]" style={{ color: j === 0 ? "#cbd5e1" : "#94a3b8" }}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusChip({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? "bg-slate-800 text-slate-400 border-slate-700";
  const label = STATUS_LABELS[status] ?? status;
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider", color)}>
      {label}
    </span>
  );
}

function LeadsTab() {
  const leads = useLeads({ limit: 20 });
  const rows = (leads.data ?? []).map((l) => [
    `${l.first_name} ${l.last_name}`,
    l.email,
    l.course_interest ?? "—",
    l.source_channel ?? "—",
    <StatusChip key={l.id} status={l.status} />,
    formatDate(l.created_at),
  ]);
  return <DataTable columns={["Name", "Email", "Interest", "Source", "Status", "Date"]} rows={rows} isLoading={leads.isLoading} />;
}

function ApplicationsTab() {
  const apps = useApplications({ limit: 20 });
  const rows = (apps.data ?? []).map((a) => [
    a.application_id,
    `${a.first_name} ${a.last_name}`,
    a.program,
    <StatusChip key={a.id} status={a.status} />,
    formatDate(a.created_at),
    <button key={a.id} className="btn-ghost text-[10px] h-6 px-2">View <ChevronRight className="inline w-3 h-3" /></button>,
  ]);
  return <DataTable columns={["App ID", "Applicant", "Program", "Status", "Date", ""]} rows={rows} isLoading={apps.isLoading} />;
}

function DocumentsTab() {
  const docs = useDocumentReviewQueue({ limit: 20 });
  const rows = (docs.data ?? []).map((d) => [
    d.application_id.slice(0, 12) + "...",
    d.document_type.replace(/_/g, " "),
    <StatusChip key={d.id} status={d.status} />,
    formatDate(d.uploaded_at),
    <div key={d.id} className="flex gap-1.5">
      <button className="btn-approve h-6 px-2 text-[9px]">Approve</button>
      <button className="btn-review h-6 px-2 text-[9px]">Reject</button>
    </div>,
  ]);
  return <DataTable columns={["Application", "Document", "Status", "Uploaded", "Actions"]} rows={rows} isLoading={docs.isLoading} />;
}

function TestsTab() {
  const tests = useEntranceTests();
  const rows = (tests.data ?? []).map((t) => [
    t.name,
    t.code,
    t.mode,
    formatDate(t.date),
    <span key={t.id} className={cn(
      "text-[10px] font-semibold uppercase",
      t.status === "UPCOMING" ? "text-blue-400" : t.status === "COMPLETED" ? "text-emerald-400" : "text-amber-400"
    )}>{t.status}</span>,
    String(t.registered_count ?? 0),
  ]);
  return <DataTable columns={["Name", "Code", "Mode", "Date", "Status", "Registered"]} rows={rows} isLoading={tests.isLoading} />;
}

function MeritTab() {
  const merit = useMeritLists();
  const rows = (merit.data ?? []).map((m) => [
    m.program,
    m.category,
    `Round ${m.round}`,
    String(m.total_seats),
    String(m.allocated_seats),
    <span key={m.id} className={cn(
      "text-[10px] font-semibold uppercase",
      m.status === "PUBLISHED" ? "text-emerald-400" : m.status === "APPROVED" ? "text-blue-400" : "text-amber-400"
    )}>{m.status}</span>,
  ]);
  return <DataTable columns={["Program", "Category", "Round", "Seats", "Allocated", "Status"]} rows={rows} isLoading={merit.isLoading} />;
}

function OffersTab() {
  const offers = useOffers();
  const rows = (offers.data ?? []).map((o) => [
    o.offer_reference,
    o.applicant_name ?? "—",
    o.program ?? "—",
    <StatusChip key={o.id} status={o.status} />,
    formatDate(o.issued_at),
    formatDate(o.acceptance_deadline),
  ]);
  return <DataTable columns={["Reference", "Applicant", "Program", "Status", "Issued", "Deadline"]} rows={rows} isLoading={offers.isLoading} />;
}

function EnrollmentTab() {
  return (
    <div className="flex flex-col items-center justify-center py-16" style={{ color: "#334155" }}>
      <Users className="w-10 h-10 mb-3 opacity-40" />
      <p className="text-[13px] font-medium" style={{ color: "#64748b" }}>Enrollment data loads when documents are cleared</p>
      <p className="text-[11px] mt-1" style={{ color: "#475569" }}>Stage 10 — Final provisioning</p>
    </div>
  );
}

// ── Policy / Rules Wizard ────────────────────────────────────

const POLICY_META: Record<string, { label: string; description: string; type: "number" | "boolean"; unit?: string; min?: number; max?: number; step?: number }> = {
  "admissions.eligibility.min_academic_percentage": {
    label: "Min Academic Percentage",
    description: "Minimum aggregate % required for eligibility. Applicants below this are auto-rejected.",
    type: "number", unit: "%", min: 0, max: 100, step: 1,
  },
  "admissions.eligibility.review_band_lower": {
    label: "Review Band Lower Threshold",
    description: "Applicants between this % and min academic % are flagged for manual review instead of auto-reject.",
    type: "number", unit: "%", min: 0, max: 100, step: 1,
  },
  "admissions.eligibility.min_entrance_score": {
    label: "Min Entrance Test Score",
    description: "Minimum score required on entrance test. Scores below this fail eligibility.",
    type: "number", unit: "pts", min: 0, max: 100, step: 1,
  },
  "admissions.eligibility.docs_required_for_offer": {
    label: "Documents Required Before Offer",
    description: "When enabled, offer letters are only generated after all documents are approved.",
    type: "boolean",
  },
  "admissions.counsellor.max_load": {
    label: "Max Counsellor Lead Load",
    description: "Maximum number of leads a single counsellor can be assigned at once.",
    type: "number", unit: "leads", min: 1, max: 200, step: 1,
  },
  "admissions.offer_letter.validity_days": {
    label: "Offer Letter Validity",
    description: "Number of days an offer letter remains valid before it auto-expires.",
    type: "number", unit: "days", min: 1, max: 180, step: 1,
  },
  "finance.fee.overdue_grace_days": {
    label: "Fee Overdue Grace Period",
    description: "Days after fee deadline before the payment is considered overdue and triggers escalation.",
    type: "number", unit: "days", min: 0, max: 60, step: 1,
  },
  "academics.attendance.min_percentage": {
    label: "Min Attendance Percentage",
    description: "Minimum attendance % required. Students below this are flagged for academic review.",
    type: "number", unit: "%", min: 0, max: 100, step: 1,
  },
};

const CATEGORY_LABELS: Record<string, string> = {
  admissions: "Admissions & Eligibility",
  finance: "Finance & Fees",
  academics: "Academics",
  general: "General",
};

function PolicyTab() {
  const [policies, setPolicies] = useState<InstitutionPolicy[]>([]);
  const [drafts, setDrafts] = useState<Record<string, number | boolean | string>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [saved, setSaved] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setIsLoading(true);
    policiesApi.list()
      .then((res) => {
        setPolicies(res.policies);
        const initial: Record<string, number | boolean | string> = {};
        res.policies.forEach((p) => { initial[p.key] = p.value; });
        setDrafts(initial);
        setIsLoading(false);
      })
      .catch((e) => { setError(e.message); setIsLoading(false); });
  }, []);

  const handleChange = (key: string, val: number | boolean | string) => {
    setDrafts((d) => ({ ...d, [key]: val }));
    setSaved((s) => ({ ...s, [key]: false }));
  };

  const handleSave = async (policy: InstitutionPolicy) => {
    setSaving((s) => ({ ...s, [policy.key]: true }));
    try {
      await policiesApi.upsert(policy.key, drafts[policy.key] ?? policy.value, policy.description, policy.category);
      setSaved((s) => ({ ...s, [policy.key]: true }));
      setPolicies((ps) => ps.map((p) => p.key === policy.key ? { ...p, value: drafts[p.key] ?? p.value } : p));
      setTimeout(() => setSaved((s) => ({ ...s, [policy.key]: false })), 2000);
    } catch {
      // keep dirty state
    } finally {
      setSaving((s) => ({ ...s, [policy.key]: false }));
    }
  };

  const handleReset = (policy: InstitutionPolicy) => {
    setDrafts((d) => ({ ...d, [policy.key]: policy.value }));
    setSaved((s) => ({ ...s, [policy.key]: false }));
  };

  if (isLoading) return (
    <div className="space-y-3">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="skeleton-dark h-20 rounded-xl" />
      ))}
    </div>
  );

  if (error) return (
    <div className="flex items-center gap-2 p-4 rounded-xl" style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.15)", color: "#f87171" }}>
      <AlertTriangle className="w-4 h-4 flex-shrink-0" />
      <span className="text-[12px]">{error}</span>
    </div>
  );

  // Group by category
  const groups = policies.reduce<Record<string, InstitutionPolicy[]>>((acc, p) => {
    (acc[p.category] ??= []).push(p);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-3 p-4 rounded-xl" style={{ background: "rgba(129,140,248,0.06)", border: "1px solid rgba(129,140,248,0.12)" }}>
        <Info className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: "#818cf8" }} />
        <div>
          <p className="text-[12px] font-semibold" style={{ color: "#c7d2fe" }}>Institution Policy Engine</p>
          <p className="text-[11px] mt-0.5" style={{ color: "#64748b" }}>
            These thresholds drive the autonomous admissions pipeline. Changes take effect immediately — no code deployment needed.
            All edits are audit-logged with actor ID.
          </p>
        </div>
      </div>

      {Object.entries(groups).map(([category, catPolicies]) => (
        <div key={category}>
          {/* Category header */}
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold uppercase tracking-[0.14em]" style={{ color: "#818cf8" }}>
              {CATEGORY_LABELS[category] ?? category}
            </span>
            <div className="flex-1 h-px" style={{ background: "rgba(129,140,248,0.12)" }} />
          </div>

          <div className="space-y-2">
            {catPolicies.map((policy) => {
              const meta = POLICY_META[policy.key];
              const draft = drafts[policy.key] ?? policy.value;
              const isDirty = draft !== policy.value;
              const isSaving = saving[policy.key];
              const isSaved = saved[policy.key];

              return (
                <div
                  key={policy.key}
                  className="p-4 rounded-xl transition-all"
                  style={{
                    background: isDirty ? "rgba(129,140,248,0.06)" : "rgba(255,255,255,0.025)",
                    border: `1px solid ${isDirty ? "rgba(129,140,248,0.2)" : "rgba(255,255,255,0.06)"}`,
                  }}
                >
                  <div className="flex items-start justify-between gap-4">
                    {/* Left: label + description */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[12px] font-semibold" style={{ color: "#e2e8f0" }}>
                          {meta?.label ?? policy.key}
                        </span>
                        {isDirty && (
                          <span className="text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded"
                            style={{ background: "rgba(251,191,36,0.12)", color: "#fbbf24", border: "1px solid rgba(251,191,36,0.2)" }}>
                            unsaved
                          </span>
                        )}
                        {isSaved && (
                          <span className="text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded"
                            style={{ background: "rgba(34,197,94,0.12)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.2)" }}>
                            saved
                          </span>
                        )}
                      </div>
                      {meta?.description && (
                        <p className="text-[11px]" style={{ color: "#64748b" }}>{meta.description}</p>
                      )}
                      <p className="text-[10px] mt-1 font-mono" style={{ color: "#334155" }}>{policy.key}</p>
                    </div>

                    {/* Right: control */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {meta?.type === "boolean" ? (
                        <button
                          onClick={() => handleChange(policy.key, !draft)}
                          className="relative flex-shrink-0 transition-all"
                          style={{ width: 40, height: 22 }}
                        >
                          <div
                            className="absolute inset-0 rounded-full transition-all"
                            style={{
                              background: draft ? "rgba(129,140,248,0.4)" : "rgba(255,255,255,0.08)",
                              border: `1px solid ${draft ? "rgba(129,140,248,0.5)" : "rgba(255,255,255,0.1)"}`,
                            }}
                          />
                          <div
                            className="absolute top-[3px] transition-all rounded-full"
                            style={{
                              width: 16, height: 16,
                              background: draft ? "#818cf8" : "#475569",
                              left: draft ? 21 : 3,
                            }}
                          />
                        </button>
                      ) : (
                        <div className="flex items-center gap-2">
                          <input
                            type="number"
                            min={meta?.min}
                            max={meta?.max}
                            step={meta?.step ?? 1}
                            value={draft as number}
                            onChange={(e) => handleChange(policy.key, Number(e.target.value))}
                            className="text-[13px] font-semibold text-center rounded-lg px-2 py-1 w-20 transition-all"
                            style={{
                              background: "rgba(255,255,255,0.05)",
                              border: "1px solid rgba(255,255,255,0.1)",
                              color: "#e2e8f0",
                              outline: "none",
                            }}
                          />
                          {meta?.unit && (
                            <span className="text-[11px]" style={{ color: "#475569" }}>{meta.unit}</span>
                          )}
                        </div>
                      )}

                      {/* Action buttons */}
                      <button
                        onClick={() => handleSave(policy)}
                        disabled={!isDirty || isSaving}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-semibold transition-all"
                        style={{
                          background: isDirty ? "rgba(129,140,248,0.15)" : "transparent",
                          border: `1px solid ${isDirty ? "rgba(129,140,248,0.3)" : "rgba(255,255,255,0.05)"}`,
                          color: isDirty ? "#818cf8" : "#334155",
                          cursor: isDirty ? "pointer" : "default",
                        }}
                      >
                        {isSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                        Save
                      </button>
                      {isDirty && (
                        <button
                          onClick={() => handleReset(policy)}
                          className="p-1.5 rounded-lg transition-all"
                          style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)", color: "#475569" }}
                          title="Reset to saved value"
                        >
                          <RotateCcw className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Footer: last updated */}
                  <div className="flex items-center gap-2 mt-2 pt-2" style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}>
                    <span className="text-[10px]" style={{ color: "#334155" }}>
                      Last updated by <span style={{ color: "#475569" }}>{policy.updated_by}</span>
                      {policy.updated_at && (
                        <> · {formatDate(policy.updated_at)}</>
                      )}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main export ──────────────────────────────────────────────

export default function AdmissionsPage() {
  const [activeTab, setActiveTab] = useState<TabId>("inbox");
  const reviewQueue = useReviewQueue();

  const inboxCount = MOCK_INBOX.length;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Page header */}
      <div className="flex-shrink-0 mb-5 px-1">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[9px] font-bold uppercase tracking-[0.18em] mb-1.5 flex items-center gap-2"
              style={{ color: "#818cf8" }}>
              <span className="module-tag">E04</span>
              Admissions Module
            </div>
            <h1 className="text-2xl font-bold leading-tight" style={{ fontFamily: "var(--font-family-sans)", color: "#e2e8f0", letterSpacing: "-0.02em" }}>
              Admissions & Intake
            </h1>
            <p className="text-[12px] mt-0.5" style={{ color: "#64748b" }}>
              Intake 2025–26 · AI-assisted pipeline
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button className="btn-ghost flex items-center gap-1.5">
              <Filter className="w-3.5 h-3.5" /> Filter
            </button>
            <button className="btn-primary-glow flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5" />
              New Lead
            </button>
          </div>
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto pr-1">
        {/* Analytics bar */}
        <AnalyticsBar />

        {/* Tab navigation */}
        <TabNav active={activeTab} onChange={setActiveTab} />

        {/* Tab content */}
        {activeTab === "inbox" && (
          <div>
            <div className="section-header">
              <Clock className="w-3 h-3" style={{ color: "#475569" }} />
              Review Inbox
              <span className="ml-1 px-1.5 py-0.5 rounded text-[9px] font-bold"
                style={{ background: "rgba(251,113,133,0.15)", color: "#fb7185", border: "1px solid rgba(251,113,133,0.2)" }}>
                {inboxCount}
              </span>
            </div>
            {MOCK_INBOX.map((item) => (
              <InboxCard key={item.id} item={item} />
            ))}
            {reviewQueue.data?.map((item) => (
              <InboxCard
                key={item.id}
                item={{
                  id: item.id,
                  type: "exception",
                  title: item.applicant_name,
                  subtitle: item.reason,
                  priority: item.severity === "critical" || item.severity === "high" ? "high" : "medium",
                  age: item.created_at ? formatDate(item.created_at) : "—",
                  actions: [{ label: "Review", variant: "review" }],
                }}
              />
            ))}
            <FutureItemsSection />
          </div>
        )}

        {activeTab === "leads" && <LeadsTab />}
        {activeTab === "applications" && <ApplicationsTab />}
        {activeTab === "documents" && <DocumentsTab />}
        {activeTab === "tests" && <TestsTab />}
        {activeTab === "merit" && <MeritTab />}
        {activeTab === "offers" && <OffersTab />}
        {activeTab === "enrollment" && <EnrollmentTab />}
        {activeTab === "settings" && <PolicyTab />}
      </div>
    </div>
  );
}
