/**
 * ConvocationPage — E18 Convocation Management
 * Route: /convocation
 *
 * Tab 1: Ceremony Planner (create/manage convocation events)
 * Tab 2: Degree Audit Table (eligible students, distinctions, gold medals)
 * Tab 3: Seating Chart (seat allocation preview)
 * Tab 4: Gold Medals
 */
import { useState, useEffect } from 'react';
import { ALISTabs, ALISTabsList, ALISTabsTrigger, ALISTabsContent } from '@/components/ui/alis-tabs';

// ── Types ──────────────────────────────────────────────────────────────────

interface ConvocationEvent {
  id: string;
  title: string;
  ceremony_date?: string;
  venue?: string;
  batch_year?: number;
  status?: string;
  eligible_count?: number;
  total_graduates?: number;
  gold_medals_count?: number;
}

interface AuditRecord {
  id: string;
  student_id?: string;
  student_name?: string;
  program_name?: string;
  program_code?: string;
  cgpa?: number;
  cgpa_no_grace?: number;
  is_distinction?: boolean;
  gold_medal_eligible?: boolean;
  backlogs?: number;
  dues_cleared?: boolean;
}

interface GoldMedal {
  id: string;
  program_name?: string;
  program_code?: string;
  student_name?: string;
  cgpa_no_grace?: number;
}

interface SeatRecord {
  id: string;
  seat_label?: string;
  seat_number?: number;
  section_label?: string;
  student_name?: string;
  program_name?: string;
  program_code?: string;
  overall_position?: number;
}

