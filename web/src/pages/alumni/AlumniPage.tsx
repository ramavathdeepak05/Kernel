import { useState } from "react";
import {
  GraduationCap, Briefcase, Users, TrendingUp,
  CheckCircle2, Building2, Star, Calendar,
} from "lucide-react";
import { ALISTabs, ALISTabsList, ALISTabsTrigger, ALISTabsContent } from "@/components/ui/alis-tabs";
import {
  useAlumniStats, useAlumniProfiles, usePlacementStats,
  usePlacements, useJobBoard, useRecruitmentDrives, useMentors,
} from "@/hooks/use-alumni";
import type { AlumniProfile, PlacementRecord, JobPosting, RecruitmentDrive } from "@/services/alumni";

// ── Constants ──────────────────────────────────────────────────

type TabId = "overview" | "placements" | "jobs" | "drives" | "alumni";

const TEAL        = "#1D9E75";
const TEAL_BG     = "rgba(29,158,117,0.08)";
const TEAL_BORDER = "rgba(29,158,117,0.2)";

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: "overview",   label: "Overview",   icon: <TrendingUp className="w-3.5 h-3.5" /> },
  { id: "placements", label: "Placements", icon: <Briefcase className="w-3.5 h-3.5" /> },
  { id: "jobs",       label: "Job board",  icon: <Building2 className="w-3.5 h-3.5" /> },
  { id: "drives",     label: "Drives",     icon: <Calendar className="w-3.5 h-3.5" /> },
  { id: "alumni",     label: "Alumni DB",  icon: <Users className="w-3.5 h-3.5" /> },
];

const OFFER_TYPE_BADGE: Record<string, { bg: string; color: string }> = {
  CAMPUS:         { bg: TEAL_BG, color: TEAL },
  OFF_CAMPUS:     { bg: "#E6F1FB", color: "#185FA5" },
  LATERAL:        { bg: "#FAEEDA", color: "#854F0B" },
  HIGHER_STUDIES: { bg: "#EAF3DE", color: "#3B6D11" },
};

