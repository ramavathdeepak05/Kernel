import { useState } from "react";
import {
  MessageSquare, Mail, Send, AlertCircle,
  Megaphone, BarChart2, RefreshCw, Layers,
} from "lucide-react";
import {
  useCommsStats, useTemplates, useFailedLogs,
  useAnnouncements, useBulkCampaigns,
} from "@/hooks/use-communication";
import type { NotifTemplate, NotifLog, Announcement, BulkCampaign } from "@/services/communication";

// ── Constants ──────────────────────────────────────────────────

type TabId = "overview" | "templates" | "announcements" | "campaigns" | "logs";

const TEAL        = "#1D9E75";
const TEAL_BG     = "rgba(29,158,117,0.08)";
const TEAL_BORDER = "rgba(29,158,117,0.2)";

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: "overview",      label: "Overview",      icon: <BarChart2 className="w-3.5 h-3.5" /> },
  { id: "templates",     label: "Templates",     icon: <Layers className="w-3.5 h-3.5" /> },
  { id: "announcements", label: "Announcements", icon: <Megaphone className="w-3.5 h-3.5" /> },
  { id: "campaigns",     label: "Campaigns",     icon: <Send className="w-3.5 h-3.5" /> },
  { id: "logs",          label: "Failed logs",   icon: <AlertCircle className="w-3.5 h-3.5" /> },
];

const CHANNEL_COLOR: Record<string, { bg: string; color: string }> = {
  EMAIL:    { bg: "#E6F1FB", color: "#185FA5" },
  SMS:      { bg: "#EAF3DE", color: "#3B6D11" },
  WHATSAPP: { bg: "rgba(37,211,102,0.1)", color: "#1a7c47" },
  IN_APP:   { bg: TEAL_BG, color: TEAL },
  PUSH:     { bg: "#FAEEDA", color: "#854F0B" },
};

const PRIORITY_BADGE: Record<string, { bg: string; color: string }> = {
  URGENT: { bg: "#FCEBEB", color: "#A32D2D" },
  HIGH:   { bg: "#FAEEDA", color: "#854F0B" },
  NORMAL: { bg: "#E6F1FB", color: "#185FA5" },
  LOW:    { bg: "var(--color-background-secondary, #1e2a3a)", color: "var(--color-text-secondary, #64748b)" },
};

const STATUS_BADGE: Record<string, { bg: string; color: string }> = {
  SENT:      { bg: "#EAF3DE", color: "#3B6D11" },
  FAILED:    { bg: "#FCEBEB", color: "#A32D2D" },
  PENDING:   { bg: "#FAEEDA", color: "#854F0B" },
  BOUNCED:   { bg: "#FCEBEB", color: "#A32D2D" },
  RETRYING:  { bg: "#FAEEDA", color: "#854F0B" },
  COMPLETED: { bg: "#EAF3DE", color: "#3B6D11" },
  RUNNING:   { bg: TEAL_BG, color: TEAL },
  QUEUED:    { bg: "#E6F1FB", color: "#185FA5" },
  DRAFT:     { bg: "rgba(100,116,139,0.1)", color: "#64748b" },
  PAUSED:    { bg: "#FAEEDA", color: "#854F0B" },
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

function ChannelIcon({ channel }: { channel: string }) {
  const icons: Record<string, React.ReactNode> = {
    EMAIL:    <Mail className="w-3 h-3" />,
    SMS:      <MessageSquare className="w-3 h-3" />,
    WHATSAPP: <MessageSquare className="w-3 h-3" />,
    IN_APP:   <Megaphone className="w-3 h-3" />,
    PUSH:     <Send className="w-3 h-3" />,
  };
  const s = CHANNEL_COLOR[channel] ?? CHANNEL_COLOR.IN_APP;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 3,
      padding: "2px 7px", borderRadius: 20, fontSize: 10, fontWeight: 500,
      background: s.bg, color: s.color,
    }}>
      {icons[channel]} {channel}
    </span>
  );
}

// ── Overview tab ───────────────────────────────────────────────

