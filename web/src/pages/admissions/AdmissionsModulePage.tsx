/**
 * AdmissionsModulePage — Full Admissions Workflow
 * Route: /admissions/pipeline
 *
 * Tab 1: Applications Kanban (Lead → Submitted → Docs → Eligible → Merit → Offer → Enrolled)
 * Tab 2: Document Review queue (pending verification, forgery flags)
 * Tab 3: Reporting Gate tracker (REPORTING_PENDING applicants, days until deadline)
 * Tab 4: Re-admission applications
 */

import { useState, useEffect } from 'react';

const COLORS = {
  bg: '#0E1020',
  surface: '#11131F',
  card: '#1A1D2E',
  text: '#C9D1E9',
  muted: '#7B82A8',
  border: '#1E2235',
  teal: '#1D9E75',
  purple: '#5D5FEF',
  amber: '#EF9F27',
  red: '#E24B4A',
};

// ── TAB 1: KANBAN ────────────────────────────────────────────────

const STAGES = [
  { key: 'lead', label: 'Lead', count: 0, color: '#7B82A8' },
  { key: 'submitted', label: 'Submitted', count: 0, color: '#5D5FEF' },
  { key: 'docs', label: 'Docs Review', count: 0, color: '#EF9F27' },
  { key: 'eligible', label: 'Eligible', count: 0, color: '#1D9E75' },
  { key: 'merit', label: 'Merit Listed', count: 0, color: '#4CAF9F' },
  { key: 'offer', label: 'Offer Sent', count: 0, color: '#9B59B6' },
  { key: 'enrolled', label: 'Enrolled', count: 0, color: '#1D9E75' },
];

const KANBAN_CARDS: Record<string, { name: string; program: string; branch: string }[]> = {
  lead: [], submitted: [], docs: [], eligible: [], merit: [], offer: [], enrolled: [],
};

// ── TAB 2: DOCUMENT QUEUE ────────────────────────────────────────

type DocItem = {
  id: string;
  applicant: string;
  doc: string;
  status: string;
  method: string;
  flag: string | null;
  submitted: string;
};

const INITIAL_DOC_QUEUE: DocItem[] = [];

// ── TAB 3: REPORTING GATE ────────────────────────────────────────

type ReportingItem = {
  id: string;
  name: string;
  program: string;
  deadline: string;
  daysLeft: number;
  method: string | null;
  reported: boolean;
};

const INITIAL_REPORTING: ReportingItem[] = [
  { id: 'r1', name: 'Suresh Pillai', program: 'B.Tech CSE', deadline: '2026-03-25', daysLeft: 6, method: 'WALK_IN', reported: false },
  { id: 'r2', name: 'Anita Sharma', program: 'MBA', deadline: '2026-03-22', daysLeft: 3, method: 'QR_SCAN', reported: false },
  { id: 'r3', name: 'Vijay Rajan', program: 'B.Sc CS', deadline: '2026-03-20', daysLeft: 1, method: null, reported: false },
];

// ── TAB 4: RE-ADMISSION ──────────────────────────────────────────

type ReadmissionItem = {
  id: string;
  name: string;
  program: string;
  gap: string;
  semesters: number;
  status: string;
};

const INITIAL_READMISSIONS: ReadmissionItem[] = [
  { id: 'ra1', name: 'Deepak Kumar', program: 'B.Tech ME', gap: '2022–2025', semesters: 4, status: 'UNDER_REVIEW' },
  { id: 'ra2', name: 'Nisha Patel', program: 'B.Tech ECE', gap: '2021–2024', semesters: 2, status: 'SUBMITTED' },
];

// ── Helpers ──────────────────────────────────────────────────────

function daysColor(days: number): string {
  if (days > 3) return COLORS.teal;
  if (days >= 2) return COLORS.amber;
  return COLORS.red;
}

function docStatusColor(status: string): string {
  switch (status) {
    case 'APPROVED': return COLORS.teal;
    case 'PENDING': return COLORS.amber;
    case 'FLAGGED': return COLORS.red;
    case 'REJECTED': return COLORS.red;
    default: return COLORS.muted;
  }
}