const STATUS_BADGE: Record<string, { bg: string; color: string }> = {
  OFFERED:    { bg: "#E6F1FB", color: "#185FA5" },
  ACCEPTED:   { bg: TEAL_BG, color: TEAL },
  JOINED:     { bg: "#EAF3DE", color: "#3B6D11" },
  DECLINED:   { bg: "#FCEBEB", color: "#A32D2D" },
  RESCINDED:  { bg: "#FCEBEB", color: "#A32D2D" },
  OPEN:       { bg: "#EAF3DE", color: "#3B6D11" },
  CLOSED:     { bg: "rgba(100,116,139,0.1)", color: "#64748b" },
  DRAFT:      { bg: "rgba(100,116,139,0.1)", color: "#64748b" },
  ANNOUNCED:          { bg: "#E6F1FB", color: "#185FA5" },
  REGISTRATION_OPEN:  { bg: TEAL_BG, color: TEAL },
  IN_PROGRESS:        { bg: "#FAEEDA", color: "#854F0B" },
  COMPLETED:          { bg: "#EAF3DE", color: "#3B6D11" },
  CANCELLED:          { bg: "#FCEBEB", color: "#A32D2D" },
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

const fmtLPA = (n?: number) => n != null ? `₹${n.toFixed(1)} LPA` : "—";
const DEPT_COLORS = ["#1D9E75", "#818cf8", "#fbbf24", "#fb7185", "#38bdf8", "#a78bfa", "#f97316"];

// ── Overview tab ───────────────────────────────────────────────

function OverviewTab() {
  const { data: stats } = useAlumniStats();
  const { data: placement } = usePlacementStats();
  const { data: drives } = useRecruitmentDrives();
  const { data: mentors } = useMentors();

  const kpis = [
    { label: "Alumni registered", value: stats?.total_alumni ?? "—",    sub: `${stats?.verified ?? 0} verified`, color: TEAL,     bg: TEAL_BG,                       border: TEAL_BORDER,                   icon: <GraduationCap className="w-5 h-5" /> },
    { label: "Placed this year",  value: stats?.placements_ytd ?? "—",  sub: `${placement?.placement_pct?.toFixed(1) ?? "—"}% placement`, color: "#34d399", bg: "rgba(52,211,153,0.08)", border: "rgba(52,211,153,0.2)", icon: <Briefcase className="w-5 h-5" /> },
    { label: "Avg package",       value: fmtLPA(placement?.avg_package_lpa), sub: `Highest: ${fmtLPA(placement?.highest_package_lpa)}`, color: "#fbbf24", bg: "rgba(251,191,36,0.08)", border: "rgba(251,191,36,0.2)", icon: <TrendingUp className="w-5 h-5" /> },
    { label: "Active mentors",    value: stats?.active_mentors ?? "—",  sub: "alumni mentoring students", color: "#818cf8", bg: "rgba(99,102,241,0.08)", border: "rgba(99,102,241,0.2)", icon: <Star className="w-5 h-5" /> },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* KPIs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 8 }}>
        {kpis.map(k => (
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

      {/* Program placement + top recruiters */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {/* Program placement */}
        <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
          <div style={{ padding: "9px 12px", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", background: "var(--color-background-secondary, #0f1c2e)" }}>
            <p style={{ fontSize: 11, fontWeight: 500 }}>Placement by program</p>
          </div>
          <div style={{ padding: "10px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
            {(placement?.by_program ?? []).map((p, idx) => {
              const pct = p.total > 0 ? Math.round((p.placed / p.total) * 100) : 0;
              const color = DEPT_COLORS[idx % DEPT_COLORS.length];
              return (
                <div key={p.program}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                    <span style={{ fontSize: 11, fontWeight: 500 }}>{p.program}</span>
                    <span style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)" }}>
                      {p.placed}/{p.total} · {fmtLPA(p.avg_lpa)}
                    </span>
                  </div>
                  <div style={{ height: 4, borderRadius: 2, background: "rgba(255,255,255,0.06)" }}>
                    <div style={{ width: `${pct}%`, height: "100%", borderRadius: 2, background: color }} />
                  </div>
                </div>
              );
            })}
            {!placement?.by_program?.length && (
              <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>No placement data</p>
            )}
          </div>
        </div>

        {/* Top recruiters */}
        <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
          <div style={{ padding: "9px 12px", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", background: "var(--color-background-secondary, #0f1c2e)" }}>
            <p style={{ fontSize: 11, fontWeight: 500 }}>Top recruiters</p>
          </div>
          {(placement?.top_recruiters ?? []).slice(0, 6).map((r, i, arr) => (
            <div key={r.company} style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "8px 12px",
              borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: 6, background: "rgba(255,255,255,0.04)",
                  border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 12, fontWeight: 500, color: TEAL,
                }}>
                  {r.company.charAt(0)}
                </div>
                <p style={{ fontSize: 12, fontWeight: 500 }}>{r.company}</p>
              </div>
              <div style={{ textAlign: "right" }}>
                <p style={{ fontSize: 12, fontWeight: 500 }}>{r.offers} offers</p>
                <p style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)" }}>{fmtLPA(r.avg_lpa)}</p>
              </div>
            </div>
          ))}
          {!placement?.top_recruiters?.length && (
            <div style={{ padding: "16px 12px", textAlign: "center", fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>No recruiter data</div>
          )}
        </div>
      </div>

      {/* Upcoming drives + mentors */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
          <div style={{ padding: "9px 12px", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", background: "var(--color-background-secondary, #0f1c2e)" }}>
            <p style={{ fontSize: 11, fontWeight: 500 }}>Upcoming drives</p>
          </div>
          {(drives ?? []).filter(d => d.status === "ANNOUNCED" || d.status === "REGISTRATION_OPEN").slice(0, 4).map((d, i, arr) => {
            const ss = STATUS_BADGE[d.status] ?? STATUS_BADGE.ANNOUNCED;
            return (
              <div key={d.id} style={{
                padding: "8px 12px",
                borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
                  <p style={{ fontSize: 12, fontWeight: 500 }}>{d.company}</p>
                  <Badge s={ss}>{d.status.replace("_", " ")}</Badge>
                </div>
                <p style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)" }}>
                  {new Date(d.drive_date).toLocaleDateString()} · {d.package_range}
                </p>
              </div>
            );
          })}
          {!drives?.filter(d => ["ANNOUNCED","REGISTRATION_OPEN"].includes(d.status)).length && (
            <div style={{ padding: "16px 12px", textAlign: "center", fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>No upcoming drives</div>
          )}
        </div>

        <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
          <div style={{ padding: "9px 12px", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", background: "var(--color-background-secondary, #0f1c2e)" }}>
            <p style={{ fontSize: 11, fontWeight: 500 }}>Alumni mentors</p>
          </div>
          {(mentors ?? []).slice(0, 4).map((m, i, arr) => (
            <div key={m.id} style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "8px 12px",
              borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
            }}>
              <div>
                <p style={{ fontSize: 12, fontWeight: 500 }}>{m.full_name}</p>
                <p style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)" }}>
                  {m.current_designation ?? "—"} at {m.current_employer ?? "—"} · {m.program} {m.batch_year}
                </p>
              </div>
              {m.is_verified && <CheckCircle2 className="w-3.5 h-3.5" style={{ color: TEAL }} />}
            </div>
          ))}
          {!mentors?.length && (
            <div style={{ padding: "16px 12px", textAlign: "center", fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>No mentors registered</div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Placements tab ─────────────────────────────────────────────

function PlacementsTab() {
  const { data: records, isLoading } = usePlacements();
  const cols = "1.5fr 1.5fr 1fr 1fr 80px 80px";

  return (
    <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
      <div style={{ display: "grid", gridTemplateColumns: cols, padding: "6px 12px", background: "var(--color-background-secondary, #0f1c2e)", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" }}>
        {["Student", "Company / Role", "Program", "Package", "Type", "Status"].map(h => (
          <span key={h} style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary, #64748b)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{h}</span>
        ))}
      </div>
      {isLoading && (
        <div style={{ padding: "20px 12px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>Loading…</div>
      )}
      {(records ?? []).map((r: PlacementRecord, i, arr) => {
        const ts = OFFER_TYPE_BADGE[r.offer_type] ?? OFFER_TYPE_BADGE.OFF_CAMPUS;
        const ss = STATUS_BADGE[r.status] ?? STATUS_BADGE.OFFERED;
        return (
          <div key={r.id} style={{
            display: "grid", gridTemplateColumns: cols, padding: "8px 12px", alignItems: "center",
            borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
          }}>
            <p style={{ fontSize: 12, fontWeight: 500 }}>{r.student_name}</p>
            <div>
              <p style={{ fontSize: 12, fontWeight: 500 }}>{r.company}</p>
              <p style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)", marginTop: 1 }}>{r.role}</p>
            </div>
            <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>{r.program}</p>
            <p style={{ fontSize: 12, fontWeight: 500, color: "#34d399" }}>{fmtLPA(r.package_lpa)}</p>
            <Badge s={ts}>{r.offer_type.replace("_", " ")}</Badge>
            <Badge s={ss}>{r.status}</Badge>
          </div>
        );
      })}
      {!isLoading && !records?.length && (
        <div style={{ padding: "20px 12px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>No placement records</div>
      )}
    </div>
  );
}

// ── Job board tab ──────────────────────────────────────────────

function JobBoardTab() {
  const { data: jobs, isLoading } = useJobBoard("OPEN");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <p style={{ fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>
          {jobs?.filter(j => j.status === "OPEN").length ?? 0} open positions
        </p>
      </div>
      {isLoading && (
        <div style={{ padding: "20px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>Loading…</div>
      )}
      {(jobs ?? []).map((j: JobPosting) => {
        const ss = STATUS_BADGE[j.status] ?? STATUS_BADGE.OPEN;
        const daysLeft = Math.ceil((new Date(j.deadline).getTime() - Date.now()) / 86400000);
        return (
          <div key={j.id} style={{
            border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))",
            borderRadius: 8, padding: "10px 12px",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
              <div>
                <p style={{ fontSize: 13, fontWeight: 500 }}>{j.title}</p>
                <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)", marginTop: 2 }}>
                  {j.company} · {j.location}
                </p>
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <Badge s={ss}>{j.status}</Badge>
                {daysLeft > 0 && daysLeft <= 7 && (
                  <span style={{ fontSize: 10, color: "#fb7185" }}>{daysLeft}d left</span>
                )}
              </div>
            </div>
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <span style={{ fontSize: 11, fontWeight: 500, color: "#34d399" }}>
                {j.min_package_lpa != null && j.max_package_lpa != null
                  ? `₹${j.min_package_lpa}–${j.max_package_lpa} LPA`
                  : j.min_package_lpa != null ? `₹${j.min_package_lpa}+ LPA` : "Package undisclosed"}
              </span>
              <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 4, background: "rgba(255,255,255,0.04)", color: "var(--color-text-secondary, #64748b)" }}>{j.type}</span>
              {j.experience_years != null && (
                <span style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)" }}>{j.experience_years}yr exp</span>
              )}
              <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--color-text-secondary, #64748b)" }}>{j.applications_count} applied</span>
            </div>
          </div>
        );
      })}
      {!isLoading && !jobs?.length && (
        <div style={{ padding: "24px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)", border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8 }}>
          No open positions
        </div>
      )}
    </div>
  );
}

// ── Drives tab ─────────────────────────────────────────────────

function DrivesTab() {
  const { data: drives, isLoading } = useRecruitmentDrives();
  const cols = "1.5fr 1fr 1fr 60px 60px 60px 90px";

  return (
    <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
      <div style={{ display: "grid", gridTemplateColumns: cols, padding: "6px 12px", background: "var(--color-background-secondary, #0f1c2e)", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" }}>
        {["Company", "Date", "Package range", "Reg.", "Short.", "Sel.", "Status"].map(h => (
          <span key={h} style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary, #64748b)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{h}</span>
        ))}
      </div>
      {isLoading && (
        <div style={{ padding: "20px 12px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>Loading…</div>
      )}
      {(drives ?? []).map((d: RecruitmentDrive, i, arr) => {
        const ss = STATUS_BADGE[d.status] ?? STATUS_BADGE.ANNOUNCED;
        return (
          <div key={d.id} style={{
            display: "grid", gridTemplateColumns: cols, padding: "8px 12px", alignItems: "center",
            borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
          }}>
            <div>
              <p style={{ fontSize: 12, fontWeight: 500 }}>{d.company}</p>
              <p style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)", marginTop: 1 }}>{d.venue}</p>
            </div>
            <p style={{ fontSize: 11 }}>{new Date(d.drive_date).toLocaleDateString()}</p>
            <p style={{ fontSize: 11, fontWeight: 500, color: "#34d399" }}>{d.package_range}</p>
            <p style={{ fontSize: 12 }}>{d.registered_count}</p>
            <p style={{ fontSize: 12 }}>{d.shortlisted_count}</p>
            <p style={{ fontSize: 12, fontWeight: 500, color: d.selected_count > 0 ? TEAL : "var(--color-text-primary, #e2e8f0)" }}>{d.selected_count}</p>
            <Badge s={ss}>{d.status.replace("_", " ")}</Badge>
          </div>
        );
      })}
      {!isLoading && !drives?.length && (
        <div style={{ padding: "20px 12px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>No drives scheduled</div>
      )}
    </div>
  );
}

// ── Alumni DB tab ──────────────────────────────────────────────

function AlumniDBTab() {
  const { data: profiles, isLoading } = useAlumniProfiles();
  const cols = "2fr 1fr 1.5fr 1fr 60px 60px";

  return (
    <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
      <div style={{ display: "grid", gridTemplateColumns: cols, padding: "6px 12px", background: "var(--color-background-secondary, #0f1c2e)", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" }}>
        {["Name", "Batch", "Current role", "Location", "Verified", "Mentor"].map(h => (
          <span key={h} style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary, #64748b)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{h}</span>
        ))}
      </div>
      {isLoading && (
        <div style={{ padding: "20px 12px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>Loading…</div>
      )}
      {(profiles ?? []).map((a: AlumniProfile, i, arr) => (
        <div key={a.id} style={{
          display: "grid", gridTemplateColumns: cols, padding: "8px 12px", alignItems: "center",
          borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
        }}>
          <div>
            <p style={{ fontSize: 12, fontWeight: 500 }}>{a.full_name}</p>
            <p style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)", marginTop: 1 }}>{a.program}</p>
          </div>
          <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>{a.batch_year}</p>
          <div>
            {a.current_designation && <p style={{ fontSize: 11, fontWeight: 500 }}>{a.current_designation}</p>}
            {a.current_employer && <p style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)", marginTop: 1 }}>{a.current_employer}</p>}
            {!a.current_designation && !a.current_employer && <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>—</p>}
          </div>
          <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>{a.location ?? "—"}</p>
          <span style={{ fontSize: 12, color: a.is_verified ? TEAL : "rgba(100,116,139,0.5)" }}>
            {a.is_verified ? "✓" : "—"}
          </span>
          <span style={{ fontSize: 12, color: a.is_mentor ? "#818cf8" : "rgba(100,116,139,0.5)" }}>
            {a.is_mentor ? <Star className="w-3.5 h-3.5" /> : "—"}
          </span>
        </div>
      ))}
      {!isLoading && !profiles?.length && (
        <div style={{ padding: "20px 12px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>No alumni profiles yet</div>
      )}
    </div>
  );
}

// ── Page root ──────────────────────────────────────────────────

export default function AlumniPage() {
  const [tab, setTab] = useState<TabId>("overview");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ fontSize: 16, fontWeight: 500 }}>Alumni & placement</h1>
          <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)", marginTop: 2 }}>
            Alumni database · Placement records · Job board · Recruitment drives · Mentors
          </p>
        </div>
        <span style={{ fontSize: 10, fontWeight: 500, padding: "3px 8px", borderRadius: 20, background: TEAL_BG, color: TEAL, border: `0.5px solid ${TEAL_BORDER}` }}>
          E12
        </span>
      </div>

      {/* Tabs */}
      <ALISTabs defaultValue="overview">
        <ALISTabsList>
          {TABS.map(t => (
            <ALISTabsTrigger key={t.id} value={t.id}>
              <span className="flex items-center gap-1.5">{t.icon} {t.label}</span>
            </ALISTabsTrigger>
          ))}
        </ALISTabsList>
        <ALISTabsContent value="overview"><OverviewTab /></ALISTabsContent>
        <ALISTabsContent value="placements"><PlacementsTab /></ALISTabsContent>
        <ALISTabsContent value="jobs"><JobBoardTab /></ALISTabsContent>
        <ALISTabsContent value="drives"><DrivesTab /></ALISTabsContent>
        <ALISTabsContent value="alumni"><AlumniDBTab /></ALISTabsContent>
      </ALISTabs>
    </div>
  );
}