function OverviewTab() {
  const { data: stats } = useCommsStats();
  const { data: campaigns } = useBulkCampaigns();
  const { data: failed } = useFailedLogs();

  const kpis = [
    { label: "Active templates",  value: stats?.templates_active ?? "—",  sub: "across all channels",          color: TEAL,     bg: TEAL_BG,                       border: TEAL_BORDER,                   icon: <Layers className="w-5 h-5" /> },
    { label: "Sent today",        value: stats?.sent_today ?? "—",         sub: "notifications dispatched",    color: "#34d399", bg: "rgba(52,211,153,0.08)",       border: "rgba(52,211,153,0.2)",        icon: <Send className="w-5 h-5" /> },
    { label: "Failed today",      value: stats?.failed_today ?? "—",       sub: "pending retry",               color: "#fb7185", bg: "rgba(251,113,133,0.08)",      border: "rgba(251,113,133,0.2)",       icon: <AlertCircle className="w-5 h-5" /> },
    { label: "Delivery rate",     value: stats?.delivery_rate != null ? `${stats.delivery_rate.toFixed(1)}%` : "—", sub: "7-day rolling",  color: "#fbbf24", bg: "rgba(251,191,36,0.08)", border: "rgba(251,191,36,0.2)", icon: <BarChart2 className="w-5 h-5" /> },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* KPIs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 8 }}>
        {kpis.map(k => (
          <div key={k.label} style={{
            background: "var(--color-background-secondary, #0f1c2e)",
            border: `0.5px solid ${k.border}`,
            borderRadius: 8, padding: "10px 12px",
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
              <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)", fontWeight: 500 }}>{k.label}</p>
              <span style={{ color: k.color, opacity: 0.7 }}>{k.icon}</span>
            </div>
            <p style={{ fontSize: 22, fontWeight: 500, color: k.color }}>{k.value}</p>
            <p style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)", marginTop: 2 }}>{k.sub}</p>
          </div>
        ))}
      </div>

      {/* Channel breakdown + recent campaigns */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {/* Channel breakdown */}
        <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
          <div style={{ padding: "9px 12px", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", background: "var(--color-background-secondary, #0f1c2e)" }}>
            <p style={{ fontSize: 11, fontWeight: 500 }}>Channel delivery rates</p>
          </div>
          <div style={{ padding: "8px 12px", display: "flex", flexDirection: "column", gap: 10 }}>
            {(stats?.channel_breakdown ?? [
              { channel: "EMAIL", count: 0, rate: 0 },
              { channel: "SMS", count: 0, rate: 0 },
              { channel: "WHATSAPP", count: 0, rate: 0 },
              { channel: "IN_APP", count: 0, rate: 0 },
            ]).map(c => {
              const rateColor = c.rate >= 95 ? TEAL : c.rate >= 80 ? "#fbbf24" : "#fb7185";
              return (
                <div key={c.channel}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                    <ChannelIcon channel={c.channel} />
                    <span style={{ fontSize: 11, fontWeight: 500, color: rateColor }}>{c.count} · {c.rate.toFixed(1)}%</span>
                  </div>
                  <div style={{ height: 3, borderRadius: 2, background: "rgba(255,255,255,0.06)" }}>
                    <div style={{ width: `${c.rate}%`, height: "100%", borderRadius: 2, background: rateColor }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Active campaigns */}
        <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
          <div style={{ padding: "9px 12px", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", background: "var(--color-background-secondary, #0f1c2e)" }}>
            <p style={{ fontSize: 11, fontWeight: 500 }}>Recent campaigns</p>
          </div>
          {(campaigns ?? []).slice(0, 5).map((c, i, arr) => {
            const s = STATUS_BADGE[c.status] ?? STATUS_BADGE.DRAFT;
            const pct = c.total_recipients > 0 ? Math.round((c.sent_count / c.total_recipients) * 100) : 0;
            return (
              <div key={c.id} style={{
                padding: "8px 12px",
                borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <p style={{ fontSize: 12, fontWeight: 500 }}>{c.name}</p>
                  <Badge s={s}>{c.status}</Badge>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <ChannelIcon channel={c.channel} />
                  <span style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)" }}>{c.sent_count}/{c.total_recipients}</span>
                  <div style={{ flex: 1, height: 3, borderRadius: 2, background: "rgba(255,255,255,0.06)" }}>
                    <div style={{ width: `${pct}%`, height: "100%", borderRadius: 2, background: TEAL }} />
                  </div>
                </div>
              </div>
            );
          })}
          {!campaigns?.length && (
            <div style={{ padding: "16px 12px", textAlign: "center", fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}>
              No campaigns yet
            </div>
          )}
        </div>
      </div>

      {/* Agent brief */}
      <div style={{ border: `0.5px solid ${TEAL_BORDER}`, borderRadius: 8, padding: "10px 12px", background: TEAL_BG }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: TEAL, display: "inline-block" }} />
          <span style={{ fontSize: 11, fontWeight: 500, color: TEAL }}>Agent brief</span>
        </div>
        <p style={{ fontSize: 12, color: "var(--color-text-secondary, #94a3b8)", lineHeight: 1.6 }}>
          {failed?.length
            ? `${failed.length} notifications failed in the last 24 hours. ${failed.filter(f => f.channel === "EMAIL").length} are email bounces — check SPF/DKIM config.`
            : "All channels are delivering normally. No retries pending."}
          {campaigns?.filter(c => c.status === "RUNNING").length
            ? ` ${campaigns.filter(c => c.status === "RUNNING").length} campaign(s) are currently running.`
            : ""}
        </p>
      </div>
    </div>
  );
}

// ── Templates tab ──────────────────────────────────────────────

function TemplatesTab() {
  const { data: templates, isLoading } = useTemplates();

  const cols = "2.5fr 1fr 1fr 80px";

  return (
    <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
      <div style={{ display: "grid", gridTemplateColumns: cols, padding: "6px 12px", background: "var(--color-background-secondary, #0f1c2e)", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" }}>
        {["Template", "Channel", "Code", "Active"].map(h => (
          <span key={h} style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary, #64748b)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{h}</span>
        ))}
      </div>
      {isLoading && (
        <div style={{ padding: "20px 12px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>Loading…</div>
      )}
      {(templates ?? []).map((t: NotifTemplate, i, arr) => (
        <div key={t.id} style={{
          display: "grid", gridTemplateColumns: cols, padding: "9px 12px", alignItems: "center",
          borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
        }}>
          <div>
            <p style={{ fontSize: 12, fontWeight: 500 }}>{t.name}</p>
            {t.subject && <p style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)", marginTop: 1 }}>{t.subject}</p>}
          </div>
          <ChannelIcon channel={t.channel} />
          <code style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)", fontFamily: "monospace" }}>{t.code}</code>
          <span style={{
            width: 8, height: 8, borderRadius: "50%",
            background: t.is_active ? TEAL : "rgba(100,116,139,0.4)",
            display: "inline-block",
          }} />
        </div>
      ))}
      {!isLoading && !templates?.length && (
        <div style={{ padding: "20px 12px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>
          No templates yet — create your first template
        </div>
      )}
    </div>
  );
}

// ── Announcements tab ──────────────────────────────────────────

function AnnouncementsTab() {
  const { data: announcements, isLoading } = useAnnouncements();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {isLoading && (
        <div style={{ padding: "20px 12px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>Loading…</div>
      )}
      {(announcements ?? []).map((a: Announcement) => {
        const ps = PRIORITY_BADGE[a.priority] ?? PRIORITY_BADGE.NORMAL;
        return (
          <div key={a.id} style={{
            border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))",
            borderRadius: 8, padding: "10px 12px",
            borderLeft: a.priority === "URGENT" ? "2.5px solid #E24B4A" : a.priority === "HIGH" ? "2.5px solid #EF9F27" : "2.5px solid transparent",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
              <div style={{ flex: 1, marginRight: 12 }}>
                <p style={{ fontSize: 13, fontWeight: 500 }}>{a.title}</p>
                <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)", marginTop: 2 }}>{a.body}</p>
              </div>
              <Badge s={ps}>{a.priority}</Badge>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {a.target_roles.map(r => (
                <span key={r} style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)", background: "rgba(255,255,255,0.04)", padding: "1px 6px", borderRadius: 4 }}>{r}</span>
              ))}
              <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--color-text-secondary, #64748b)" }}>
                {a.read_count} read · {new Date(a.created_at).toLocaleDateString()}
              </span>
            </div>
          </div>
        );
      })}
      {!isLoading && !announcements?.length && (
        <div style={{ padding: "24px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)", border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8 }}>
          No active announcements
        </div>
      )}
    </div>
  );
}

// ── Campaigns tab ──────────────────────────────────────────────

function CampaignsTab() {
  const { data: campaigns, isLoading } = useBulkCampaigns();
  const cols = "2fr 1fr 1fr 1.5fr 80px";

  return (
    <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
      <div style={{ display: "grid", gridTemplateColumns: cols, padding: "6px 12px", background: "var(--color-background-secondary, #0f1c2e)", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" }}>
        {["Campaign", "Channel", "Status", "Progress", "Fail"].map(h => (
          <span key={h} style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary, #64748b)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{h}</span>
        ))}
      </div>
      {isLoading && (
        <div style={{ padding: "20px 12px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>Loading…</div>
      )}
      {(campaigns ?? []).map((c: BulkCampaign, i, arr) => {
        const ss = STATUS_BADGE[c.status] ?? STATUS_BADGE.DRAFT;
        const pct = c.total_recipients > 0 ? Math.round((c.sent_count / c.total_recipients) * 100) : 0;
        const barColor = pct >= 90 ? TEAL : pct >= 50 ? "#fbbf24" : "#fb7185";
        return (
          <div key={c.id} style={{
            display: "grid", gridTemplateColumns: cols, padding: "9px 12px", alignItems: "center",
            borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
          }}>
            <div>
              <p style={{ fontSize: 12, fontWeight: 500 }}>{c.name}</p>
              <p style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)", marginTop: 1 }}>
                {c.scheduled_at ? new Date(c.scheduled_at).toLocaleString() : "Immediate"}
              </p>
            </div>
            <ChannelIcon channel={c.channel} />
            <Badge s={ss}>{c.status}</Badge>
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                <span style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)" }}>{c.sent_count}/{c.total_recipients}</span>
                <span style={{ fontSize: 10, fontWeight: 500, color: barColor }}>{pct}%</span>
              </div>
              <div style={{ height: 3, borderRadius: 2, background: "rgba(255,255,255,0.06)" }}>
                <div style={{ width: `${pct}%`, height: "100%", borderRadius: 2, background: barColor }} />
              </div>
            </div>
            <span style={{ fontSize: 11, fontWeight: 500, color: c.failed_count > 0 ? "#fb7185" : "var(--color-text-secondary, #64748b)" }}>
              {c.failed_count}
            </span>
          </div>
        );
      })}
      {!isLoading && !campaigns?.length && (
        <div style={{ padding: "20px 12px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>
          No campaigns yet
        </div>
      )}
    </div>
  );
}

// ── Failed logs tab ────────────────────────────────────────────

function FailedLogsTab() {
  const { data: logs, isLoading, refetch } = useFailedLogs();
  const cols = "1fr 1fr 1.5fr 1fr 80px";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <p style={{ fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>
          {logs?.length ?? 0} failed in the last 24 hours
        </p>
        <button
          onClick={() => refetch()}
          style={{ display: "flex", alignItems: "center", gap: 4, padding: "4px 10px", borderRadius: 6, border: "0.5px solid rgba(255,255,255,0.1)", background: "transparent", cursor: "pointer", fontSize: 11, color: "var(--color-text-secondary, #64748b)" }}
        >
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
      </div>
      <div style={{ border: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", borderRadius: 8, overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: cols, padding: "6px 12px", background: "var(--color-background-secondary, #0f1c2e)", borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" }}>
          {["Recipient", "Channel", "Error", "Status", "Time"].map(h => (
            <span key={h} style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary, #64748b)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{h}</span>
          ))}
        </div>
        {isLoading && (
          <div style={{ padding: "20px 12px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>Loading…</div>
        )}
        {(logs ?? []).map((l: NotifLog, i, arr) => {
          const ss = STATUS_BADGE[l.status] ?? STATUS_BADGE.FAILED;
          return (
            <div key={l.id} style={{
              display: "grid", gridTemplateColumns: cols, padding: "8px 12px", alignItems: "center",
              borderBottom: i < arr.length - 1 ? "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))" : "none",
            }}>
              <p style={{ fontSize: 11, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{l.recipient}</p>
              <ChannelIcon channel={l.channel} />
              <p style={{ fontSize: 10, color: "#fb7185", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {l.error_message ?? "Unknown error"}
              </p>
              <Badge s={ss}>{l.status}</Badge>
              <p style={{ fontSize: 10, color: "var(--color-text-secondary, #64748b)" }}>
                {l.created_at ? new Date(l.created_at).toLocaleTimeString() : "—"}
              </p>
            </div>
          );
        })}
        {!isLoading && !logs?.length && (
          <div style={{ padding: "20px 12px", textAlign: "center", fontSize: 12, color: "var(--color-text-secondary, #64748b)" }}>
            No failures in the last 24 hours
          </div>
        )}
      </div>
    </div>
  );
}

// ── Page root ──────────────────────────────────────────────────

export default function CommunicationHubPage() {
  const [tab, setTab] = useState<TabId>("overview");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ fontSize: 16, fontWeight: 500 }}>Communication hub</h1>
          <p style={{ fontSize: 11, color: "var(--color-text-secondary, #64748b)", marginTop: 2 }}>
            Templates · Announcements · Bulk campaigns · Delivery logs
          </p>
        </div>
        <span style={{ fontSize: 10, fontWeight: 500, padding: "3px 8px", borderRadius: 20, background: TEAL_BG, color: TEAL, border: `0.5px solid ${TEAL_BORDER}` }}>
          E10
        </span>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 2, borderBottom: "0.5px solid var(--color-border-tertiary, rgba(255,255,255,0.06))", paddingBottom: 0 }}>
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              display: "flex", alignItems: "center", gap: 5, padding: "6px 12px",
              borderRadius: "6px 6px 0 0", border: "0.5px solid transparent",
              borderBottom: tab === t.id ? "0.5px solid transparent" : "none",
              background: tab === t.id ? "var(--color-background-secondary, #0f1c2e)" : "transparent",
              color: tab === t.id ? TEAL : "var(--color-text-secondary, #64748b)",
              fontSize: 12, fontWeight: tab === t.id ? 500 : 400, cursor: "pointer",
              marginBottom: tab === t.id ? -1 : 0,
              outline: "none",
            }}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "overview"      && <OverviewTab />}
      {tab === "templates"     && <TemplatesTab />}
      {tab === "announcements" && <AnnouncementsTab />}
      {tab === "campaigns"     && <CampaignsTab />}
      {tab === "logs"          && <FailedLogsTab />}
    </div>
  );
}
