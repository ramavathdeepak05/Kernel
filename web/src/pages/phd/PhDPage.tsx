/**
 * PhDPage — E15 PhD / Doctoral Research Management
 * Route: /phd
 *
 * Tab 1: Scholar Registry (list of PhD scholars with status and milestone progress)
 * Tab 2: Milestone Tracker (selected scholar's 9-milestone timeline)
 * Tab 3: DC Meeting Scheduler (upcoming meetings, outcomes)
 * Tab 4: Plagiarism Reports (Drillbit check status)
 */
import { useState } from 'react';

const SCHOLARS = [
  { id: 's1', name: 'Dr. Candidate Rajan Kumar', rollNo: 'PHD2023001', program: 'CSE', supervisor: 'Dr. Priya Menon', status: 'RESEARCH', milestonesComplete: 5, totalMilestones: 9, enrolledSince: '2023-07' },
  { id: 's2', name: 'Anjali Singh', rollNo: 'PHD2023045', program: 'ECE', supervisor: 'Dr. Ramesh Iyer', status: 'PROPOSAL_APPROVED', milestonesComplete: 4, totalMilestones: 9, enrolledSince: '2023-07' },
  { id: 's3', name: 'Suresh Bose', rollNo: 'PHD2022012', program: 'ME', supervisor: 'Prof. Kavitha Rao', status: 'THESIS_SUBMITTED', milestonesComplete: 8, totalMilestones: 9, enrolledSince: '2022-07' },
];

const DC_MEETINGS = [
  { id: 'm1', scholar: 'Rajan Kumar', date: '2026-04-15', type: 'Biannual Review', status: 'SCHEDULED', committee: ['Dr. Priya Menon', 'Prof. Anand', 'External: Dr. Sharma'] },
  { id: 'm2', scholar: 'Anjali Singh', date: '2026-05-02', type: 'Proposal Defense', status: 'SCHEDULED', committee: ['Dr. Ramesh Iyer', 'Prof. Kumar'] },
];

const PLAGIARISM = [
  { id: 'p1', scholar: 'Suresh Bose', document: 'Thesis Draft v2.pdf', submittedAt: '2026-03-10', status: 'PASSED', similarity: 18.4, threshold: 25 },
  { id: 'p2', scholar: 'Anjali Singh', document: 'Literature Review.pdf', submittedAt: '2026-03-14', status: 'PENDING', similarity: null, threshold: 25 },
];

const MILESTONES = [
  { key: 'COURSEWORK_COMPLETE', label: 'Coursework Complete', state: 'done', date: 'Jan 2024' },
  { key: 'QUALIFYING_EXAM', label: 'Qualifying Exam', state: 'done', date: 'Apr 2024' },
  { key: 'LITERATURE_REVIEW', label: 'Literature Review', state: 'done', date: 'Jun 2024' },
  { key: 'SYNOPSIS_APPROVAL', label: 'Synopsis Approval', state: 'done', date: 'Aug 2024' },
  { key: 'PROPOSAL_DEFENSE', label: 'Proposal Defense', state: 'done', date: 'Oct 2024' },
  { key: 'DATA_COLLECTION', label: 'Data Collection', state: 'inprogress', date: null },
  { key: 'THESIS_DRAFT', label: 'Thesis Draft', state: 'pending', date: null },
  { key: 'PLAGIARISM_CHECK', label: 'Plagiarism Check', state: 'pending', date: null },
  { key: 'VIVA_VOCE', label: 'Viva Voce', state: 'pending', date: null },
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

function statusColor(status: string): string {
  if (status === 'RESEARCH') return COLORS.teal;
  if (status === 'PROPOSAL_APPROVED') return COLORS.purple;
  if (status === 'THESIS_SUBMITTED') return COLORS.amber;
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
    }}>{label.replace(/_/g, ' ')}</span>
  );
}

function ProgressBar({ value, total }: { value: number; total: number }) {
  const pct = Math.round((value / total) * 100);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: COLORS.border, borderRadius: 99 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: COLORS.teal, borderRadius: 99 }} />
      </div>
      <span style={{ fontSize: 12, color: COLORS.muted, whiteSpace: 'nowrap' }}>{value} / {total}</span>
    </div>
  );
}

