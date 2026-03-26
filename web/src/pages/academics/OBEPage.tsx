/**
 * OBEPage — E20 OBE / CO-PO Mapping Studio
 * Route: /academics/obe
 *
 * Tab 1: CO-PO Mapping Matrix (course outcomes × program outcomes heatmap)
 * Tab 2: Attainment Report (PO-level attainment %)
 * Tab 3: Gap Analysis (POs below target)
 * Tab 4: NBA Export (download prompt)
 */
import { useState, useEffect } from 'react';

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

// ── API types ───────────────────────────────────────────────────────────────

interface COEntry {
  co_code: string;
  co_description?: string;
  po_mappings?: { po_code: string; strength: number }[];
}

interface MatrixApiResponse {
  course_id: string;
  outcomes?: COEntry[];
}

interface POAttainmentEntry {
  po_code: string;
  avg_attainment_pct?: number;
  attainment_pct?: number;
  target_pct?: number;
}

interface AttainmentApiResponse {
  po_attainment?: POAttainmentEntry[];
  target_pct?: number;
}

interface GapEntry {
  po_code: string;
  attainment_pct: number;
  target_pct: number;
  gap_pct: number;
  status: string;
}

interface Program {
  id: string;
  name: string;
}

interface Course {
  id: string;
  code: string;
  name: string;
}

// ── helpers ─────────────────────────────────────────────────────────────────

function authHeader() {
  return { Authorization: `Bearer ${localStorage.getItem('token') ?? ''}` };
}

function cellStyle(val: number): { background: string; color: string; label: string } {
  if (val === 3) return { background: COLORS.teal, color: '#fff', label: 'H' };
  if (val === 2) return { background: COLORS.amber + '40', color: COLORS.amber, label: 'M' };
  if (val === 1) return { background: COLORS.purple + '22', color: COLORS.purple, label: 'L' };
  return { background: 'transparent', color: COLORS.border, label: '' };
}

// ── OBEPage ─────────────────────────────────────────────────────────────────

