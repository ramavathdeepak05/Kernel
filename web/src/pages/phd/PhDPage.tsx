/**
 * PhDPage — E15 PhD / Doctoral Research Management
 * Route: /phd
 *
 * Tab 1: Scholar Registry (list of PhD scholars with status and milestone progress)
 * Tab 2: Milestone Tracker (selected scholar's 9-milestone timeline)
 * Tab 3: DC Meeting Scheduler (upcoming meetings, outcomes)
 * Tab 4: Plagiarism Reports (Drillbit check status)
 */
import { useState, useEffect, useCallback } from 'react';

// ── Types ──────────────────────────────────────────────────────────────────

interface Scholar {
  id: string;
  student_name: string;
  supervisor_name: string;
  status: string;
  milestones_complete: number;
  total_milestones: number;
  enrollment_date?: string;
  program_id?: string;
  research_area?: string;
  roll_no?: string;
}

interface Milestone {
  id: string;
  milestone_type: string;
  status: 'PENDING' | 'COMPLETE';
  completed_at?: string;
  notes?: string;
}

interface DCMeeting {
  id: string;
  phd_id: string;
  scheduled_at?: string;
  held_at?: string;
  committee_members?: string[] | Record<string, string>[];
  agenda?: string;
  minutes?: string;
  outcome?: string;
  next_meeting_due?: string;
  created_at?: string;
}

interface PlagiarismReport {
  id: string;
  phd_id: string;
  document_url?: string;
  similarity_pct?: number | null;
  provider?: string;
  threshold_pct?: number;
  status: string;
  checked_at?: string;
  created_at?: string;
}

interface ScholarDetail extends Scholar {
  milestones: Milestone[];
  latest_dc_meeting?: DCMeeting;
  latest_plagiarism_report?: PlagiarismReport;
  dc_meetings?: DCMeeting[];
  plagiarism_reports?: PlagiarismReport[];
}

// Derived DC meeting row for table (scholar name + meeting data)
interface DCMeetingRow extends DCMeeting {
  scholar_name: string;
  scholar_id: string;
}

// Derived plagiarism row for table (scholar name + report data)
interface PlagiarismRow extends PlagiarismReport {
  scholar_name: string;
}

