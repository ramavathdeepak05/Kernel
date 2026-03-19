/**
 * ConvocationPage — E18 Convocation Management
 * Route: /convocation
 *
 * Tab 1: Ceremony Planner (create/manage convocation events)
 * Tab 2: Degree Audit Table (eligible students, distinctions, gold medals)
 * Tab 3: Seating Chart (seat allocation preview)
 * Tab 4: Gold Medals
 */
import { useState } from 'react';

const CONVOCATIONS = [
  { id: 'c1', title: '28th Annual Convocation', date: '2026-05-15', venue: 'Main Auditorium', batch: 2025, status: 'AUDIT_COMPLETE', eligible: 287, total: 312 },
];

const AUDIT_RECORDS = [
  { student: 'Arjun Mehta', program: 'B.Tech CSE', cgpa: 9.12, cgpaNoGrace: 9.08, distinction: true, goldMedal: true, backlogs: 0, duesCleared: true },
  { student: 'Priya Nair', program: 'B.Tech ECE', cgpa: 8.67, cgpaNoGrace: 8.61, distinction: true, goldMedal: false, backlogs: 0, duesCleared: true },
  { student: 'Rohit Bose', program: 'B.Tech ME', cgpa: 7.43, cgpaNoGrace: 7.43, distinction: false, goldMedal: false, backlogs: 0, duesCleared: true },
  { student: 'Kavitha Rao', program: 'MBA', cgpa: 9.34, cgpaNoGrace: 9.28, distinction: true, goldMedal: true, backlogs: 0, duesCleared: true },
  { student: 'Deepak Singh', program: 'B.Sc CS', cgpa: 6.12, cgpaNoGrace: 6.12, distinction: false, goldMedal: false, backlogs: 2, duesCleared: false },
];

const GOLD_MEDALS = [
  { program: 'B.Tech CSE', winner: 'Arjun Mehta', cgpaNoGrace: 9.08 },
  { program: 'B.Tech ECE', winner: 'Priya Nair', cgpaNoGrace: 8.61 },
  { program: 'MBA', winner: 'Kavitha Rao', cgpaNoGrace: 9.28 },
];

// Seating data for preview
const SEATING_SECTIONS = [
  {
    section: 'A', program: 'B.Tech CSE',
    seats: Array.from({ length: 10 }, (_, i) => ({ id: `A${String(i + 1).padStart(2, '0')}`, student: `CSE Student ${i + 1}` })),
  },
  {
    section: 'B', program: 'B.Tech ECE',
    seats: Array.from({ length: 8 }, (_, i) => ({ id: `B${String(i + 1).padStart(2, '0')}`, student: `ECE Student ${i + 1}` })),
  },
  {
    section: 'C', program: 'B.Tech ME',
    seats: Array.from({ length: 6 }, (_, i) => ({ id: `C${String(i + 1).padStart(2, '0')}`, student: `ME Student ${i + 1}` })),
  },
  {
    section: 'D', program: 'MBA',
    seats: Array.from({ length: 5 }, (_, i) => ({ id: `D${String(i + 1).padStart(2, '0')}`, student: `MBA Student ${i + 1}` })),
  },
];

const SECTION_COLORS: Record<string, string> = { A: '#1D9E75', B: '#5D5FEF', C: '#EF9F27', D: '#E24B4A' };

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

function ActionButton({ label, color, variant = 'outline' }: { label: string; color: string; variant?: 'solid' | 'outline' }) {
  return (
    <button style={{
      background: variant === 'solid' ? color : 'transparent',
      color: variant === 'solid' ? '#fff' : color,
      border: `1px solid ${color}`,
      borderRadius: 6,
      padding: '6px 14px',
      fontSize: 13,
      cursor: 'pointer',
      fontWeight: 500,
    }}>{label}</button>
  );
}