// ── API ────────────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string): Promise<T | null> {
  try {
    const token = sessionStorage.getItem('token') ?? '';
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

const SECTION_COLORS: Record<string, string> = { A: '#1D9E75', B: '#5D5FEF', C: '#EF9F27', D: '#E24B4A', E: '#60a5fa', F: '#a78bfa' };

function sectionColor(label: string): string {
  return SECTION_COLORS[label?.toUpperCase()?.[0]] ?? '#7B82A8';
}

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

function ActionButton({ label, color, variant = 'outline', onClick }: { label: string; color: string; variant?: 'solid' | 'outline'; onClick?: () => void }) {
  return (
    <button onClick={onClick} style={{
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

function Spinner() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
      <div style={{ width: 28, height: 28, border: `3px solid ${COLORS.border}`, borderTopColor: COLORS.teal, borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// ── Group seats by section/program ─────────────────────────────────────────

interface SeatingSection {
  section: string;
  program: string;
  seats: { id: string; student: string }[];
}

function groupSeats(records: SeatRecord[]): SeatingSection[] {
  const map = new Map<string, SeatingSection>();
  for (const r of records) {
    const sectionKey = r.section_label ?? r.program_code ?? 'A';
    if (!map.has(sectionKey)) {
      map.set(sectionKey, { section: sectionKey, program: r.program_name ?? r.program_code ?? sectionKey, seats: [] });
    }
    const label = r.seat_label ?? `${sectionKey}${String(r.seat_number ?? map.get(sectionKey)!.seats.length + 1).padStart(2, '0')}`;
    map.get(sectionKey)!.seats.push({ id: label, student: r.student_name ?? r.student_id ?? label });
  }
  return Array.from(map.values());
}

// ── Main Component ─────────────────────────────────────────────────────────

export function ConvocationPage() {
  const [convocations, setConvocations] = useState<ConvocationEvent[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [auditRecords, setAuditRecords] = useState<AuditRecord[]>([]);
  const [goldMedals, setGoldMedals] = useState<GoldMedal[]>([]);
  const [seatingSections, setSeatingSections] = useState<SeatingSection[]>([]);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);

  // Load convocations list
  useEffect(() => {
    apiFetch<{ convocations: ConvocationEvent[] }>('/convocation').then(d => {
      const list = d?.convocations ?? [];
      setConvocations(list);
      if (list.length > 0) setSelectedId(list[0].id);
      setLoading(false);
    });
  }, []);

  // Load detail data when convocation selected or tab changes
  useEffect(() => {
    if (!selectedId) return;
    setDetailLoading(true);
    Promise.all([
      apiFetch<{ audit_records: AuditRecord[] }>(`/convocation/${selectedId}/audit`),
      apiFetch<{ gold_medals: GoldMedal[] }>(`/convocation/${selectedId}/gold-medals`),
      apiFetch<{ seating: SeatRecord[] }>(`/convocation/${selectedId}/seating`),
    ]).then(([audit, medals, seating]) => {
      setAuditRecords(audit?.audit_records ?? []);
      setGoldMedals(medals?.gold_medals ?? []);
      setSeatingSections(groupSeats(seating?.seating ?? []));
      setDetailLoading(false);
    });
  }, [selectedId]);

  const selected = convocations.find(c => c.id === selectedId);
  const eligibleCount = auditRecords.filter(r => (r.backlogs ?? 0) === 0 && r.dues_cleared !== false).length;
  const totalCount = auditRecords.length;

  return (
    <div style={{ minHeight: '100vh', background: COLORS.bg, color: COLORS.text, fontFamily: 'Inter, system-ui, sans-serif', padding: 32 }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: COLORS.text, margin: 0 }}>Convocation Management</h1>
          <p style={{ color: COLORS.muted, marginTop: 6, fontSize: 14 }}>E18 — Ceremony Planning, Degree Audit, Seating & Gold Medals</p>
        </div>

        {/* Tabs */}
        <ALISTabs defaultValue="planner">
          <ALISTabsList>
            <ALISTabsTrigger value="planner">Ceremony Planner</ALISTabsTrigger>
            <ALISTabsTrigger value="audit">Degree Audit</ALISTabsTrigger>
            <ALISTabsTrigger value="seating">Seating Chart</ALISTabsTrigger>
            <ALISTabsTrigger value="medals">Gold Medals</ALISTabsTrigger>
          </ALISTabsList>

        {loading ? <Spinner /> : convocations.length === 0 ? (
          <p style={{ color: COLORS.muted, fontSize: 14 }}>No convocation events created yet.</p>
        ) : (
          <>
            {/* Tab 1 — Ceremony Planner */}
            <ALISTabsContent value="planner">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {convocations.map(c => (
                  <div key={c.id}
                    onClick={() => setSelectedId(c.id)}
                    style={{ background: COLORS.card, border: `1px solid ${selectedId === c.id ? COLORS.teal + '66' : COLORS.border}`, borderRadius: 12, padding: 28, cursor: 'pointer' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
                      <div>
                        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>{c.title}</h2>
                        <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 6 }}>
                          {c.batch_year && `Batch ${c.batch_year} · `}{c.ceremony_date} {c.venue && `· ${c.venue}`}
                        </div>
                      </div>
                      <StatusBadge label={c.status ?? 'CREATED'} color={COLORS.teal} />
                    </div>

                    {/* Stats */}
                    <div style={{ display: 'flex', gap: 20, marginBottom: 24 }}>
                      <div style={{ background: COLORS.surface, borderRadius: 8, padding: '14px 22px', flex: 1, textAlign: 'center' }}>
                        <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.teal }}>{c.eligible_count ?? eligibleCount}</div>
                        <div style={{ color: COLORS.muted, fontSize: 12 }}>Eligible</div>
                      </div>
                      <div style={{ background: COLORS.surface, borderRadius: 8, padding: '14px 22px', flex: 1, textAlign: 'center' }}>
                        <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.text }}>{c.total_graduates ?? totalCount}</div>
                        <div style={{ color: COLORS.muted, fontSize: 12 }}>Total Graduates</div>
                      </div>
                      <div style={{ background: COLORS.surface, borderRadius: 8, padding: '14px 22px', flex: 1, textAlign: 'center' }}>
                        <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.amber }}>{(c.total_graduates ?? totalCount) - (c.eligible_count ?? eligibleCount)}</div>
                        <div style={{ color: COLORS.muted, fontSize: 12 }}>Ineligible</div>
                      </div>
                      <div style={{ background: COLORS.surface, borderRadius: 8, padding: '14px 22px', flex: 1, textAlign: 'center' }}>
                        <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.purple }}>{c.gold_medals_count ?? goldMedals.length}</div>
                        <div style={{ color: COLORS.muted, fontSize: 12 }}>Gold Medals</div>
                      </div>
                    </div>

                    {totalCount > 0 && (
                      <div style={{ marginBottom: 24 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: COLORS.muted, marginBottom: 6 }}>
                          <span>Eligibility Progress</span>
                          <span>{Math.round((eligibleCount / totalCount) * 100)}%</span>
                        </div>
                        <div style={{ height: 8, background: COLORS.surface, borderRadius: 99 }}>
                          <div style={{ width: `${(eligibleCount / totalCount) * 100}%`, height: '100%', background: COLORS.teal, borderRadius: 99 }} />
                        </div>
                      </div>
                    )}

                    <div style={{ display: 'flex', gap: 10 }}>
                      <ActionButton label="Run Degree Audit" color={COLORS.teal} variant="solid" />
                      <ActionButton label="Generate Seating" color={COLORS.purple} />
                      <ActionButton label="Mark Complete" color={COLORS.amber} />
                    </div>
                  </div>
                ))}
              </div>
            </ALISTabsContent>

            {/* Tab 2 — Degree Audit */}
            <ALISTabsContent value="audit">
              {detailLoading ? <Spinner /> : auditRecords.length === 0 ? (
                <p style={{ color: COLORS.muted, fontSize: 14 }}>
                  No degree audit records. Select a convocation and click "Run Degree Audit" to generate records.
                </p>
              ) : (
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
                      {auditRecords.map((r, i) => {
                        const eligible = (r.backlogs ?? 0) === 0 && r.dues_cleared !== false;
                        return (
                          <tr key={r.id} style={{
                            background: !eligible
                              ? `${COLORS.red}0A`
                              : i % 2 === 0 ? 'transparent' : COLORS.surface + '55',
                          }}>
                            <td style={{ padding: '13px 14px', fontWeight: 600, fontSize: 14 }}>
                              {r.gold_medal_eligible && <span style={{ marginRight: 6 }}>🥇</span>}
                              {r.student_name ?? r.student_id ?? '—'}
                            </td>
                            <td style={{ padding: '13px 14px', fontSize: 13, color: COLORS.muted }}>{r.program_name ?? r.program_code ?? '—'}</td>
                            <td style={{ padding: '13px 14px', fontSize: 14, fontWeight: 600 }}>{r.cgpa?.toFixed(2) ?? '—'}</td>
                            <td style={{ padding: '13px 14px', fontSize: 14, fontWeight: 600 }}>{r.cgpa_no_grace?.toFixed(2) ?? '—'}</td>
                            <td style={{ padding: '13px 14px' }}>
                              {r.is_distinction
                                ? <span style={{ color: COLORS.teal, fontWeight: 700 }}>Yes</span>
                                : <span style={{ color: COLORS.muted }}>—</span>}
                            </td>
                            <td style={{ padding: '13px 14px' }}>
                              {r.gold_medal_eligible
                                ? <span style={{ color: COLORS.amber, fontWeight: 700 }}>Eligible</span>
                                : <span style={{ color: COLORS.muted }}>—</span>}
                            </td>
                            <td style={{ padding: '13px 14px' }}>
                              <span style={{ color: (r.backlogs ?? 0) > 0 ? COLORS.red : COLORS.teal, fontWeight: 600 }}>{r.backlogs ?? 0}</span>
                            </td>
                            <td style={{ padding: '13px 14px' }}>
                              <span style={{ color: r.dues_cleared !== false ? COLORS.teal : COLORS.red, fontWeight: 600 }}>
                                {r.dues_cleared !== false ? 'Cleared' : 'Pending'}
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
            </ALISTabsContent>

            {/* Tab 3 — Seating Chart */}
            <ALISTabsContent value="seating">
              {detailLoading ? <Spinner /> : seatingSections.length === 0 ? (
                <p style={{ color: COLORS.muted, fontSize: 14 }}>
                  No seating plan generated. Click "Generate Seating" on the Ceremony Planner tab.
                </p>
              ) : (
                <div>
                  <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 24 }}>
                    {/* Legend */}
                    <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
                      {seatingSections.map(s => (
                        <div key={s.section} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <div style={{ width: 12, height: 12, borderRadius: 3, background: sectionColor(s.section) }} />
                          <span style={{ fontSize: 13, color: COLORS.muted }}>Section {s.section} — {s.program}</span>
                        </div>
                      ))}
                    </div>

                    {/* Stage label */}
                    <div style={{
                      background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8,
                      padding: '10px 0', textAlign: 'center', color: COLORS.muted, fontSize: 13,
                      letterSpacing: 2, marginBottom: 32, fontWeight: 600,
                    }}>STAGE</div>

                    {/* Seating rows */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                      {seatingSections.map(sec => {
                        const color = sectionColor(sec.section);
                        return (
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
                                    width: 52, height: 44,
                                    background: color + '22',
                                    border: `1px solid ${color}55`,
                                    borderRadius: 6,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    fontSize: 12, color, fontWeight: 600, cursor: 'default',
                                  }}
                                >
                                  {seat.id}
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    <div style={{ marginTop: 20, fontSize: 12, color: COLORS.muted, fontStyle: 'italic' }}>
                      Hover over a seat to see the assigned student name.
                    </div>
                  </div>
                </div>
              )}
            </ALISTabsContent>

            {/* Tab 4 — Gold Medals */}
            <ALISTabsContent value="medals">
              {detailLoading ? <Spinner /> : (
                <div>
                  <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 28, marginBottom: 20 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                      <div>
                        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>
                          Gold Medal Recipients{selected?.batch_year ? ` — Batch ${selected.batch_year}` : ''}
                        </h3>
                        {selected && <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 4 }}>{selected.title}</div>}
                      </div>
                      <button style={{
                        background: COLORS.amber, color: '#000', border: 'none',
                        borderRadius: 6, padding: '8px 18px', fontSize: 13, fontWeight: 700, cursor: 'pointer',
                      }}>Export PDF</button>
                    </div>

                    {goldMedals.length === 0 ? (
                      <p style={{ color: COLORS.muted, fontSize: 13 }}>
                        No gold medals computed yet. Run the gold medals computation from the Ceremony Planner tab.
                      </p>
                    ) : (
                      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                          <tr style={{ background: COLORS.surface }}>
                            {['#', 'Program', 'Winner', 'CGPA (No Grace)'].map(h => (
                              <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: 12, fontWeight: 600, color: COLORS.muted, borderBottom: `1px solid ${COLORS.border}` }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {goldMedals.map((m, i) => (
                            <tr key={m.id} style={{ background: i % 2 === 0 ? 'transparent' : COLORS.surface + '55' }}>
                              <td style={{ padding: '16px 16px', fontSize: 22 }}>🏆</td>
                              <td style={{ padding: '16px 16px', fontSize: 14, color: COLORS.muted }}>{m.program_name ?? m.program_code ?? '—'}</td>
                              <td style={{ padding: '16px 16px', fontWeight: 700, fontSize: 15, color: COLORS.amber }}>{m.student_name ?? '—'}</td>
                              <td style={{ padding: '16px 16px', fontWeight: 700, fontSize: 16, color: COLORS.teal }}>
                                {m.cgpa_no_grace != null ? m.cgpa_no_grace.toFixed(2) : '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>

                  {/* Criteria note */}
                  <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: 16, fontSize: 13, color: COLORS.muted }}>
                    <strong style={{ color: COLORS.text }}>Eligibility Criteria:</strong> Highest CGPA (excluding grace marks) in the program, zero backlogs, no pending dues. Only one gold medal per program per batch.
                  </div>
                </div>
              )}
            </ALISTabsContent>
          </>
        )}
        </ALISTabs>
      </div>
    </div>
  );
}