// ── API ────────────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string): Promise<T | null> {
  try {
    const token = localStorage.getItem('token') ?? '';
    const res = await fetch(`/api/v1${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    return res.json() as Promise<T>;
  } catch {
    return null;
  }
}

// ── Constants ──────────────────────────────────────────────────────────────

const MILESTONE_ORDER = [
  'COURSEWORK_COMPLETE',
  'QUALIFYING_EXAM',
  'LITERATURE_REVIEW',
  'SYNOPSIS_APPROVAL',
  'PROPOSAL_DEFENSE',
  'DATA_COLLECTION',
  'THESIS_DRAFT',
  'PLAGIARISM_CHECK',
  'VIVA_VOCE',
];

const MILESTONE_LABELS: Record<string, string> = {
  COURSEWORK_COMPLETE: 'Coursework Complete',
  QUALIFYING_EXAM: 'Qualifying Exam',
  LITERATURE_REVIEW: 'Literature Review',
  SYNOPSIS_APPROVAL: 'Synopsis Approval',
  PROPOSAL_DEFENSE: 'Proposal Defense',
  DATA_COLLECTION: 'Data Collection',
  THESIS_DRAFT: 'Thesis Draft',
  PLAGIARISM_CHECK: 'Plagiarism Check',
  VIVA_VOCE: 'Viva Voce',
};

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

// ── Helpers ────────────────────────────────────────────────────────────────

function statusColor(status: string): string {
  if (status === 'RESEARCH') return COLORS.teal;
  if (status === 'PROPOSAL_APPROVED') return COLORS.purple;
  if (status === 'THESIS_SUBMITTED') return COLORS.amber;
  if (status === 'DEGREE_AWARDED') return '#60a5fa';
  if (status === 'REGISTERED') return '#a78bfa';
  return COLORS.muted;
}

function formatDate(iso?: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' });
}

function formatEnrolled(iso?: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function committeeNames(members?: string[] | Record<string, string>[]): string[] {
  if (!members || members.length === 0) return [];
  if (typeof members[0] === 'string') return members as string[];
  return (members as Record<string, string>[]).map(m => m.name ?? m.id ?? String(m));
}

// ── Sub-components ─────────────────────────────────────────────────────────

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
    }}>{label.replace(/_/g, ' ')}</span>
  );
}

function ProgressBar({ value, total }: { value: number; total: number }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: COLORS.border, borderRadius: 99 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: COLORS.teal, borderRadius: 99 }} />
      </div>
      <span style={{ fontSize: 12, color: COLORS.muted, whiteSpace: 'nowrap' }}>{value} / {total}</span>
    </div>
  );
}

function Spinner() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
      <div style={{
        width: 28, height: 28, border: `3px solid ${COLORS.border}`,
        borderTopColor: COLORS.teal, borderRadius: '50%', animation: 'spin 0.8s linear infinite',
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────

export function PhDPage() {
  const [activeTab, setActiveTab] = useState<'registry' | 'milestones' | 'meetings' | 'plagiarism'>('registry');

  // Scholars list
  const [scholars, setScholars] = useState<Scholar[]>([]);
  const [scholarsLoading, setScholarsLoading] = useState(true);

  // Selected scholar + detail (for milestones tab)
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ScholarDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // DC meetings — derived from all scholar details (lazy loaded when tab is opened)
  const [dcRows, setDcRows] = useState<DCMeetingRow[]>([]);
  const [plagRows, setPlagRows] = useState<PlagiarismRow[]>([]);
  const [enrichLoading, setEnrichLoading] = useState(false);

  // ── Load scholars list ────────────────────────────────────────────────────
  useEffect(() => {
    setScholarsLoading(true);
    apiFetch<{ scholars: Scholar[] }>('/phd/scholars').then(d => {
      const list = d?.scholars ?? [];
      setScholars(list);
      if (list.length > 0 && !selectedId) setSelectedId(list[0].id);
      setScholarsLoading(false);
    });
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Load selected scholar detail ──────────────────────────────────────────
  useEffect(() => {
    if (!selectedId) return;
    setDetailLoading(true);
    apiFetch<ScholarDetail>(`/phd/scholars/${selectedId}`).then(d => {
      setDetail(d);
      setDetailLoading(false);
    });
  }, [selectedId]);

  // ── Enrich DC meetings + plagiarism rows (when those tabs are opened) ─────
  const loadEnrichedData = useCallback(async () => {
    if (scholars.length === 0) return;
    setEnrichLoading(true);
    const details = await Promise.all(
      scholars.map(s => apiFetch<ScholarDetail>(`/phd/scholars/${s.id}`))
    );
    const meetings: DCMeetingRow[] = [];
    const plagReports: PlagiarismRow[] = [];
    details.forEach((d, i) => {
      if (!d) return;
      const sName = scholars[i].student_name;
      const sId = scholars[i].id;
      // Prefer dc_meetings array, fall back to latest_dc_meeting
      const mtgs = d.dc_meetings ?? (d.latest_dc_meeting ? [d.latest_dc_meeting] : []);
      mtgs.forEach(m => meetings.push({ ...m, scholar_name: sName, scholar_id: sId }));
      // Prefer plagiarism_reports array, fall back to latest_plagiarism_report
      const plags = d.plagiarism_reports ?? (d.latest_plagiarism_report ? [d.latest_plagiarism_report] : []);
      plags.forEach(p => plagReports.push({ ...p, scholar_name: sName }));
    });
    setDcRows(meetings);
    setPlagRows(plagReports);
    setEnrichLoading(false);
  }, [scholars]);

  useEffect(() => {
    if (activeTab === 'meetings' || activeTab === 'plagiarism') {
      if (dcRows.length === 0 && plagRows.length === 0 && !enrichLoading) {
        loadEnrichedData();
      }
    }
  }, [activeTab, dcRows.length, plagRows.length, enrichLoading, loadEnrichedData]);

  // ── Build milestone rows for selected scholar ─────────────────────────────
  const milestoneRows = (() => {
    if (!detail?.milestones) return MILESTONE_ORDER.map(key => ({ key, state: 'pending' as const, date: null }));
    const byType = Object.fromEntries(detail.milestones.map(m => [m.milestone_type, m]));
    // Find first pending to mark as "inprogress"
    let foundFirst = false;
    return MILESTONE_ORDER.map(key => {
      const m = byType[key];
      if (m?.status === 'COMPLETE') return { key, state: 'done' as const, date: m.completed_at ?? null };
      if (!foundFirst) { foundFirst = true; return { key, state: 'inprogress' as const, date: null }; }
      return { key, state: 'pending' as const, date: null };
    });
  })();

  const selectedScholar = scholars.find(s => s.id === selectedId);

  const tabs = [
    { key: 'registry', label: 'Scholar Registry' },
    { key: 'milestones', label: 'Milestone Tracker' },
    { key: 'meetings', label: 'DC Meetings' },
    { key: 'plagiarism', label: 'Plagiarism Reports' },
  ] as const;

  return (
    <div style={{ minHeight: '100vh', background: COLORS.bg, color: COLORS.text, fontFamily: 'Inter, system-ui, sans-serif', padding: 32 }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: COLORS.text, margin: 0 }}>PhD / Doctoral Research Management</h1>
          <p style={{ color: COLORS.muted, marginTop: 6, fontSize: 14 }}>E15 — Scholar Registry, Milestones, DC Meetings & Plagiarism</p>
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

        {/* Tab 1 — Scholar Registry */}
        {activeTab === 'registry' && (
          scholarsLoading ? <Spinner /> : scholars.length === 0 ? (
            <p style={{ color: COLORS.muted, fontSize: 14 }}>No PhD scholars registered.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {scholars.map(s => (
                <div key={s.id} onClick={() => { setSelectedId(s.id); }} style={{
                  background: COLORS.card,
                  border: `1px solid ${selectedId === s.id ? COLORS.teal + '66' : COLORS.border}`,
                  borderRadius: 10,
                  padding: 20,
                  cursor: 'pointer',
                  transition: 'border-color 0.2s',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 16 }}>{s.student_name}</div>
                      <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 3 }}>
                        {s.roll_no ?? s.id.slice(0, 8).toUpperCase()} &bull; {s.program_id ?? s.research_area ?? 'Research'} &bull; Enrolled: {formatEnrolled(s.enrollment_date)}
                      </div>
                      <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 2 }}>
                        Supervisor: <span style={{ color: COLORS.text }}>{s.supervisor_name}</span>
                      </div>
                    </div>
                    <StatusBadge label={s.status} color={statusColor(s.status)} />
                  </div>
                  <ProgressBar value={s.milestones_complete} total={s.total_milestones || 9} />
                </div>
              ))}
            </div>
          )
        )}

        {/* Tab 2 — Milestone Tracker */}
        {activeTab === 'milestones' && (
          scholarsLoading ? <Spinner /> : (
            <div>
              <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 20, marginBottom: 24 }}>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                  {scholars.map(s => (
                    <button key={s.id} onClick={() => setSelectedId(s.id)} style={{
                      background: selectedId === s.id ? COLORS.teal : COLORS.surface,
                      color: selectedId === s.id ? '#fff' : COLORS.muted,
                      border: `1px solid ${selectedId === s.id ? COLORS.teal : COLORS.border}`,
                      borderRadius: 6,
                      padding: '6px 14px',
                      fontSize: 13,
                      cursor: 'pointer',
                    }}>{s.student_name.split(' ').slice(-2).join(' ')}</button>
                  ))}
                </div>
                {selectedScholar && (
                  <div style={{ marginTop: 12, color: COLORS.muted, fontSize: 13 }}>
                    Viewing: <span style={{ color: COLORS.text, fontWeight: 600 }}>{selectedScholar.student_name}</span>
                    &nbsp;—&nbsp;{selectedScholar.program_id ?? selectedScholar.research_area ?? 'Research'} &bull; {selectedScholar.supervisor_name}
                  </div>
                )}
              </div>

              {detailLoading ? <Spinner /> : (
                <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 28 }}>
                  {milestoneRows.map((m, i) => (
                    <div key={m.key} style={{ display: 'flex', gap: 0, position: 'relative' }}>
                      {/* Vertical line */}
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginRight: 18 }}>
                        {/* Circle */}
                        <div style={{
                          width: 30,
                          height: 30,
                          borderRadius: '50%',
                          background: m.state === 'done' ? COLORS.teal : m.state === 'inprogress' ? COLORS.amber + '33' : COLORS.surface,
                          border: `2px solid ${m.state === 'done' ? COLORS.teal : m.state === 'inprogress' ? COLORS.amber : COLORS.border}`,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: 14,
                          flexShrink: 0,
                          zIndex: 1,
                        }}>
                          {m.state === 'done' ? '✓' : m.state === 'inprogress' ? '↻' : ''}
                        </div>
                        {/* Connector line */}
                        {i < milestoneRows.length - 1 && (
                          <div style={{
                            width: 2,
                            flex: 1,
                            minHeight: 36,
                            background: m.state === 'done' ? COLORS.teal + '66' : COLORS.border,
                          }} />
                        )}
                      </div>
                      {/* Content */}
                      <div style={{ paddingBottom: i < milestoneRows.length - 1 ? 24 : 0, paddingTop: 4, flex: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: 15, color: m.state === 'pending' ? COLORS.muted : COLORS.text }}>
                          {MILESTONE_LABELS[m.key] ?? m.key.replace(/_/g, ' ')}
                        </div>
                        <div style={{ fontSize: 12, marginTop: 2, color: m.state === 'done' ? COLORS.teal : m.state === 'inprogress' ? COLORS.amber : COLORS.muted }}>
                          {m.state === 'done' ? `Completed ${formatDate(m.date ?? undefined)}` : m.state === 'inprogress' ? 'In Progress' : 'Pending'}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        )}

        {/* Tab 3 — DC Meetings */}
        {activeTab === 'meetings' && (
          enrichLoading ? <Spinner /> : dcRows.length === 0 ? (
            <p style={{ color: COLORS.muted, fontSize: 14 }}>No DC meetings scheduled yet.</p>
          ) : (
            <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: COLORS.surface }}>
                    {['Scholar', 'Date', 'Agenda', 'Committee', 'Status', 'Action'].map(h => (
                      <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: 12, fontWeight: 600, color: COLORS.muted, borderBottom: `1px solid ${COLORS.border}` }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {dcRows.map((m, i) => {
                    const members = committeeNames(m.committee_members);
                    const hasOutcome = !!m.outcome;
                    return (
                      <tr key={m.id} style={{ background: i % 2 === 0 ? 'transparent' : COLORS.surface + '88' }}>
                        <td style={{ padding: '14px 16px', fontWeight: 600, fontSize: 14 }}>{m.scholar_name}</td>
                        <td style={{ padding: '14px 16px', fontSize: 14, color: COLORS.muted }}>{formatDate(m.scheduled_at ?? m.held_at)}</td>
                        <td style={{ padding: '14px 16px', fontSize: 13, color: COLORS.text, maxWidth: 200 }}>
                          <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.agenda ?? '—'}</div>
                        </td>
                        <td style={{ padding: '14px 16px' }}>
                          {members.length > 0 ? (
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                              {members.slice(0, 3).map(c => (
                                <span key={c} style={{
                                  background: COLORS.purple + '22',
                                  color: COLORS.purple,
                                  border: `1px solid ${COLORS.purple}44`,
                                  borderRadius: 4,
                                  padding: '2px 8px',
                                  fontSize: 11,
                                }}>{c}</span>
                              ))}
                              {members.length > 3 && <span style={{ fontSize: 11, color: COLORS.muted }}>+{members.length - 3}</span>}
                            </div>
                          ) : <span style={{ color: COLORS.muted, fontSize: 13 }}>—</span>}
                        </td>
                        <td style={{ padding: '14px 16px' }}>
                          <StatusBadge label={hasOutcome ? 'COMPLETED' : m.held_at ? 'HELD' : 'SCHEDULED'} color={hasOutcome ? COLORS.teal : COLORS.amber} />
                        </td>
                        <td style={{ padding: '14px 16px' }}>
                          {!hasOutcome && (
                            <button style={{
                              background: 'transparent',
                              color: COLORS.teal,
                              border: `1px solid ${COLORS.teal}`,
                              borderRadius: 6,
                              padding: '5px 12px',
                              fontSize: 12,
                              cursor: 'pointer',
                            }}>Record Outcome</button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
        )}

        {/* Tab 4 — Plagiarism Reports */}
        {activeTab === 'plagiarism' && (
          enrichLoading ? <Spinner /> : plagRows.length === 0 ? (
            <p style={{ color: COLORS.muted, fontSize: 14 }}>No plagiarism reports submitted yet.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {plagRows.map(p => {
                const docName = p.document_url ? p.document_url.split('/').pop() ?? p.document_url : 'Document';
                const threshold = p.threshold_pct ?? 25;
                const similarity = p.similarity_pct ?? null;
                const passed = p.status === 'PASSED' || (similarity !== null && similarity <= threshold);
                return (
                  <div key={p.id} style={{
                    background: COLORS.card,
                    border: `1px solid ${COLORS.border}`,
                    borderRadius: 10,
                    padding: 22,
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 16 }}>{docName}</div>
                        <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 3 }}>
                          Scholar: {p.scholar_name} &bull; Submitted: {formatDate(p.created_at)}
                          {p.provider ? ` &bull; Provider: ${p.provider}` : ''}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                        <StatusBadge label={p.status} color={passed ? COLORS.teal : p.status === 'PENDING' ? COLORS.amber : COLORS.red} />
                        {p.status === 'PENDING' && (
                          <button style={{
                            background: COLORS.surface,
                            color: COLORS.amber,
                            border: `1px solid ${COLORS.amber}`,
                            borderRadius: 6,
                            padding: '5px 12px',
                            fontSize: 12,
                            cursor: 'pointer',
                          }}>Check Again</button>
                        )}
                      </div>
                    </div>

                    {/* Similarity gauge */}
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 13, color: COLORS.muted }}>
                        <span>Similarity</span>
                        <span>Threshold: {threshold}%</span>
                      </div>
                      <div style={{ position: 'relative', height: 20, background: COLORS.surface, borderRadius: 6, overflow: 'visible' }}>
                        {similarity !== null && (
                          <div style={{
                            width: `${Math.min(similarity, 100)}%`,
                            height: '100%',
                            background: passed ? COLORS.teal : COLORS.red,
                            borderRadius: 6,
                            transition: 'width 0.4s',
                          }} />
                        )}
                        {/* Threshold line */}
                        <div style={{
                          position: 'absolute',
                          left: `${threshold}%`,
                          top: -4,
                          bottom: -4,
                          width: 2,
                          background: COLORS.red,
                          borderRadius: 2,
                        }} />
                        {similarity === null && (
                          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', paddingLeft: 10, fontSize: 12, color: COLORS.muted }}>
                            Awaiting result...
                          </div>
                        )}
                      </div>
                      {similarity !== null && (
                        <div style={{ marginTop: 6, fontSize: 13, color: passed ? COLORS.teal : COLORS.red, fontWeight: 600 }}>
                          {similarity}% similarity &mdash; {passed ? 'Below threshold. Cleared.' : 'Above threshold. Review required.'}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )
        )}
      </div>
    </div>
  );
}