export function ConvocationPage() {
  const [activeTab, setActiveTab] = useState<'planner' | 'audit' | 'seating' | 'medals'>('planner');

  const tabs = [
    { key: 'planner', label: 'Ceremony Planner' },
    { key: 'audit', label: 'Degree Audit' },
    { key: 'seating', label: 'Seating Chart' },
    { key: 'medals', label: 'Gold Medals' },
  ] as const;

  const isEligible = (r: typeof AUDIT_RECORDS[0]) => r.backlogs === 0 && r.duesCleared;

  return (
    <div style={{ minHeight: '100vh', background: COLORS.bg, color: COLORS.text, fontFamily: 'Inter, system-ui, sans-serif', padding: 32 }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: COLORS.text, margin: 0 }}>Convocation Management</h1>
          <p style={{ color: COLORS.muted, marginTop: 6, fontSize: 14 }}>E18 — Ceremony Planning, Degree Audit, Seating & Gold Medals</p>
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

        {/* Tab 1 — Ceremony Planner */}
        {activeTab === 'planner' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {CONVOCATIONS.map(c => (
              <div key={c.id} style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 28 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
                  <div>
                    <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>{c.title}</h2>
                    <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 6 }}>
                      Batch {c.batch} &bull; {c.date} &bull; {c.venue}
                    </div>
                  </div>
                  <StatusBadge label={c.status} color={COLORS.teal} />
                </div>

                {/* Stats */}
                <div style={{ display: 'flex', gap: 20, marginBottom: 24 }}>
                  <div style={{ background: COLORS.surface, borderRadius: 8, padding: '14px 22px', flex: 1, textAlign: 'center' }}>
                    <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.teal }}>{c.eligible}</div>
                    <div style={{ color: COLORS.muted, fontSize: 12 }}>Eligible</div>
                  </div>
                  <div style={{ background: COLORS.surface, borderRadius: 8, padding: '14px 22px', flex: 1, textAlign: 'center' }}>
                    <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.text }}>{c.total}</div>
                    <div style={{ color: COLORS.muted, fontSize: 12 }}>Total Graduates</div>
                  </div>
                  <div style={{ background: COLORS.surface, borderRadius: 8, padding: '14px 22px', flex: 1, textAlign: 'center' }}>
                    <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.amber }}>{c.total - c.eligible}</div>
                    <div style={{ color: COLORS.muted, fontSize: 12 }}>Ineligible</div>
                  </div>
                  <div style={{ background: COLORS.surface, borderRadius: 8, padding: '14px 22px', flex: 1, textAlign: 'center' }}>
                    <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.purple }}>{GOLD_MEDALS.length}</div>
                    <div style={{ color: COLORS.muted, fontSize: 12 }}>Gold Medals</div>
                  </div>
                </div>

                {/* Eligible progress */}
                <div style={{ marginBottom: 24 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: COLORS.muted, marginBottom: 6 }}>
                    <span>Eligibility Progress</span>
                    <span>{Math.round((c.eligible / c.total) * 100)}%</span>
                  </div>
                  <div style={{ height: 8, background: COLORS.surface, borderRadius: 99 }}>
                    <div style={{ width: `${(c.eligible / c.total) * 100}%`, height: '100%', background: COLORS.teal, borderRadius: 99 }} />
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 10 }}>
                  <ActionButton label="Run Degree Audit" color={COLORS.teal} variant="solid" />
                  <ActionButton label="Generate Seating" color={COLORS.purple} />
                  <ActionButton label="Mark Complete" color={COLORS.amber} />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Tab 2 — Degree Audit */}
        {activeTab === 'audit' && (
          <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: COLORS.surface }}>
                  {['Student', 'Program', 'CGPA', 'CGPA (No Grace)', 'Distinction', 'Gold Medal', 'Backlogs', 'Dues', 'Status'].map(h => (
                    <th key={h} style={{ padding: '12px 14px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: COLORS.muted, borderBottom: `1px solid ${COLORS.border}`, whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {AUDIT_RECORDS.map((r, i) => {
                  const eligible = isEligible(r);
                  return (
                    <tr key={r.student} style={{
                      background: !eligible
                        ? `${COLORS.red}0A`
                        : i % 2 === 0 ? 'transparent' : COLORS.surface + '55',
                    }}>
                      <td style={{ padding: '13px 14px', fontWeight: 600, fontSize: 14 }}>
                        {r.goldMedal && <span style={{ marginRight: 6 }}>🥇</span>}
                        {r.student}
                      </td>
                      <td style={{ padding: '13px 14px', fontSize: 13, color: COLORS.muted }}>{r.program}</td>
                      <td style={{ padding: '13px 14px', fontSize: 14, fontWeight: 600 }}>{r.cgpa.toFixed(2)}</td>
                      <td style={{ padding: '13px 14px', fontSize: 14, fontWeight: 600 }}>{r.cgpaNoGrace.toFixed(2)}</td>
                      <td style={{ padding: '13px 14px' }}>
                        {r.distinction
                          ? <span style={{ color: COLORS.teal, fontWeight: 700 }}>Yes</span>
                          : <span style={{ color: COLORS.muted }}>—</span>}
                      </td>
                      <td style={{ padding: '13px 14px' }}>
                        {r.goldMedal
                          ? <span style={{ color: COLORS.amber, fontWeight: 700 }}>Eligible</span>
                          : <span style={{ color: COLORS.muted }}>—</span>}
                      </td>
                      <td style={{ padding: '13px 14px' }}>
                        <span style={{ color: r.backlogs > 0 ? COLORS.red : COLORS.teal, fontWeight: 600 }}>{r.backlogs}</span>
                      </td>
                      <td style={{ padding: '13px 14px' }}>
                        <span style={{ color: r.duesCleared ? COLORS.teal : COLORS.red, fontWeight: 600 }}>
                          {r.duesCleared ? 'Cleared' : 'Pending'}
                        </span>
                      </td>
                      <td style={{ padding: '13px 14px' }}>
                        <StatusBadge label={eligible ? 'ELIGIBLE' : 'INELIGIBLE'} color={eligible ? COLORS.teal : COLORS.red} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Tab 3 — Seating Chart */}
        {activeTab === 'seating' && (
          <div>
            <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 24 }}>
              {/* Legend */}
              <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
                {SEATING_SECTIONS.map(s => (
                  <div key={s.section} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ width: 12, height: 12, borderRadius: 3, background: SECTION_COLORS[s.section] }} />
                    <span style={{ fontSize: 13, color: COLORS.muted }}>Section {s.section} — {s.program}</span>
                  </div>
                ))}
              </div>

              {/* Stage label */}
              <div style={{
                background: COLORS.surface,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 8,
                padding: '10px 0',
                textAlign: 'center',
                color: COLORS.muted,
                fontSize: 13,
                letterSpacing: 2,
                marginBottom: 32,
                fontWeight: 600,
              }}>STAGE</div>

              {/* Seating rows */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                {SEATING_SECTIONS.map(sec => (
                  <div key={sec.section}>
                    <div style={{ fontSize: 12, color: COLORS.muted, marginBottom: 8, letterSpacing: 1 }}>
                      ROW {sec.section} &mdash; {sec.program}
                    </div>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      {sec.seats.map(seat => (
                        <div
                          key={seat.id}
                          title={`${seat.id}: ${seat.student}`}
                          style={{
                            width: 52,
                            height: 44,
                            background: SECTION_COLORS[sec.section] + '22',
                            border: `1px solid ${SECTION_COLORS[sec.section]}55`,
                            borderRadius: 6,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: 12,
                            color: SECTION_COLORS[sec.section],
                            fontWeight: 600,
                            cursor: 'default',
                          }}
                        >
                          {seat.id}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              <div style={{ marginTop: 20, fontSize: 12, color: COLORS.muted, fontStyle: 'italic' }}>
                Hover over a seat to see the assigned student name.
              </div>
            </div>
          </div>
        )}

        {/* Tab 4 — Gold Medals */}
        {activeTab === 'medals' && (
          <div>
            <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 28, marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Gold Medal Recipients — Batch 2025</h3>
                  <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 4 }}>28th Annual Convocation</div>
                </div>
                <button style={{
                  background: COLORS.amber,
                  color: '#000',
                  border: 'none',
                  borderRadius: 6,
                  padding: '8px 18px',
                  fontSize: 13,
                  fontWeight: 700,
                  cursor: 'pointer',
                }}>Export PDF</button>
              </div>

              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: COLORS.surface }}>
                    {['#', 'Program', 'Winner', 'CGPA (No Grace)'].map(h => (
                      <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: 12, fontWeight: 600, color: COLORS.muted, borderBottom: `1px solid ${COLORS.border}` }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {GOLD_MEDALS.map((m, i) => (
                    <tr key={m.program} style={{ background: i % 2 === 0 ? 'transparent' : COLORS.surface + '55' }}>
                      <td style={{ padding: '16px 16px', fontSize: 22 }}>🏆</td>
                      <td style={{ padding: '16px 16px', fontSize: 14, color: COLORS.muted }}>{m.program}</td>
                      <td style={{ padding: '16px 16px', fontWeight: 700, fontSize: 15, color: COLORS.amber }}>{m.winner}</td>
                      <td style={{ padding: '16px 16px', fontWeight: 700, fontSize: 16, color: COLORS.teal }}>{m.cgpaNoGrace.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Criteria note */}
            <div style={{
              background: COLORS.surface,
              border: `1px solid ${COLORS.border}`,
              borderRadius: 8,
              padding: 16,
              fontSize: 13,
              color: COLORS.muted,
            }}>
              <strong style={{ color: COLORS.text }}>Eligibility Criteria:</strong> Highest CGPA (excluding grace marks) in the program, zero backlogs, no pending dues. Only one gold medal per program per batch.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