export function PhDPage() {
  const [activeTab, setActiveTab] = useState<'registry' | 'milestones' | 'meetings' | 'plagiarism'>('registry');
  const [selectedScholar, setSelectedScholar] = useState(SCHOLARS[0]);

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
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {SCHOLARS.map(s => (
              <div key={s.id} onClick={() => { setSelectedScholar(s); }} style={{
                background: COLORS.card,
                border: `1px solid ${selectedScholar.id === s.id ? COLORS.teal + '66' : COLORS.border}`,
                borderRadius: 10,
                padding: 20,
                cursor: 'pointer',
                transition: 'border-color 0.2s',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 16 }}>{s.name}</div>
                    <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 3 }}>
                      {s.rollNo} &bull; {s.program} &bull; Enrolled: {s.enrolledSince}
                    </div>
                    <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 2 }}>
                      Supervisor: <span style={{ color: COLORS.text }}>{s.supervisor}</span>
                    </div>
                  </div>
                  <StatusBadge label={s.status} color={statusColor(s.status)} />
                </div>
                <ProgressBar value={s.milestonesComplete} total={s.totalMilestones} />
              </div>
            ))}
          </div>
        )}

        {/* Tab 2 — Milestone Tracker */}
        {activeTab === 'milestones' && (
          <div>
            <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 20, marginBottom: 24 }}>
              <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                {SCHOLARS.map(s => (
                  <button key={s.id} onClick={() => setSelectedScholar(s)} style={{
                    background: selectedScholar.id === s.id ? COLORS.teal : COLORS.surface,
                    color: selectedScholar.id === s.id ? '#fff' : COLORS.muted,
                    border: `1px solid ${selectedScholar.id === s.id ? COLORS.teal : COLORS.border}`,
                    borderRadius: 6,
                    padding: '6px 14px',
                    fontSize: 13,
                    cursor: 'pointer',
                  }}>{s.name.split(' ').slice(-2).join(' ')}</button>
                ))}
              </div>
              <div style={{ marginTop: 12, color: COLORS.muted, fontSize: 13 }}>
                Viewing: <span style={{ color: COLORS.text, fontWeight: 600 }}>{selectedScholar.name}</span>
                &nbsp;—&nbsp;{selectedScholar.program} &bull; {selectedScholar.supervisor}
              </div>
            </div>

            <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 28 }}>
              {MILESTONES.map((m, i) => (
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
                    {i < MILESTONES.length - 1 && (
                      <div style={{
                        width: 2,
                        flex: 1,
                        minHeight: 36,
                        background: m.state === 'done' ? COLORS.teal + '66' : COLORS.border,
                      }} />
                    )}
                  </div>
                  {/* Content */}
                  <div style={{ paddingBottom: i < MILESTONES.length - 1 ? 24 : 0, paddingTop: 4, flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 15, color: m.state === 'pending' ? COLORS.muted : COLORS.text }}>
                      {m.label}
                    </div>
                    <div style={{ fontSize: 12, marginTop: 2, color: m.state === 'done' ? COLORS.teal : m.state === 'inprogress' ? COLORS.amber : COLORS.muted }}>
                      {m.state === 'done' ? `Completed ${m.date}` : m.state === 'inprogress' ? 'In Progress' : 'Pending'}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 3 — DC Meetings */}
        {activeTab === 'meetings' && (
          <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: COLORS.surface }}>
                  {['Scholar', 'Date', 'Meeting Type', 'Committee', 'Status', 'Action'].map(h => (
                    <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: 12, fontWeight: 600, color: COLORS.muted, borderBottom: `1px solid ${COLORS.border}` }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {DC_MEETINGS.map((m, i) => (
                  <tr key={m.id} style={{ background: i % 2 === 0 ? 'transparent' : COLORS.surface + '88' }}>
                    <td style={{ padding: '14px 16px', fontWeight: 600, fontSize: 14 }}>{m.scholar}</td>
                    <td style={{ padding: '14px 16px', fontSize: 14, color: COLORS.muted }}>{m.date}</td>
                    <td style={{ padding: '14px 16px', fontSize: 14 }}>{m.type}</td>
                    <td style={{ padding: '14px 16px' }}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {m.committee.map(c => (
                          <span key={c} style={{
                            background: COLORS.purple + '22',
                            color: COLORS.purple,
                            border: `1px solid ${COLORS.purple}44`,
                            borderRadius: 4,
                            padding: '2px 8px',
                            fontSize: 11,
                          }}>{c}</span>
                        ))}
                      </div>
                    </td>
                    <td style={{ padding: '14px 16px' }}>
                      <StatusBadge label={m.status} color={COLORS.teal} />
                    </td>
                    <td style={{ padding: '14px 16px' }}>
                      <button style={{
                        background: 'transparent',
                        color: COLORS.teal,
                        border: `1px solid ${COLORS.teal}`,
                        borderRadius: 6,
                        padding: '5px 12px',
                        fontSize: 12,
                        cursor: 'pointer',
                      }}>Record Outcome</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Tab 4 — Plagiarism Reports */}
        {activeTab === 'plagiarism' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {PLAGIARISM.map(p => (
              <div key={p.id} style={{
                background: COLORS.card,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 10,
                padding: 22,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 16 }}>{p.document}</div>
                    <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 3 }}>Scholar: {p.scholar} &bull; Submitted: {p.submittedAt}</div>
                  </div>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    <StatusBadge label={p.status} color={p.status === 'PASSED' ? COLORS.teal : COLORS.amber} />
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
                    <span>Threshold: {p.threshold}%</span>
                  </div>
                  <div style={{ position: 'relative', height: 20, background: COLORS.surface, borderRadius: 6, overflow: 'visible' }}>
                    {p.similarity !== null && (
                      <div style={{
                        width: `${p.similarity}%`,
                        height: '100%',
                        background: p.status === 'PASSED' ? COLORS.teal : COLORS.red,
                        borderRadius: 6,
                        transition: 'width 0.4s',
                      }} />
                    )}
                    {/* Threshold line */}
                    <div style={{
                      position: 'absolute',
                      left: `${p.threshold}%`,
                      top: -4,
                      bottom: -4,
                      width: 2,
                      background: COLORS.red,
                      borderRadius: 2,
                    }} />
                    {p.similarity === null && (
                      <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', paddingLeft: 10, fontSize: 12, color: COLORS.muted }}>
                        Awaiting result...
                      </div>
                    )}
                  </div>
                  {p.similarity !== null && (
                    <div style={{ marginTop: 6, fontSize: 13, color: p.status === 'PASSED' ? COLORS.teal : COLORS.red, fontWeight: 600 }}>
                      {p.similarity}% similarity &mdash; {p.status === 'PASSED' ? 'Below threshold. Cleared.' : 'Above threshold. Review required.'}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