export function OBEPage() {
  const [activeTab, setActiveTab] = useState<'matrix' | 'attainment' | 'gaps' | 'export'>('matrix');

  // selector state
  const [programs, setPrograms] = useState<Program[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [programId, setProgramId] = useState('');
  const [courseId, setCourseId] = useState('');

  // data state
  const [matrix, setMatrix] = useState<MatrixApiResponse | null>(null);
  const [attainment, setAttainment] = useState<AttainmentApiResponse | null>(null);
  const [gaps, setGaps] = useState<GapEntry[]>([]);
  const [loadingMatrix, setLoadingMatrix] = useState(false);
  const [loadingAttainment, setLoadingAttainment] = useState(false);

  // load programs on mount
  useEffect(() => {
    fetch('/api/v1/academics/programs', { headers: authHeader() })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        const list: Program[] = (data?.programs ?? data?.data ?? []).map((p: { id: string; name?: string; program_name?: string }) => ({
          id: p.id,
          name: p.name ?? p.program_name ?? p.id,
        }));
        setPrograms(list);
        if (list.length > 0) setProgramId(list[0].id);
      })
      .catch(() => {});
  }, []);

  // load courses when program changes
  useEffect(() => {
    if (!programId) return;
    fetch(`/api/v1/academics/courses?program_id=${programId}`, { headers: authHeader() })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        const list: Course[] = (data?.courses ?? data?.data ?? []).map((c: { id: string; code?: string; name?: string; course_name?: string }) => ({
          id: c.id,
          code: c.code ?? c.id,
          name: c.name ?? c.course_name ?? c.id,
        }));
        setCourses(list);
        if (list.length > 0) setCourseId(list[0].id);
      })
      .catch(() => {});
  }, [programId]);

  // fetch CO-PO matrix when course changes
  useEffect(() => {
    if (!courseId) return;
    setLoadingMatrix(true);
    fetch(`/api/v1/academics/obe/matrix/${courseId}`, { headers: authHeader() })
      .then(r => r.ok ? r.json() : null)
      .then(data => { setMatrix(data ?? null); setLoadingMatrix(false); })
      .catch(() => setLoadingMatrix(false));
  }, [courseId]);

  // fetch attainment + gaps when program changes
  useEffect(() => {
    if (!programId) return;
    setLoadingAttainment(true);
    Promise.all([
      fetch(`/api/v1/academics/obe/attainment/${programId}`, { headers: authHeader() }).then(r => r.ok ? r.json() : null),
      fetch(`/api/v1/academics/obe/gap-analysis/${programId}`, { headers: authHeader() }).then(r => r.ok ? r.json() : null),
    ]).then(([attData, gapData]) => {
      setAttainment(attData ?? null);
      setGaps(Array.isArray(gapData) ? gapData : (gapData?.gaps ?? []));
      setLoadingAttainment(false);
    }).catch(() => setLoadingAttainment(false));
  }, [programId]);

  const tabs = [
    { key: 'matrix',     label: 'CO-PO Matrix'      },
    { key: 'attainment', label: 'Attainment Report'  },
    { key: 'gaps',       label: 'Gap Analysis'       },
    { key: 'export',     label: 'NBA Export'         },
  ] as const;

  const poList = matrix?.outcomes
    ? Array.from(new Set(matrix.outcomes.flatMap(co => (co.po_mappings ?? []).map(m => m.po_code)))).sort()
    : [];

  const attList = attainment?.po_attainment ?? [];
  const targetPct = attainment?.target_pct ?? attList[0]?.target_pct ?? 70;
  const gapPOs = gaps.filter(g => g.status !== 'MET' || g.gap_pct > 0);

  return (
    <div style={{ minHeight: '100vh', background: COLORS.bg, color: COLORS.text, fontFamily: 'Inter, system-ui, sans-serif', padding: 32 }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        {/* Header */}
        <div style={{ marginBottom: 20 }}>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: COLORS.text, margin: 0 }}>OBE / CO-PO Mapping Studio</h1>
          <p style={{ color: COLORS.muted, marginTop: 6, fontSize: 14 }}>E20 — Outcome-Based Education Compliance</p>
        </div>

        {/* Selectors */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
          <div>
            <label style={{ fontSize: 11, color: COLORS.muted, display: 'block', marginBottom: 4 }}>Program</label>
            <select
              value={programId}
              onChange={e => setProgramId(e.target.value)}
              style={{ padding: '7px 12px', borderRadius: 7, border: `1px solid ${COLORS.border}`, background: COLORS.card, color: COLORS.text, fontSize: 13 }}
            >
              {programs.length === 0 && <option value="">Loading…</option>}
              {programs.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          {activeTab === 'matrix' && (
            <div>
              <label style={{ fontSize: 11, color: COLORS.muted, display: 'block', marginBottom: 4 }}>Course</label>
              <select
                value={courseId}
                onChange={e => setCourseId(e.target.value)}
                style={{ padding: '7px 12px', borderRadius: 7, border: `1px solid ${COLORS.border}`, background: COLORS.card, color: COLORS.text, fontSize: 13 }}
              >
                {courses.length === 0 && <option value="">No courses</option>}
                {courses.map(c => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
              </select>
            </div>
          )}
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

        {/* Tab 1 — CO-PO Matrix */}
        {activeTab === 'matrix' && (
          <div>
            <div style={{ display: 'flex', gap: 16, marginBottom: 18, alignItems: 'center' }}>
              <span style={{ fontSize: 12, color: COLORS.muted }}>Mapping Strength:</span>
              {[
                { label: 'H — High (3)',   bg: COLORS.teal, color: '#fff' },
                { label: 'M — Medium (2)', bg: COLORS.amber + '40', color: COLORS.amber },
                { label: 'L — Low (1)',    bg: COLORS.purple + '22', color: COLORS.purple },
                { label: 'No Mapping',     bg: COLORS.surface, color: COLORS.muted },
              ].map(l => (
                <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <div style={{ width: 26, height: 18, borderRadius: 3, background: l.bg, border: `1px solid ${COLORS.border}` }} />
                  <span style={{ fontSize: 12, color: COLORS.muted }}>{l.label}</span>
                </div>
              ))}
            </div>

            {loadingMatrix ? (
              <div style={{ textAlign: 'center', padding: 48, color: COLORS.muted }}>Loading matrix…</div>
            ) : !matrix || (matrix.outcomes ?? []).length === 0 ? (
              <div style={{ textAlign: 'center', padding: 48, color: COLORS.muted, fontSize: 14 }}>
                {courseId ? 'No CO-PO mapping data for this course.' : 'Select a course to view the CO-PO matrix.'}
              </div>
            ) : (
              <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'auto' }}>
                <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 700 }}>
                  <thead>
                    <tr style={{ background: COLORS.surface }}>
                      <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: 12, color: COLORS.muted, borderBottom: `1px solid ${COLORS.border}`, borderRight: `1px solid ${COLORS.border}`, minWidth: 200 }}>
                        Course Outcome
                      </th>
                      {poList.map(po => (
                        <th key={po} style={{ padding: '10px 8px', textAlign: 'center', fontSize: 12, color: COLORS.muted, borderBottom: `1px solid ${COLORS.border}`, borderRight: `1px solid ${COLORS.border}20`, minWidth: 52 }}>
                          {po}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(matrix.outcomes ?? []).map((co, ri) => {
                      const strengthMap: Record<string, number> = {};
                      (co.po_mappings ?? []).forEach(m => { strengthMap[m.po_code] = m.strength; });
                      return (
                        <tr key={co.co_code} style={{ background: ri % 2 === 0 ? 'transparent' : COLORS.surface + '55' }}>
                          <td style={{ padding: '10px 16px', borderRight: `1px solid ${COLORS.border}`, borderBottom: `1px solid ${COLORS.border}20` }}>
                            <span style={{ fontWeight: 700, color: COLORS.teal, fontSize: 13 }}>{co.co_code}</span>
                            {co.co_description && (
                              <div style={{ fontSize: 11, color: COLORS.muted, marginTop: 2, maxWidth: 200, lineHeight: 1.4 }}>{co.co_description}</div>
                            )}
                          </td>
                          {poList.map(po => {
                            const val = strengthMap[po] ?? 0;
                            const cs = cellStyle(val);
                            return (
                              <td key={po} style={{ padding: 4, textAlign: 'center', borderRight: `1px solid ${COLORS.border}20`, borderBottom: `1px solid ${COLORS.border}20` }}>
                                <div style={{ width: 36, height: 28, margin: '0 auto', borderRadius: 4, background: cs.background, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: cs.color }}>
                                  {cs.label}
                                </div>
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Tab 2 — Attainment Report */}
        {activeTab === 'attainment' && (
          <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 28 }}>
            {loadingAttainment ? (
              <div style={{ textAlign: 'center', padding: 48, color: COLORS.muted }}>Loading attainment data…</div>
            ) : attList.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 48, color: COLORS.muted, fontSize: 14 }}>No attainment data for this program yet.</div>
            ) : (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 22 }}>
                  <div>
                    <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>PO-Level Attainment</h3>
                    <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 4 }}>Target: {targetPct}%</div>
                  </div>
                  <div style={{ display: 'flex', gap: 14, fontSize: 13 }}>
                    <span style={{ color: COLORS.teal }}>&#9646; Met target ({attList.filter(a => (a.avg_attainment_pct ?? a.attainment_pct ?? 0) >= targetPct).length})</span>
                    <span style={{ color: COLORS.red }}>&#9646; Below target ({attList.filter(a => (a.avg_attainment_pct ?? a.attainment_pct ?? 0) < targetPct).length})</span>
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  {attList.map(a => {
                    const pct = a.avg_attainment_pct ?? a.attainment_pct ?? 0;
                    const met = pct >= targetPct;
                    return (
                      <div key={a.po_code}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                          <span style={{ fontWeight: 600, fontSize: 14 }}>{a.po_code}</span>
                          <div style={{ display: 'flex', gap: 12, alignItems: 'center', fontSize: 13 }}>
                            <span style={{ color: COLORS.muted }}>Target: {targetPct}%</span>
                            <span style={{ fontWeight: 700, color: met ? COLORS.teal : COLORS.red }}>{pct.toFixed(1)}%</span>
                          </div>
                        </div>
                        <div style={{ position: 'relative', height: 16, background: COLORS.surface, borderRadius: 99 }}>
                          <div style={{ width: `${Math.min(pct, 100)}%`, height: '100%', background: met ? COLORS.teal : COLORS.red, borderRadius: 99, transition: 'width 0.4s' }} />
                          <div style={{ position: 'absolute', left: `${targetPct}%`, top: -3, bottom: -3, width: 2, background: COLORS.amber, borderRadius: 2 }} />
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div style={{ marginTop: 20, fontSize: 12, color: COLORS.muted, fontStyle: 'italic' }}>
                  Orange line indicates target threshold ({targetPct}%). Bars extend to actual attainment %.
                </div>
              </>
            )}
          </div>
        )}

        {/* Tab 3 — Gap Analysis */}
        {activeTab === 'gaps' && (
          <div>
            {loadingAttainment ? (
              <div style={{ textAlign: 'center', padding: 48, color: COLORS.muted }}>Loading gap analysis…</div>
            ) : gapPOs.length === 0 ? (
              <div style={{ background: COLORS.teal + '12', border: `1px solid ${COLORS.teal}33`, borderRadius: 8, padding: '16px 18px', fontSize: 14, color: COLORS.teal, fontWeight: 600 }}>
                All Program Outcomes meet the attainment target.
              </div>
            ) : (
              <>
                <div style={{ background: COLORS.red + '12', border: `1px solid ${COLORS.red}33`, borderRadius: 8, padding: '12px 18px', marginBottom: 20, fontSize: 14, color: COLORS.red, fontWeight: 600 }}>
                  {gapPOs.length} Program Outcome{gapPOs.length !== 1 ? 's' : ''} below the {targetPct}% attainment target.
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  {gapPOs.map(a => (
                    <div key={a.po_code} style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderLeft: `4px solid ${COLORS.red}`, borderRadius: 10, padding: 20 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
                          <span style={{ fontWeight: 800, fontSize: 18, color: COLORS.red }}>{a.po_code}</span>
                          <span style={{ background: COLORS.red + '22', color: COLORS.red, border: `1px solid ${COLORS.red}44`, borderRadius: 6, padding: '2px 10px', fontSize: 11, fontWeight: 700 }}>
                            GAP: -{a.gap_pct.toFixed(1)}%
                          </span>
                        </div>
                        <div style={{ textAlign: 'right', fontSize: 13, color: COLORS.muted }}>
                          <div>Attainment: <span style={{ color: COLORS.red, fontWeight: 700 }}>{a.attainment_pct.toFixed(1)}%</span></div>
                          <div>Target: <span style={{ color: COLORS.text }}>{a.target_pct}%</span></div>
                        </div>
                      </div>
                      <div style={{ position: 'relative', height: 10, background: COLORS.surface, borderRadius: 99, marginBottom: 12 }}>
                        <div style={{ width: `${a.attainment_pct}%`, height: '100%', background: COLORS.red + '88', borderRadius: 99 }} />
                        <div style={{ position: 'absolute', left: `${a.attainment_pct}%`, width: `${a.gap_pct}%`, height: '100%', background: COLORS.red + '33', borderRadius: '0 99px 99px 0', borderRight: `2px dashed ${COLORS.red}` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {/* Tab 4 — NBA Export */}
        {activeTab === 'export' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 28 }}>
              <div style={{ marginBottom: 24 }}>
                <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>NBA OBE Report</h3>
                <div style={{ color: COLORS.muted, fontSize: 14, marginTop: 6 }}>
                  {programs.find(p => p.id === programId)?.name ?? 'Select a program'} — Accreditation Cycle
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {[
                  { label: 'Download CO-PO Matrix',      subtitle: 'Mapping matrix with H/M/L strength values',                format: 'CSV',  color: COLORS.teal   },
                  { label: 'Download Attainment Report', subtitle: 'PO-level attainment data with target comparison',           format: 'PDF',  color: COLORS.purple },
                  { label: 'Download NBA Exhibit 2.6',   subtitle: 'Formatted NBA Tier-1 submission document',                  format: 'DOCX', color: COLORS.amber  },
                ].map(item => (
                  <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: '16px 20px' }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 15 }}>{item.label}</div>
                      <div style={{ fontSize: 13, color: COLORS.muted, marginTop: 3 }}>{item.subtitle}</div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <span style={{ background: item.color + '22', color: item.color, border: `1px solid ${item.color}44`, borderRadius: 4, padding: '2px 8px', fontSize: 11, fontWeight: 700 }}>{item.format}</span>
                      <button style={{ background: item.color, color: '#fff', border: 'none', borderRadius: 6, padding: '8px 18px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
                        {item.label}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: 16, fontSize: 13, color: COLORS.muted }}>
              <strong style={{ color: COLORS.text }}>Note:</strong> Exports are generated from live CO-PO mapping and attainment data. Ensure attainment calculation is complete before submitting to NBA.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
