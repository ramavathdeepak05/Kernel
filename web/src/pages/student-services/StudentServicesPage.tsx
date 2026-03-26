import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Users, BookOpen, Bus, Home, AlertCircle,
  CheckCircle2, Clock, ChevronRight, TrendingUp,
} from "lucide-react";

// ── Design tokens (ALIS OS spec) ──────────────────────────────
const TEAL = "#1D9E75";
const TEAL_BG = "rgba(29,158,117,0.08)";
const TEAL_BORDER = "rgba(29,158,117,0.2)";

const BORDER = "0.5px solid rgba(51,65,85,0.5)";
const PANEL_BG = "rgba(15,23,42,0.6)";
const ROW_BG = "rgba(30,41,59,0.5)";

// Badge color semantics per ALIS spec
const BADGE: Record<string, { bg: string; color: string }> = {
  green:  { bg: "#EAF3DE", color: "#3B6D11" },
  amber:  { bg: "#FAEEDA", color: "#854F0B" },
  red:    { bg: "#FCEBEB", color: "#A32D2D" },
  blue:   { bg: "#E6F1FB", color: "#185FA5" },
  gray:   { bg: "rgba(51,65,85,0.3)", color: "#94a3b8" },
};

function Badge({ variant, children }: { variant: keyof typeof BADGE; children: React.ReactNode }) {
  const s = BADGE[variant];
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 7px",
      borderRadius: 20,
      fontSize: 10,
      fontWeight: 500,
      background: s.bg,
      color: s.color,
    }}>
      {children}
    </span>
  );
}

// ── API helpers ───────────────────────────────────────────────

const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

async function apiFetch<T>(endpoint: string): Promise<T> {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API}${endpoint}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

// ── Types ─────────────────────────────────────────────────────

interface HostelOccupancy {
  total_rooms: number;
  occupied: number;
  available: number;
  maintenance: number;
  occupancy_pct: number;
}

interface LibrarySummary {
  total_books: number;
  available: number;
  borrowed: number;
  overdue: number;
  borrowings_today: number;
}

interface OverdueBook {
  id: string;
  borrower_name: string;
  title: string;
  author: string;
  due_date: string;
  days_overdue: number;
}

interface TransportRoute {
  id: string;
  route_name: string;
  start_point: string;
  end_point: string;
  capacity: number;
  enrolled: number;
  is_active: boolean;
}

// ── Hooks ─────────────────────────────────────────────────────

function useHostelOccupancy() {
  return useQuery({
    queryKey: ["ss", "hostel", "occupancy"],
    queryFn: () => apiFetch<HostelOccupancy>("/students/hostel/occupancy"),
    staleTime: 60_000,
    retry: 1,
  });
}

function useLibrarySummary() {
  return useQuery({
    queryKey: ["ss", "library", "summary"],
    queryFn: () => apiFetch<LibrarySummary>("/students/library/summary"),
    staleTime: 60_000,
    retry: 1,
  });
}

function useOverdueBooks() {
  return useQuery({
    queryKey: ["ss", "library", "overdue"],
    queryFn: () => apiFetch<{ overdue_books: OverdueBook[]; total: number }>("/students/library/overdue"),
    staleTime: 30_000,
    retry: 1,
  });
}

function useTransportRoutes() {
  return useQuery({
    queryKey: ["ss", "transport", "routes"],
    queryFn: () => apiFetch<{ routes: TransportRoute[]; total: number }>("/students/transport/routes"),
    staleTime: 60_000,
    retry: 1,
  });
}

// ── Overview Tab ──────────────────────────────────────────────