function methodBadge(method: string | null): string {
  if (!method) return '—';
  return method.replace('_', ' ');
}

// ── API helpers ──────────────────────────────────────────────────

function authHeader() {
  return { Authorization: `Bearer ${sessionStorage.getItem('token') ?? ''}`, 'Content-Type': 'application/json' };
}

// ── Main Component ───────────────────────────────────────────────

export function AdmissionsModulePage() {
  const [activeTab, setActiveTab] = useState<'kanban' | 'docs' | 'reporting' | 'readmission'>('kanban');

  // Kanban stage counts
  const [stages, setStages] = useState(STAGES);

  // Doc queue state
  const [docQueue, setDocQueue] = useState<DocItem[]>(INITIAL_DOC_QUEUE);

  // Reporting gate state
  const [reporting, setReporting] = useState<ReportingItem[]>(INITIAL_REPORTING);

  // Re-admission state
  const [readmissions, setReadmissions] = useState<ReadmissionItem[]>(INITIAL_READMISSIONS);

  // Load pipeline stage counts
  useEffect(() => {
    fetch('/api/v1/admissions/pipeline-summary', { headers: authHeader() })
      .then(r => r.ok ? r.json() as Promise<{ stage: string; count: number }[]> : null)
      .then(data => {
        if (!data || !Array.isArray(data) || data.length === 0) return;
        const by: Record<string, number> = {};
        data.forEach(s => { by[s.stage] = s.count; });
        setStages(STAGES.map(s => {
          let count = s.count;
          if (s.key === 'lead')      count = by['leads']      ?? s.count;
          if (s.key === 'submitted') count = by['applied']    ?? s.count;
          if (s.key === 'docs')      count = by['documents']  ?? s.count;
          if (s.key === 'eligible')  count = by['eligibility'] ?? s.count;
          if (s.key === 'merit')     count = (by['entrance_test'] ?? 0) + (by['interview'] ?? 0) || s.count;
          if (s.key === 'offer')     count = by['offer']      ?? s.count;
          if (s.key === 'enrolled')  count = by['enrolled']   ?? s.count;
          return { ...s, count };
        }));
      })
      .catch(() => {});
  }, []);

  // Load doc review queue
  useEffect(() => {
    fetch('/api/v1/admissions/review?entity_type=applicant', { headers: authHeader() })
      .then(r => r.ok ? r.json() as Promise<{ items?: any[] }> : null)
      .then(data => {
        const items = data?.items ?? [];
        if (items.length === 0) return;
        setDocQueue(items.map((item: any, idx: number) => {
          let method = 'Manual';
          try { method = JSON.parse(item.flags ?? '{}').method ?? 'Manual'; } catch { /* noop */ }
          return {
            id: item.id ?? `ri-${idx}`,
            applicant: item.entity_id ? `Applicant …${String(item.entity_id).slice(-6)}` : 'Applicant',
            doc: item.reason ?? 'Document Review',
            status: item.status === 'APPROVED' ? 'APPROVED' : item.status === 'REJECTED' ? 'REJECTED' : item.flags ? 'FLAGGED' : 'PENDING',
            method,
            flag: (item.status === 'PENDING' && item.reason) ? item.reason : null,
            submitted: item.created_at ? String(item.created_at).slice(0, 10) : '',
          };
        }));
      })
      .catch(() => {});
  }, []);

  // Load re-admissions
  useEffect(() => {
    fetch('/api/v1/admissions/readmission', { headers: authHeader() })
      .then(r => r.ok ? r.json() as Promise<{ applications?: any[] }> : null)
      .then(data => {
        const apps = data?.applications ?? [];
        if (apps.length === 0) return;
        setReadmissions(apps.map((a: any) => ({
          id: a.id,
          name: a.applicant_name ?? a.student_name ?? 'Applicant',
          program: a.program_name ?? a.program_id ?? '—',
          gap: (a.gap_start && a.gap_end) ? `${a.gap_start}–${a.gap_end}` : (a.gap ?? '—'),
          semesters: a.semesters_completed ?? a.gap_semesters ?? 0,
          status: a.status ?? 'SUBMITTED',
        })));
      })
      .catch(() => {});
  }, []);

  async function approveDoc(id: string) {
    await fetch(`/api/v1/admissions/review/${id}/decide`, {
      method: 'POST', headers: authHeader(),
      body: JSON.stringify({ decision: 'APPROVED' }),
    }).catch(() => {});
    setDocQueue((prev) => prev.map((d) => d.id === id ? { ...d, status: 'APPROVED' } : d));
  }
  async function rejectDoc(id: string) {
    await fetch(`/api/v1/admissions/review/${id}/decide`, {
      method: 'POST', headers: authHeader(),
      body: JSON.stringify({ decision: 'REJECTED' }),
    }).catch(() => {});
    setDocQueue((prev) => prev.map((d) => d.id === id ? { ...d, status: 'REJECTED' } : d));
  }
  function markReported(id: string) {
    setReporting((prev) => prev.map((r) => r.id === id ? { ...r, reported: true } : r));
  }
  async function approveReadmission(id: string) {
    await fetch(`/api/v1/admissions/readmission/${id}/approve`, {
      method: 'POST', headers: authHeader(),
      body: JSON.stringify({ notes: '' }),
    }).catch(() => {});
    setReadmissions((prev) => prev.map((r) => r.id === id ? { ...r, status: 'APPROVED' } : r));
  }
  async function rejectReadmission(id: string) {
    await fetch(`/api/v1/admissions/readmission/${id}/reject`, {
      method: 'POST', headers: authHeader(),
      body: JSON.stringify({ notes: '' }),
    }).catch(() => {});
    setReadmissions((prev) => prev.map((r) => r.id === id ? { ...r, status: 'REJECTED' } : r));
  }

  const tabs = [
    { key: 'kanban', label: 'Applications Kanban' },
    { key: 'docs', label: 'Document Queue' },
    { key: 'reporting', label: 'Reporting Gate' },
    { key: 'readmission', label: 'Re-admissions' },
  ] as const;

  return (
    <div style={{ minHeight: '100vh', background: COLORS.bg, color: COLORS.text, fontFamily: 'Inter, system-ui, sans-serif', padding: '24px' }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Admissions Pipeline</h1>
        <p style={{ margin: '4px 0 0', color: COLORS.muted, fontSize: 13 }}>Full admissions workflow — Kanban, Document Queue, Reporting Gate & Re-admissions</p>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 22, background: COLORS.surface, borderRadius: 8, padding: 4, width: 'fit-content' }}>
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            style={{
              padding: '7px 18px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 500,
              background: activeTab === t.key ? COLORS.purple : 'transparent',
              color: activeTab === t.key ? '#fff' : COLORS.muted,
              transition: 'all 0.15s',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── TAB 1: KANBAN ── */}
      {activeTab === 'kanban' && (
        <div style={{ overflowX: 'auto', paddingBottom: 16 }}>
          <div style={{ display: 'flex', gap: 14, minWidth: 'max-content' }}>
            {stages.map((stage) => (
              <div key={stage.key} style={{ width: 180, flexShrink: 0 }}>
                {/* Column header */}
                <div style={{
                  background: COLORS.card, border: `1px solid ${COLORS.border}`,
                  borderTop: `3px solid ${stage.color}`,
                  borderRadius: '8px 8px 0 0', padding: '10px 14px',
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                  <span style={{ fontWeight: 600, fontSize: 13, color: COLORS.text }}>{stage.label}</span>
                  <span style={{
                    fontSize: 11, fontWeight: 700,
                    background: `${stage.color}33`, color: stage.color,
                    padding: '2px 7px', borderRadius: 10,
                  }}>
                    {stage.count}
                  </span>
                </div>

                {/* Column body */}
                <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderTop: 'none', borderRadius: '0 0 8px 8px', minHeight: 280, padding: 8 }}>
                  {KANBAN_CARDS[stage.key].map((card, idx) => (
                    <div key={idx} style={{
                      background: COLORS.card, border: `1px solid ${COLORS.border}`,
                      borderRadius: 7, padding: '10px 12px', marginBottom: 8,
                      cursor: 'pointer',
                    }}>
                      <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: COLORS.text }}>{card.name}</p>
                      <p style={{ margin: '3px 0 0', fontSize: 11, color: COLORS.muted }}>{card.program} · {card.branch}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── TAB 2: DOCUMENT QUEUE ── */}
      {activeTab === 'docs' && (
        <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: `1px solid ${COLORS.border}` }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>Document Verification Queue</span>
            <span style={{ marginLeft: 12, fontSize: 12, color: COLORS.muted }}>{docQueue.filter((d) => d.status === 'PENDING' || d.status === 'FLAGGED').length} awaiting review</span>
          </div>
          {docQueue.map((doc) => (
            <div
              key={doc.id}
              style={{
                padding: '14px 20px',
                borderBottom: `1px solid ${COLORS.border}`,
                borderLeft: doc.status === 'FLAGGED' ? `4px solid ${COLORS.red}` : '4px solid transparent',
                display: 'grid',
                gridTemplateColumns: '1fr auto',
                gap: 16,
                alignItems: 'flex-start',
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                  <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text }}>{doc.applicant}</span>
                  <span style={{ fontSize: 12, color: COLORS.muted }}>—</span>
                  <span style={{ fontSize: 13, color: COLORS.text }}>{doc.doc}</span>
                  <span style={{
                    fontSize: 11, fontWeight: 600, color: docStatusColor(doc.status),
                    background: docStatusColor(doc.status) + '22', padding: '2px 7px', borderRadius: 10,
                  }}>
                    {doc.status}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 14 }}>
                  <span style={{ fontSize: 12, color: COLORS.muted }}>Method: <strong style={{ color: COLORS.text }}>{doc.method}</strong></span>
                  <span style={{ fontSize: 12, color: COLORS.muted }}>Submitted: {doc.submitted}</span>
                </div>
                {doc.flag && (
                  <div style={{ marginTop: 7, padding: '7px 10px', background: `${COLORS.red}18`, border: `1px solid ${COLORS.red}44`, borderRadius: 5 }}>
                    <span style={{ fontSize: 12, color: COLORS.red }}>⚠ {doc.flag}</span>
                  </div>
                )}
              </div>
              {(doc.status === 'PENDING' || doc.status === 'FLAGGED') && (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <button
                    onClick={() => approveDoc(doc.id)}
                    style={{ padding: '6px 14px', background: COLORS.teal, border: 'none', borderRadius: 6, color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => rejectDoc(doc.id)}
                    style={{ padding: '6px 14px', background: 'transparent', border: `1px solid ${COLORS.red}`, borderRadius: 6, color: COLORS.red, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
                  >
                    Reject
                  </button>
                </div>
              )}
              {doc.status === 'APPROVED' && (
                <span style={{ fontSize: 12, color: COLORS.teal, fontWeight: 600, alignSelf: 'center' }}>✓ Approved</span>
              )}
              {doc.status === 'REJECTED' && (
                <span style={{ fontSize: 12, color: COLORS.red, fontWeight: 600, alignSelf: 'center' }}>✗ Rejected</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── TAB 3: REPORTING GATE ── */}
      {activeTab === 'reporting' && (
        <div>
          <div style={{ marginBottom: 14 }}>
            <p style={{ margin: 0, fontSize: 13, color: COLORS.muted }}>Applicants with REPORTING_PENDING status — confirm physical/QR arrival before enrollment provisioning.</p>
          </div>
          <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden' }}>
            <div style={{ padding: '13px 20px', borderBottom: `1px solid ${COLORS.border}` }}>
              <span style={{ fontWeight: 600, fontSize: 14 }}>Reporting Gate — {reporting.filter((r) => !r.reported).length} pending</span>
            </div>
            {reporting.map((r) => (
              <div
                key={r.id}
                style={{
                  padding: '14px 20px',
                  borderBottom: `1px solid ${COLORS.border}`,
                  display: 'grid',
                  gridTemplateColumns: '1fr auto auto auto',
                  gap: 16,
                  alignItems: 'center',
                  opacity: r.reported ? 0.5 : 1,
                }}
              >
                <div>
                  <p style={{ margin: 0, fontSize: 14, fontWeight: 600, color: COLORS.text }}>{r.name}</p>
                  <p style={{ margin: '3px 0 0', fontSize: 12, color: COLORS.muted }}>{r.program} · {r.method ? methodBadge(r.method) : 'Method TBD'}</p>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <p style={{ margin: 0, fontSize: 11, color: COLORS.muted, marginBottom: 3 }}>Deadline</p>
                  <span style={{ fontSize: 12, color: COLORS.text }}>{r.deadline}</span>
                </div>
                <span style={{
                  fontSize: 13, fontWeight: 700,
                  color: daysColor(r.daysLeft),
                  background: daysColor(r.daysLeft) + '22',
                  padding: '4px 12px', borderRadius: 20, whiteSpace: 'nowrap',
                }}>
                  {r.daysLeft}d left
                </span>
                {r.reported ? (
                  <span style={{ fontSize: 12, color: COLORS.teal, fontWeight: 600 }}>✓ Reported</span>
                ) : (
                  <button
                    onClick={() => markReported(r.id)}
                    style={{ padding: '7px 14px', background: COLORS.teal, border: 'none', borderRadius: 6, color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap' }}
                  >
                    Mark Reported
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── TAB 4: RE-ADMISSIONS ── */}
      {activeTab === 'readmission' && (
        <div>
          <div style={{ marginBottom: 14 }}>
            <p style={{ margin: 0, fontSize: 13, color: COLORS.muted }}>Re-admission applications — gap-year applicants returning to complete their programme.</p>
          </div>
          <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px 100px 80px 120px 140px', padding: '10px 20px', borderBottom: `1px solid ${COLORS.border}`, fontSize: 11, color: COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              <span>Applicant</span>
              <span>Programme</span>
              <span>Gap Period</span>
              <span>Semesters</span>
              <span>Status</span>
              <span>Actions</span>
            </div>
            {readmissions.map((ra) => (
              <div
                key={ra.id}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 120px 100px 80px 120px 140px',
                  padding: '14px 20px',
                  borderBottom: `1px solid ${COLORS.border}`,
                  alignItems: 'center',
                }}
              >
                <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text }}>{ra.name}</span>
                <span style={{ fontSize: 13, color: COLORS.muted }}>{ra.program}</span>
                <span style={{ fontSize: 13, color: COLORS.muted }}>{ra.gap}</span>
                <span style={{ fontSize: 13, color: COLORS.text }}>{ra.semesters} sem</span>
                <span style={{
                  fontSize: 11, fontWeight: 600,
                  color: ra.status === 'APPROVED' ? COLORS.teal : ra.status === 'REJECTED' ? COLORS.red : ra.status === 'UNDER_REVIEW' ? COLORS.amber : COLORS.purple,
                  background: (ra.status === 'APPROVED' ? COLORS.teal : ra.status === 'REJECTED' ? COLORS.red : ra.status === 'UNDER_REVIEW' ? COLORS.amber : COLORS.purple) + '22',
                  padding: '3px 8px', borderRadius: 10, display: 'inline-block',
                }}>
                  {ra.status.replace('_', ' ')}
                </span>
                <div style={{ display: 'flex', gap: 8 }}>
                  {ra.status === 'UNDER_REVIEW' ? (
                    <>
                      <button
                        onClick={() => approveReadmission(ra.id)}
                        style={{ padding: '5px 12px', background: COLORS.teal, border: 'none', borderRadius: 5, color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => rejectReadmission(ra.id)}
                        style={{ padding: '5px 12px', background: 'transparent', border: `1px solid ${COLORS.red}`, borderRadius: 5, color: COLORS.red, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
                      >
                        Reject
                      </button>
                    </>
                  ) : (
                    <span style={{ fontSize: 12, color: COLORS.muted }}>—</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
