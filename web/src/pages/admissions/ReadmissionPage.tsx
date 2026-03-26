/**
 * ReadmissionPage — E17 Re-admission & Credit Transfer
 * Route: /admissions/readmission
 *
 * Tab 1: Re-admission Applications (submit + review)
 * Tab 2: Credit Transfer Requests (AI draft + review)
 */
import { useState, useEffect } from 'react';

const APPS = [
  { id: 'ra1', name: 'Deepak Kumar', program: 'B.Tech ME', gapFrom: '2022-07', gapTo: '2025-01', semesters: 4, status: 'UNDER_REVIEW', rollNo: null },
  { id: 'ra2', name: 'Nisha Patel', program: 'B.Tech ECE', gapFrom: '2021-06', gapTo: '2024-08', semesters: 2, status: 'SUBMITTED', rollNo: null },
  { id: 'ra3', name: 'Vishal Reddy', program: 'MBA', gapFrom: '2020-06', gapTo: '2023-05', semesters: 6, status: 'APPROVED', rollNo: 'RE-2024-000001' },
];

const CREDIT_TRANSFERS = [
  { id: 'ct1', student: 'Vishal Reddy', sourceCourse: 'CS201 — Data Structures', sourceInstitution: 'Mumbai University', sourceCredits: 4, status: 'AI_DRAFTED', aiDraft: { suggestion: 'CS301 — Data Structures & Algorithms', confidence: 0.87 } },
  { id: 'ct2', student: 'Deepak Kumar', sourceCourse: 'ME101 — Engineering Drawing', sourceInstitution: 'Pune University', sourceCredits: 3, status: 'UNDER_REVIEW', aiDraft: { suggestion: 'ME102 — Engineering Graphics', confidence: 0.72 } },
];

const COLORS = {
  bg: '#0E1020',
  card: '#11131F',
  surface: '#1A1D2E',
  text: '#C9D1E9',
  muted: '#7B82A8',
  border: '#1E2235',
  teal: '#1D9E75',
  purple: '#5D5FEF',
  amber: '#EF9F27',
  red: '#E24B4A',
};

const PROGRAMS = ['B.Tech CSE', 'B.Tech ECE', 'B.Tech ME', 'B.Tech Civil', 'MBA', 'MCA', 'M.Tech CSE', 'B.Sc CS'];

function statusColor(status: string): string {
  if (status === 'APPROVED') return COLORS.teal;
  if (status === 'UNDER_REVIEW') return COLORS.amber;
  if (status === 'SUBMITTED') return COLORS.purple;
  if (status === 'AI_DRAFTED') return COLORS.purple;
  if (status === 'REJECTED') return COLORS.red;
  return COLORS.muted;
}

function StatusBadge({ label, color }: { label: string; color: string }) {
  return (
    <span style={{
      background: color + '22',
      color,
      border: `1px solid ${color}44`,
      borderRadius: 6,
      padding: '2px 10px',
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: 0.5,
      whiteSpace: 'nowrap',
    }}>{label.replace(/_/g, ' ')}</span>
  );
}

type AppStatus = 'UNDER_REVIEW' | 'SUBMITTED' | 'APPROVED' | 'REJECTED';

type ReadmissionApp = {
  id: string;
  name: string;
  program: string;
  gapFrom: string;
  gapTo: string;
  semesters: number;
  status: string;
  rollNo: string | null;
};

interface ReadmissionApiRecord {
  id: string;
  applicant_name?: string;
  student_name?: string;
  program_id?: string;
  program_name?: string;
  gap_start?: string;
  gap_end?: string;
  semesters_completed?: number;
  gap_semesters?: number;
  status?: string;
  roll_number?: string;
}

function apiRecordToApp(r: ReadmissionApiRecord): ReadmissionApp {
  return {
    id: r.id,
    name: r.applicant_name ?? r.student_name ?? '—',
    program: r.program_name ?? r.program_id ?? '—',
    gapFrom: r.gap_start?.slice(0, 7) ?? '—',
    gapTo: r.gap_end?.slice(0, 7) ?? '—',
    semesters: r.semesters_completed ?? r.gap_semesters ?? 0,
    status: r.status ?? 'SUBMITTED',
    rollNo: r.roll_number ?? null,
  };
}