function OverviewTab() {
  const { data: hostel } = useHostelOccupancy();
  const { data: library } = useLibrarySummary();
  const { data: transport } = useTransportRoutes();
  const { data: overdue } = useOverdueBooks();

  const routes = transport?.routes ?? [];
  const activeRoutes = routes.filter((r) => r.is_active).length;

  const stats = [
    {
      label: "Hostel occupancy",
      value: hostel ? `${hostel.occupancy_pct?.toFixed(0) ?? 0}%` : "—",
      delta: hostel ? `${hostel.occupied} of ${hostel.total_rooms} rooms` : "",
      deltaColor: TEAL,
    },
    {
      label: "Library books",
      value: library?.total_books ?? "—",
      delta: `${library?.available ?? 0} available`,
      deltaColor: TEAL,
    },
    {
      label: "Overdue returns",
      value: overdue?.total ?? "—",
      delta: overdue?.total ? "Reminder pending" : "All clear",
      deltaColor: (overdue?.total ?? 0) > 0 ? "#EF9F27" : TEAL,
    },
    {
      label: "Bus routes",
      value: activeRoutes || "—",
      delta: `${routes.length} total`,
      deltaColor: "#64748b",
    },
  ];

  return (
    <div className="space-y-5">
      {/* 4-up stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 8 }}>
        {stats.map((s) => (
          <div key={s.label} style={{ background: PANEL_BG, borderRadius: 8, padding: "10px 12px", border: BORDER }}>
            <p style={{ fontSize: 11, color: "#64748b", marginBottom: 4 }}>{s.label}</p>
            <p style={{ fontSize: 20, fontWeight: 500, color: "#e2e8f0" }}>{s.value}</p>
            <p style={{ fontSize: 11, color: s.deltaColor, marginTop: 2 }}>{s.delta}</p>
          </div>
        ))}
      </div>

      {/* Service domains */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12 }}>
        {[
          { icon: <Home className="w-4 h-4" />, title: "Hostel", desc: "Room allocation, complaints, occupancy tracking", color: "#818cf8", items: ["Block management", "Room allocation", "Complaint tracker", "Warden portal"] },
          { icon: <BookOpen className="w-4 h-4" />, title: "Library", desc: "Book catalogue, borrowing, overdue management", color: TEAL, items: ["Book catalogue", "Issue / return", "Overdue reminders", "Search & reserve"] },
          { icon: <Bus className="w-4 h-4" />, title: "Transport", desc: "Bus routes, passes, student assignments", color: "#fbbf24", items: ["Route management", "Bus passes", "GPS tracking stub", "Student assignments"] },
          { icon: <Users className="w-4 h-4" />, title: "Counselling", desc: "Student sessions, mental health referrals", color: "#fb7185", items: ["Session booking", "Counsellor allocation", "Referral tracking", "Confidential records"] },
        ].map((domain) => (
          <div key={domain.title} style={{ background: PANEL_BG, borderRadius: 12, padding: 16, border: BORDER }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <div style={{ width: 32, height: 32, borderRadius: 8, background: `${domain.color}15`, color: domain.color, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                {domain.icon}
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 500, color: "#e2e8f0" }}>{domain.title}</div>
                <div style={{ fontSize: 10, color: "#64748b" }}>{domain.desc}</div>
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {domain.items.map((item) => (
                <div key={item} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <ChevronRight style={{ width: 12, height: 12, flexShrink: 0, color: domain.color }} />
                  <span style={{ fontSize: 11, color: "#94a3b8" }}>{item}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* ALIS agent brief */}
      <div style={{ background: PANEL_BG, borderRadius: 12, padding: 16, border: BORDER }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <div style={{ width: 7, height: 7, borderRadius: "50%", background: TEAL, flexShrink: 0 }} />
          <span style={{ fontSize: 11, fontWeight: 500, color: "#64748b" }}>ALIS Agent — student services brief</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {[
            "Hostel allocation runs autonomously after enrollment is confirmed — no manual intervention required",
            "Library overdue reminders are sent via Communication Hub automatically on day 3, 7, and 14",
            "Transport pass requests are processed within 24h — fee deducted automatically from student ledger",
            "Counselling sessions are confidential — only aggregate risk data is shared with the Registrar",
          ].map((line, i) => (
            <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
              <ChevronRight style={{ width: 14, height: 14, marginTop: 1, flexShrink: 0, color: TEAL }} />
              <p style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.5 }}>{line}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Hostel Tab ────────────────────────────────────────────────

function HostelTab() {
  const { data: occupancy, isLoading } = useHostelOccupancy();

  const bars = occupancy ? [
    { label: "Occupied", value: occupancy.occupied, color: TEAL },
    { label: "Available", value: occupancy.available, color: "#34d399" },
    { label: "Maintenance", value: occupancy.maintenance, color: "#fbbf24" },
  ] : [];
  const total = occupancy?.total_rooms || 1;

  return (
    <div className="space-y-4">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 8 }}>
        {[
          { label: "Total rooms",   value: occupancy?.total_rooms  ?? "—", color: "#94a3b8" },
          { label: "Occupied",      value: occupancy?.occupied     ?? "—", color: TEAL },
          { label: "Available",     value: occupancy?.available    ?? "—", color: "#34d399" },
          { label: "Maintenance",   value: occupancy?.maintenance  ?? "—", color: "#fbbf24" },
        ].map((c) => (
          <div key={c.label} style={{ background: PANEL_BG, borderRadius: 8, padding: "10px 12px", border: BORDER }}>
            <p style={{ fontSize: 11, color: "#64748b", marginBottom: 4 }}>{c.label}</p>
            <p style={{ fontSize: 20, fontWeight: 500, color: c.color }}>
              {isLoading ? "—" : c.value}
            </p>
          </div>
        ))}
      </div>

      {/* Occupancy breakdown */}
      <div style={{ background: PANEL_BG, borderRadius: 12, padding: 16, border: BORDER }}>
        <p style={{ fontSize: 11, fontWeight: 500, color: "#64748b", marginBottom: 12 }}>Room status breakdown</p>
        {isLoading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[...Array(3)].map((_, i) => (
              <div key={i} style={{ height: 20, borderRadius: 4, background: "rgba(51,65,85,0.4)", animation: "pulse 1.5s ease-in-out infinite" }} />
            ))}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {bars.map((b) => {
              const pct = Math.round((b.value / total) * 100);
              return (
                <div key={b.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 11, fontWeight: 500, width: 80, color: "#94a3b8" }}>{b.label}</span>
                  <div style={{ flex: 1, height: 6, borderRadius: 3, background: "rgba(30,41,59,0.8)" }}>
                    <div style={{ width: `${pct}%`, height: "100%", borderRadius: 3, background: b.color, transition: "width 0.7s ease" }} />
                  </div>
                  <span style={{ fontSize: 11, width: 40, textAlign: "right", color: b.color }}>{b.value}</span>
                  <span style={{ fontSize: 10, width: 32, textAlign: "right", color: "#475569" }}>{pct}%</span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Hostel workflow */}
      <div style={{ background: PANEL_BG, borderRadius: 12, padding: 16, border: BORDER }}>
        <p style={{ fontSize: 11, fontWeight: 500, color: "#64748b", marginBottom: 12 }}>Hostel allocation workflow</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12 }}>
          {[
            { step: "1", title: "Application",    desc: "Student applies during enrollment", color: "#818cf8" },
            { step: "2", title: "Block preference",desc: "Preferences captured per gender/program", color: "#38bdf8" },
            { step: "3", title: "Room allocation", desc: "Auto-assigned from available pool", color: TEAL },
            { step: "4", title: "Fee deduction",   desc: "Hostel fee added to student ledger", color: "#34d399" },
          ].map((s) => (
            <div key={s.step} style={{ padding: 12, borderRadius: 8, background: `${s.color}08`, border: `0.5px solid ${s.color}20` }}>
              <div style={{ width: 24, height: 24, borderRadius: "50%", background: `${s.color}18`, color: s.color, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 500, marginBottom: 8 }}>
                {s.step}
              </div>
              <div style={{ fontSize: 12, fontWeight: 500, color: "#e2e8f0", marginBottom: 4 }}>{s.title}</div>
              <div style={{ fontSize: 10, color: "#64748b" }}>{s.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Library Tab ────────────────────────────────────────────────

function LibraryTab() {
  const { data: summary, isLoading } = useLibrarySummary();
  const { data: overdueData } = useOverdueBooks();
  const overdue = overdueData?.overdue_books ?? [];

  return (
    <div className="space-y-4">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 8 }}>
        {[
          { label: "Total books",      value: summary?.total_books      ?? "—", color: "#e2e8f0" },
          { label: "Available",        value: summary?.available        ?? "—", color: "#34d399" },
          { label: "Borrowed",         value: summary?.borrowed         ?? "—", color: TEAL },
          { label: "Overdue",          value: summary?.overdue          ?? "—", color: (summary?.overdue ?? 0) > 0 ? "#EF9F27" : "#34d399" },
        ].map((c) => (
          <div key={c.label} style={{ background: PANEL_BG, borderRadius: 8, padding: "10px 12px", border: BORDER }}>
            <p style={{ fontSize: 11, color: "#64748b", marginBottom: 4 }}>{c.label}</p>
            <p style={{ fontSize: 20, fontWeight: 500, color: c.color }}>
              {isLoading ? "—" : c.value}
            </p>
          </div>
        ))}
      </div>

      {/* Overdue queue */}
      <div style={{ background: PANEL_BG, borderRadius: 12, border: BORDER, overflow: "hidden" }}>
        <div style={{ padding: "10px 16px", borderBottom: BORDER, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <p style={{ fontSize: 11, fontWeight: 500, color: "#64748b" }}>Overdue returns</p>
          {overdueData?.total ? (
            <Badge variant="amber">{overdueData.total} overdue</Badge>
          ) : (
            <Badge variant="green">All clear</Badge>
          )}
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "rgba(15,23,42,0.8)" }}>
              {["Borrower", "Book title", "Author", "Due date", "Days overdue"].map((h) => (
                <th key={h} style={{ padding: "8px 16px", textAlign: "left", fontSize: 10, fontWeight: 500, color: "#475569", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {overdue.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ padding: 32, textAlign: "center", fontSize: 12, color: "#475569" }}>
                  No overdue returns
                </td>
              </tr>
            ) : overdue.map((b, i) => (
              <tr key={b.id}
                style={{ borderTop: BORDER }}
                onMouseEnter={(e) => (e.currentTarget.style.background = ROW_BG)}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                <td style={{ padding: "9px 16px", fontSize: 12, color: "#e2e8f0" }}>{b.borrower_name}</td>
                <td style={{ padding: "9px 16px", fontSize: 12, color: "#94a3b8" }}>{b.title}</td>
                <td style={{ padding: "9px 16px", fontSize: 11, color: "#64748b" }}>{b.author}</td>
                <td style={{ padding: "9px 16px", fontSize: 11, color: "#64748b" }}>{b.due_date}</td>
                <td style={{ padding: "9px 16px" }}>
                  <Badge variant={b.days_overdue > 14 ? "red" : b.days_overdue > 7 ? "amber" : "blue"}>
                    {b.days_overdue}d
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Transport Tab ──────────────────────────────────────────────

function TransportTab() {
  const { data, isLoading } = useTransportRoutes();
  const routes = data?.routes ?? [];

  return (
    <div className="space-y-4">
      <div style={{ background: PANEL_BG, borderRadius: 12, border: BORDER, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "rgba(15,23,42,0.8)" }}>
              {["Route name", "From", "To", "Capacity", "Enrolled", "Utilization", "Status"].map((h) => (
                <th key={h} style={{ padding: "8px 16px", textAlign: "left", fontSize: 10, fontWeight: 500, color: "#475569", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? [...Array(4)].map((_, i) => (
              <tr key={i} style={{ borderTop: BORDER }}>
                {[...Array(7)].map((_, j) => (
                  <td key={j} style={{ padding: "9px 16px" }}>
                    <div style={{ height: 14, borderRadius: 3, background: "rgba(51,65,85,0.4)", width: "70%", animation: "pulse 1.5s ease-in-out infinite" }} />
                  </td>
                ))}
              </tr>
            )) : routes.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: 32, textAlign: "center", fontSize: 12, color: "#475569" }}>
                  No transport routes configured
                </td>
              </tr>
            ) : routes.map((r) => {
              const utilPct = r.capacity > 0 ? Math.round((r.enrolled / r.capacity) * 100) : 0;
              return (
                <tr key={r.id} style={{ borderTop: BORDER }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = ROW_BG)}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                  <td style={{ padding: "9px 16px", fontSize: 12, fontWeight: 500, color: "#e2e8f0" }}>{r.route_name}</td>
                  <td style={{ padding: "9px 16px", fontSize: 11, color: "#94a3b8" }}>{r.start_point}</td>
                  <td style={{ padding: "9px 16px", fontSize: 11, color: "#94a3b8" }}>{r.end_point}</td>
                  <td style={{ padding: "9px 16px", fontSize: 12, color: "#94a3b8" }}>{r.capacity}</td>
                  <td style={{ padding: "9px 16px", fontSize: 12, color: "#e2e8f0" }}>{r.enrolled}</td>
                  <td style={{ padding: "9px 16px" }}>
                    <div>
                      <div style={{ width: 50, height: 4, borderRadius: 2, background: "rgba(30,41,59,0.8)", overflow: "hidden" }}>
                        <div style={{ width: `${utilPct}%`, height: "100%", borderRadius: 2, background: utilPct > 85 ? "#E24B4A" : utilPct > 65 ? "#EF9F27" : TEAL, transition: "width 0.3s" }} />
                      </div>
                      <p style={{ fontSize: 10, color: "#64748b", marginTop: 2 }}>{utilPct}%</p>
                    </div>
                  </td>
                  <td style={{ padding: "9px 16px" }}>
                    <Badge variant={r.is_active ? "green" : "gray"}>
                      {r.is_active ? "Active" : "Inactive"}
                    </Badge>
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

// ── Grievances Tab ────────────────────────────────────────────

interface Grievance {
  id: string;
  subject: string;
  category: string;
  status: string;
  created_at: string;
  description: string;
}

function GrievancesTab() {
  const { data: grievanceData, isLoading, refetch } = useQuery({
    queryKey: ["ss", "grievances"],
    queryFn: () => apiFetch<{ grievances: Grievance[]; total: number }>("/student-services/grievances"),
    staleTime: 30_000,
    retry: 1,
  });
  const grievances = grievanceData?.grievances ?? [];

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ subject: "", category: "ACADEMIC", description: "" });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [success, setSuccess] = useState(false);

  const submit = async (e: { preventDefault: () => void }) => {
    e.preventDefault();
    setSaving(true);
    setErr("");
    try {
      const token = localStorage.getItem("token");
      const r = await fetch(`${API}/student-services/grievances`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify(form),
      });
      if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || "Failed"); }
      setSuccess(true);
      setForm({ subject: "", category: "ACADEMIC", description: "" });
      setShowForm(false);
      refetch();
    } catch (ex: unknown) { setErr(ex instanceof Error ? ex.message : "Failed to submit"); }
    finally { setSaving(false); }
  };

  const inp: React.CSSProperties = {
    width: "100%", padding: "8px 12px", borderRadius: 8,
    background: "rgba(255,255,255,0.04)", border: BORDER,
    color: "#e2e8f0", fontSize: 13, outline: "none", boxSizing: "border-box",
  };

  const CATEGORY_COLORS: Record<string, string> = {
    ACADEMIC: "#818cf8", FINANCIAL: "#fbbf24", HOSTEL: "#f97316",
    LIBRARY: TEAL, TRANSPORT: "#38bdf8", OTHER: "#94a3b8",
  };
  const STATUS_COLORS: Record<string, { bg: string; color: string }> = {
    OPEN:        { bg: "rgba(251,191,36,0.1)",  color: "#fbbf24" },
    IN_PROGRESS: { bg: "rgba(56,189,248,0.1)",  color: "#38bdf8" },
    RESOLVED:    { bg: "rgba(52,211,153,0.1)",  color: "#34d399" },
    CLOSED:      { bg: "rgba(100,116,139,0.1)", color: "#64748b" },
  };

  return (
    <div className="space-y-4">
      {/* Submit form */}
      {showForm ? (
        <div style={{ background: PANEL_BG, borderRadius: 12, border: BORDER, padding: 20 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0" }}>Submit Grievance</span>
            <button onClick={() => setShowForm(false)} style={{ background: "none", border: "none", color: "#64748b", cursor: "pointer", fontSize: 18, lineHeight: 1 }}>✕</button>
          </div>
          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 160px", gap: 12 }}>
              <div>
                <label style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", display: "block", marginBottom: 6 }}>Subject</label>
                <input required value={form.subject} onChange={(e) => setForm((f) => ({ ...f, subject: e.target.value }))} style={inp} placeholder="Brief summary of the issue" />
              </div>
              <div>
                <label style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", display: "block", marginBottom: 6 }}>Category</label>
                <select value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))} style={{ ...inp, cursor: "pointer" }}>
                  {["ACADEMIC", "FINANCIAL", "HOSTEL", "LIBRARY", "TRANSPORT", "OTHER"].map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", display: "block", marginBottom: 6 }}>Description</label>
              <textarea required rows={4} value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} style={{ ...inp, resize: "vertical" }} placeholder="Describe the issue in detail…" />
            </div>
            {err && <div style={{ padding: "8px 12px", borderRadius: 8, background: "rgba(251,113,133,0.08)", border: "1px solid rgba(251,113,133,0.2)", color: "#fb7185", fontSize: 12 }}>{err}</div>}
            <div style={{ display: "flex", gap: 10 }}>
              <button type="button" onClick={() => setShowForm(false)} style={{ padding: "8px 18px", borderRadius: 8, background: "transparent", border: BORDER, color: "#94a3b8", fontSize: 12, cursor: "pointer" }}>Cancel</button>
              <button type="submit" disabled={saving} style={{ padding: "8px 18px", borderRadius: 8, background: TEAL_BG, border: `0.5px solid ${TEAL_BORDER}`, color: TEAL, fontSize: 12, fontWeight: 600, cursor: saving ? "not-allowed" : "pointer" }}>
                {saving ? "Submitting…" : "Submit Grievance"}
              </button>
            </div>
          </form>
        </div>
      ) : (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 14px", borderRadius: 8, background: "rgba(251,113,133,0.06)", border: "0.5px solid rgba(251,113,133,0.2)" }}>
            <AlertCircle style={{ width: 14, height: 14, color: "#fb7185" }} />
            <span style={{ fontSize: 12, color: "#fb7185" }}>{isLoading ? "…" : `${grievanceData?.total ?? 0}`} grievances</span>
          </div>
          {success && <span style={{ fontSize: 11, color: TEAL }}>✓ Grievance submitted</span>}
          <button onClick={() => { setShowForm(true); setSuccess(false); }} style={{ padding: "6px 14px", borderRadius: 8, background: TEAL_BG, border: `0.5px solid ${TEAL_BORDER}`, color: TEAL, fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
            + New Grievance
          </button>
        </div>
      )}

      {/* Grievances list */}
      <div style={{ background: PANEL_BG, borderRadius: 12, border: BORDER, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "rgba(15,23,42,0.8)" }}>
              {["Subject", "Category", "Submitted", "Status"].map((h) => (
                <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "#475569" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              [...Array(3)].map((_, i) => (
                <tr key={i} style={{ borderTop: BORDER }}>
                  {[...Array(4)].map((_, j) => (
                    <td key={j} style={{ padding: "10px 16px" }}>
                      <div style={{ height: 14, borderRadius: 4, background: "rgba(51,65,85,0.4)", width: "75%", animation: "pulse 1.5s ease-in-out infinite" }} />
                    </td>
                  ))}
                </tr>
              ))
            ) : grievances.length === 0 ? (
              <tr>
                <td colSpan={4} style={{ padding: 32, textAlign: "center", fontSize: 12, color: "#475569" }}>
                  <CheckCircle2 style={{ width: 24, height: 24, margin: "0 auto 8px", color: TEAL, opacity: 0.5 }} />
                  No grievances on record
                </td>
              </tr>
            ) : grievances.map((g) => {
              const sc = STATUS_COLORS[g.status] ?? STATUS_COLORS.OPEN;
              const catColor = CATEGORY_COLORS[g.category] ?? "#94a3b8";
              return (
                <tr key={g.id} style={{ borderTop: BORDER }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = ROW_BG)}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                  <td style={{ padding: "10px 16px", fontSize: 12, color: "#e2e8f0", maxWidth: 260 }}>
                    <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{g.subject}</div>
                  </td>
                  <td style={{ padding: "10px 16px" }}>
                    <span style={{ padding: "2px 8px", borderRadius: 20, fontSize: 10, fontWeight: 500, background: `${catColor}15`, color: catColor }}>{g.category}</span>
                  </td>
                  <td style={{ padding: "10px 16px", fontSize: 11, color: "#64748b" }}>{g.created_at?.split("T")[0]}</td>
                  <td style={{ padding: "10px 16px" }}>
                    <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: 10, fontWeight: 600, background: sc.bg, color: sc.color }}>{g.status}</span>
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

// ── Main Page ─────────────────────────────────────────────────

type TabId = "overview" | "hostel" | "library" | "transport" | "grievances";

const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: "overview",    label: "Overview",    icon: <TrendingUp className="w-3.5 h-3.5" /> },
  { id: "hostel",      label: "Hostel",      icon: <Home className="w-3.5 h-3.5" /> },
  { id: "library",     label: "Library",     icon: <BookOpen className="w-3.5 h-3.5" /> },
  { id: "transport",   label: "Transport",   icon: <Bus className="w-3.5 h-3.5" /> },
  { id: "grievances",  label: "Grievances",  icon: <AlertCircle className="w-3.5 h-3.5" /> },
];

export default function StudentServicesPage() {
  const [tab, setTab] = useState<TabId>("overview");

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Header */}
      <div style={{ flexShrink: 0, padding: "20px 24px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: TEAL_BG, border: `0.5px solid ${TEAL_BORDER}`, display: "flex", alignItems: "center", justifyContent: "center", color: TEAL }}>
              <Users className="w-4 h-4" />
            </div>
            <div>
              <h1 style={{ fontSize: 18, fontWeight: 500, color: "#e2e8f0", lineHeight: 1 }}>Student services</h1>
              <p style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>E09 · Hostel · Library · Transport · Counselling</p>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 8, background: TEAL_BG, border: `0.5px solid ${TEAL_BORDER}`, fontSize: 11, color: TEAL }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: TEAL }} />
            Backend active
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 4, marginTop: 16 }}>
          {tabs.map((t) => (
            <button key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "6px 12px", borderRadius: 8,
                fontSize: 11, fontWeight: 500, cursor: "pointer",
                background: tab === t.id ? TEAL_BG : "transparent",
                color: tab === t.id ? TEAL : "#64748b",
                border: `0.5px solid ${tab === t.id ? TEAL_BORDER : "transparent"}`,
                transition: "all 0.12s",
              }}>
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 24px 24px" }}>
        {tab === "overview"   && <OverviewTab />}
        {tab === "hostel"     && <HostelTab />}
        {tab === "library"    && <LibraryTab />}
        {tab === "transport"  && <TransportTab />}
        {tab === "grievances" && <GrievancesTab />}
      </div>
    </div>
  );
}