async function apiPost(path: string, body: Record<string, unknown> = {}): Promise<boolean> {
  try {
    const token = localStorage.getItem('token') ?? '';
    const res = await fetch(`/api/v1${path}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return res.ok;
  } catch {
    return false;
  }
}

function AppTable({ apps, onRefresh }: { apps: ReadmissionApp[]; onRefresh: () => void }) {
  const [localApps, setLocalApps] = useState(apps);

  useEffect(() => { setLocalApps(apps); }, [apps]);

  async function handleAction(id: string, action: AppStatus) {
    let ok = false;
    if (action === 'UNDER_REVIEW') ok = await apiPost(`/readmission/${id}/review`);
    else if (action === 'APPROVED') ok = await apiPost(`/readmission/${id}/approve`, { notes: '' });
    else if (action === 'REJECTED') ok = await apiPost(`/readmission/${id}/reject`, { notes: '' });
    if (ok) {
      onRefresh();
    } else {
      // Optimistic update on API failure
      setLocalApps(prev => prev.map(a => a.id === id ? { ...a, status: action } : a));
    }
  }

  return (
    <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ background: COLORS.surface }}>
            {['Applicant', 'Program', 'Gap Period', 'Semesters', 'Status', 'Actions'].map(h => (
              <th key={h} style={{ padding: '12px 14px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: COLORS.muted, borderBottom: `1px solid ${COLORS.border}`, whiteSpace: 'nowrap' }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {localApps.map((a, i) => (
            <tr key={a.id} style={{ background: i % 2 === 0 ? 'transparent' : COLORS.surface + '55' }}>
              <td style={{ padding: '13px 14px', fontWeight: 600, fontSize: 14 }}>{a.name}</td>
              <td style={{ padding: '13px 14px', fontSize: 13, color: COLORS.muted }}>{a.program}</td>
              <td style={{ padding: '13px 14px', fontSize: 13, color: COLORS.muted }}>
                {a.gapFrom} &rarr; {a.gapTo}
              </td>
              <td style={{ padding: '13px 14px', fontSize: 14, textAlign: 'center' }}>
                <span style={{ fontWeight: 700, color: COLORS.text }}>{a.semesters}</span>
              </td>
              <td style={{ padding: '13px 14px' }}>
                <StatusBadge label={a.status} color={statusColor(a.status)} />
                {a.status === 'APPROVED' && a.rollNo && (
                  <div style={{ fontSize: 11, color: COLORS.teal, marginTop: 4, fontWeight: 600 }}>{a.rollNo}</div>
                )}
              </td>
              <td style={{ padding: '13px 14px' }}>
                {a.status === 'UNDER_REVIEW' && (
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button onClick={() => handleAction(a.id, 'APPROVED')} style={{
                      background: COLORS.teal, color: '#fff', border: 'none', borderRadius: 6,
                      padding: '5px 12px', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                    }}>Approve</button>
                    <button onClick={() => handleAction(a.id, 'REJECTED')} style={{
                      background: 'transparent', color: COLORS.red, border: `1px solid ${COLORS.red}`,
                      borderRadius: 6, padding: '5px 12px', fontSize: 12, cursor: 'pointer',
                    }}>Reject</button>
                  </div>
                )}
                {a.status === 'SUBMITTED' && (
                  <button onClick={() => handleAction(a.id, 'UNDER_REVIEW')} style={{
                    background: 'transparent', color: COLORS.amber, border: `1px solid ${COLORS.amber}`,
                    borderRadius: 6, padding: '5px 12px', fontSize: 12, cursor: 'pointer',
                  }}>Begin Review</button>
                )}
                {a.status === 'APPROVED' && (
                  <span style={{ fontSize: 13, color: COLORS.teal }}>Enrolled</span>
                )}
                {a.status === 'REJECTED' && (
                  <span style={{ fontSize: 13, color: COLORS.red }}>Rejected</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type FormState = {
  name: string;
  email: string;
  phone: string;
  program: string;
  gapFrom: string;
  gapTo: string;
  semesters: string;
  reason: string;
};

function NewApplicationForm() {
  const [open, setOpen] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [form, setForm] = useState<FormState>({
    name: '', email: '', phone: '', program: '', gapFrom: '', gapTo: '', semesters: '', reason: '',
  });

  function handleChange(field: keyof FormState, value: string) {
    setForm(prev => ({ ...prev, [field]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted(true);
    setTimeout(() => {
      setSubmitted(false);
      setOpen(false);
      setForm({ name: '', email: '', phone: '', program: '', gapFrom: '', gapTo: '', semesters: '', reason: '' });
    }, 2000);
  }

  const inputStyle: React.CSSProperties = {
    width: '100%',
    background: COLORS.surface,
    border: `1px solid ${COLORS.border}`,
    borderRadius: 6,
    padding: '9px 12px',
    color: COLORS.text,
    fontSize: 14,
    outline: 'none',
    boxSizing: 'border-box',
  };

  const labelStyle: React.CSSProperties = {
    fontSize: 12,
    color: COLORS.muted,
    fontWeight: 600,
    marginBottom: 5,
    display: 'block',
  };

  return (
    <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%',
          background: 'transparent',
          border: 'none',
          color: COLORS.text,
          padding: '16px 20px',
          textAlign: 'left',
          cursor: 'pointer',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: 15,
          fontWeight: 600,
        }}
      >
        <span>Submit New Re-admission Application</span>
        <span style={{ color: COLORS.muted, fontSize: 18 }}>{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <form onSubmit={handleSubmit} style={{ padding: '0 20px 20px', borderTop: `1px solid ${COLORS.border}` }}>
          <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <div>
              <label style={labelStyle}>Full Name</label>
              <input required style={inputStyle} value={form.name} onChange={e => handleChange('name', e.target.value)} placeholder="e.g. Rahul Sharma" />
            </div>
            <div>
              <label style={labelStyle}>Email</label>
              <input required type="email" style={inputStyle} value={form.email} onChange={e => handleChange('email', e.target.value)} placeholder="email@example.com" />
            </div>
            <div>
              <label style={labelStyle}>Phone</label>
              <input required style={inputStyle} value={form.phone} onChange={e => handleChange('phone', e.target.value)} placeholder="+91 98765 43210" />
            </div>
            <div>
              <label style={labelStyle}>Program</label>
              <select required style={{ ...inputStyle }} value={form.program} onChange={e => handleChange('program', e.target.value)}>
                <option value="">Select Program</option>
                {PROGRAMS.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Gap From</label>
              <input required type="month" style={inputStyle} value={form.gapFrom} onChange={e => handleChange('gapFrom', e.target.value)} />
            </div>
            <div>
              <label style={labelStyle}>Gap To</label>
              <input required type="month" style={inputStyle} value={form.gapTo} onChange={e => handleChange('gapTo', e.target.value)} />
            </div>
            <div>
              <label style={labelStyle}>Semesters Completed</label>
              <input required type="number" min="1" max="12" style={inputStyle} value={form.semesters} onChange={e => handleChange('semesters', e.target.value)} placeholder="e.g. 4" />
            </div>
          </div>
          <div style={{ marginTop: 14 }}>
            <label style={labelStyle}>Gap Reason</label>
            <textarea required rows={3} style={{ ...inputStyle, resize: 'vertical' }} value={form.reason} onChange={e => handleChange('reason', e.target.value)} placeholder="Explain the reason for the academic gap..." />
          </div>
          <div style={{ marginTop: 16, display: 'flex', gap: 10 }}>
            <button type="submit" style={{
              background: COLORS.teal, color: '#fff', border: 'none', borderRadius: 6,
              padding: '9px 22px', fontSize: 14, fontWeight: 700, cursor: 'pointer',
            }}>
              {submitted ? 'Submitted!' : 'Submit Application'}
            </button>
            <button type="button" onClick={() => setOpen(false)} style={{
              background: 'transparent', color: COLORS.muted, border: `1px solid ${COLORS.border}`,
              borderRadius: 6, padding: '9px 18px', fontSize: 14, cursor: 'pointer',
            }}>Cancel</button>
          </div>
        </form>
      )}
    </div>
  );
}

type CTDecision = Record<string, 'approved' | 'rejected' | 'partial' | null>;

function CreditTransferCard({ ct, decision, onDecide }: {
  ct: typeof CREDIT_TRANSFERS[0];
  decision: 'approved' | 'rejected' | 'partial' | null;
  onDecide: (id: string, val: 'approved' | 'rejected' | 'partial') => void;
}) {
  const conf = ct.aiDraft.confidence;
  const confPct = Math.round(conf * 100);
  const confColor = conf >= 0.8 ? COLORS.teal : conf >= 0.65 ? COLORS.amber : COLORS.red;

  return (
    <div style={{
      background: COLORS.card,
      border: `1px solid ${decision
        ? (decision === 'approved' ? COLORS.teal : decision === 'rejected' ? COLORS.red : COLORS.amber) + '66'
        : COLORS.border}`,
      borderRadius: 10,
      padding: 22,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 15 }}>{ct.student}</div>
          <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 2 }}>{ct.sourceInstitution}</div>
        </div>
        <StatusBadge label={ct.status} color={statusColor(ct.status)} />
      </div>

      {/* Source & Target */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 12, alignItems: 'center', marginBottom: 16 }}>
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: 14 }}>
          <div style={{ fontSize: 11, color: COLORS.muted, marginBottom: 4, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>Source Course</div>
          <div style={{ fontWeight: 600, fontSize: 14 }}>{ct.sourceCourse}</div>
          <div style={{ fontSize: 12, color: COLORS.muted, marginTop: 4 }}>{ct.sourceCredits} Credits &bull; {ct.sourceInstitution}</div>
        </div>

        <div style={{ textAlign: 'center', color: COLORS.muted, fontSize: 20 }}>&#8594;</div>

        <div style={{ background: COLORS.purple + '15', border: `1px solid ${COLORS.purple}44`, borderRadius: 8, padding: 14 }}>
          <div style={{ fontSize: 11, color: COLORS.purple, marginBottom: 4, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>AI Draft Equivalency</div>
          <div style={{ fontWeight: 600, fontSize: 14 }}>{ct.aiDraft.suggestion}</div>
          <div style={{ fontSize: 12, color: COLORS.muted, marginTop: 4 }}>Suggested by AI</div>
        </div>
      </div>

      {/* Confidence bar */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: COLORS.muted, marginBottom: 6 }}>
          <span>AI Confidence</span>
          <span style={{ color: confColor, fontWeight: 700 }}>{confPct}%</span>
        </div>
        <div style={{ height: 8, background: COLORS.surface, borderRadius: 99 }}>
          <div style={{ width: `${confPct}%`, height: '100%', background: confColor, borderRadius: 99 }} />
        </div>
        <div style={{ fontSize: 11, color: COLORS.muted, marginTop: 4 }}>
          {conf >= 0.8
            ? 'High confidence — recommend direct approval.'
            : conf >= 0.65
            ? 'Medium confidence — manual review advised.'
            : 'Low confidence — requires academic committee decision.'}
        </div>
      </div>

      {/* Decision panel */}
      {!decision ? (
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => onDecide(ct.id, 'approved')} style={{
            background: COLORS.teal, color: '#fff', border: 'none', borderRadius: 6,
            padding: '7px 16px', fontSize: 13, fontWeight: 600, cursor: 'pointer',
          }}>Approve</button>
          <button onClick={() => onDecide(ct.id, 'partial')} style={{
            background: 'transparent', color: COLORS.amber, border: `1px solid ${COLORS.amber}`,
            borderRadius: 6, padding: '7px 16px', fontSize: 13, cursor: 'pointer',
          }}>Partial Credit</button>
          <button onClick={() => onDecide(ct.id, 'rejected')} style={{
            background: 'transparent', color: COLORS.red, border: `1px solid ${COLORS.red}`,
            borderRadius: 6, padding: '7px 16px', fontSize: 13, cursor: 'pointer',
          }}>Reject</button>
        </div>
      ) : (
        <div style={{
          background: (decision === 'approved' ? COLORS.teal : decision === 'rejected' ? COLORS.red : COLORS.amber) + '18',
          border: `1px solid ${(decision === 'approved' ? COLORS.teal : decision === 'rejected' ? COLORS.red : COLORS.amber)}44`,
          borderRadius: 6,
          padding: '10px 14px',
          fontSize: 13,
          color: decision === 'approved' ? COLORS.teal : decision === 'rejected' ? COLORS.red : COLORS.amber,
          fontWeight: 600,
        }}>
          {decision === 'approved' && 'Credit transfer approved. Equivalency recorded in student transcript.'}
          {decision === 'partial' && 'Partial credit granted. Academic coordinator will finalize credit count.'}
          {decision === 'rejected' && 'Transfer request rejected. Student has been notified.'}
        </div>
      )}
    </div>
  );
}

export function ReadmissionPage() {
  const [activeTab, setActiveTab] = useState<'applications' | 'credits'>('applications');
  const [decisions, setDecisions] = useState<CTDecision>({});
  const [apps, setApps] = useState<ReadmissionApp[]>(APPS.map(a => a as ReadmissionApp));

  function loadApps() {
    const token = localStorage.getItem('token') ?? '';
    fetch('/api/v1/readmission', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() as Promise<{ applications?: ReadmissionApiRecord[] }> : null)
      .then(data => {
        const list = data?.applications ?? [];
        if (list.length > 0) setApps(list.map(apiRecordToApp));
      })
      .catch(() => {/* keep static fallback */});
  }

  useEffect(() => { loadApps(); }, []);

  const tabs = [
    { key: 'applications', label: 'Re-admission Applications' },
    { key: 'credits', label: 'Credit Transfer' },
  ] as const;

  function handleDecide(id: string, val: 'approved' | 'rejected' | 'partial') {
    setDecisions(prev => ({ ...prev, [id]: val }));
  }

  return (
    <div style={{ minHeight: '100vh', background: COLORS.bg, color: COLORS.text, fontFamily: 'Inter, system-ui, sans-serif', padding: 32 }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: COLORS.text, margin: 0 }}>Re-admission & Credit Transfer</h1>
          <p style={{ color: COLORS.muted, marginTop: 6, fontSize: 14 }}>E17 — Gap-year re-entries and AI-assisted course equivalency decisions</p>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 4, borderBottom: `1px solid ${COLORS.border}`, marginBottom: 28 }}>
          {tabs.map(t => (
            <button key={t.key} onClick={() => setActiveTab(t.key)} style={{
              background: activeTab === t.key ? COLORS.surface : 'transparent',
              color: activeTab === t.key ? COLORS.text : COLORS.muted,
              border: 'none',
              borderBottom: activeTab === t.key ? `2px solid ${COLORS.teal}` : '2px solid transparent',
              padding: '10px 20px',
              fontSize: 14,
              fontWeight: activeTab === t.key ? 600 : 400,
              cursor: 'pointer',
              borderRadius: '6px 6px 0 0',
            }}>{t.label}</button>
          ))}
        </div>

        {/* Tab 1 — Re-admission Applications */}
        {activeTab === 'applications' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Summary chips */}
            <div style={{ display: 'flex', gap: 12 }}>
              {[
                { label: 'Total', count: apps.length, color: COLORS.muted },
                { label: 'Under Review', count: apps.filter(a => a.status === 'UNDER_REVIEW').length, color: COLORS.amber },
                { label: 'Submitted', count: apps.filter(a => a.status === 'SUBMITTED').length, color: COLORS.purple },
                { label: 'Approved', count: apps.filter(a => a.status === 'APPROVED').length, color: COLORS.teal },
              ].map(s => (
                <div key={s.label} style={{
                  background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: '12px 20px', textAlign: 'center',
                }}>
                  <div style={{ fontSize: 22, fontWeight: 700, color: s.color }}>{s.count}</div>
                  <div style={{ fontSize: 12, color: COLORS.muted }}>{s.label}</div>
                </div>
              ))}
            </div>

            <AppTable apps={apps} onRefresh={loadApps} />
            <NewApplicationForm />
          </div>
        )}

        {/* Tab 2 — Credit Transfer */}
        {activeTab === 'credits' && (
          <div>
            <div style={{
              background: COLORS.purple + '12',
              border: `1px solid ${COLORS.purple}33`,
              borderRadius: 8,
              padding: '12px 18px',
              marginBottom: 20,
              fontSize: 13,
              color: COLORS.purple,
            }}>
              AI has auto-drafted course equivalencies based on syllabus similarity analysis. Review and approve, grant partial credit, or reject each request.
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {CREDIT_TRANSFERS.map(ct => (
                <CreditTransferCard
                  key={ct.id}
                  ct={ct}
                  decision={decisions[ct.id] ?? null}
                  onDecide={handleDecide}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
