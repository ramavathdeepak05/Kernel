/**
 * OBEPage — E20 OBE / CO-PO Mapping Studio
 * Route: /academics/obe
 *
 * Tab 1: CO-PO Mapping Matrix (course outcomes × program outcomes heatmap)
 * Tab 2: Attainment Report (PO-level attainment %)
 * Tab 3: Gap Analysis (POs below target)
 * Tab 4: NBA Export (download prompt)
 */
import { useState } from 'react';

const PROGRAM_OUTCOMES = ['PO1','PO2','PO3','PO4','PO5','PO6','PO7','PO8','PO9','PO10','PO11','PO12'];

const COURSE_OUTCOMES = [
  { code: 'CO1', description: 'Apply fundamental CS concepts to solve computational problems' },
  { code: 'CO2', description: 'Design and implement data structures for efficient data management' },
  { code: 'CO3', description: 'Analyze algorithm complexity and select optimal approaches' },
  { code: 'CO4', description: 'Develop software using object-oriented design principles' },
  { code: 'CO5', description: 'Communicate technical concepts effectively in written and oral form' },
  { code: 'CO6', description: 'Apply ethical and professional standards in computing practice' },
];

const MAPPING: Record<string, Record<string, number>> = {
  CO1: { PO1: 3, PO2: 2, PO3: 3, PO4: 1, PO5: 0, PO6: 0, PO7: 0, PO8: 0, PO9: 0, PO10: 0, PO11: 0, PO12: 0 },
  CO2: { PO1: 3, PO2: 3, PO3: 2, PO4: 2, PO5: 0, PO6: 0, PO7: 0, PO8: 0, PO9: 0, PO10: 0, PO11: 0, PO12: 0 },
  CO3: { PO1: 2, PO2: 3, PO3: 3, PO4: 0, PO5: 0, PO6: 0, PO7: 0, PO8: 0, PO9: 0, PO10: 0, PO11: 0, PO12: 1 },
  CO4: { PO1: 2, PO2: 2, PO3: 2, PO4: 3, PO5: 1, PO6: 0, PO7: 0, PO8: 0, PO9: 0, PO10: 0, PO11: 0, PO12: 0 },
  CO5: { PO1: 0, PO2: 0, PO3: 0, PO4: 0, PO5: 2, PO6: 0, PO7: 0, PO8: 0, PO9: 3, PO10: 2, PO11: 0, PO12: 0 },
  CO6: { PO1: 0, PO2: 0, PO3: 0, PO4: 0, PO5: 0, PO6: 3, PO7: 2, PO8: 3, PO9: 0, PO10: 0, PO11: 2, PO12: 2 },
};

const ATTAINMENT = [
  { po: 'PO1', attainment: 78.4, target: 70, met: true },
  { po: 'PO2', attainment: 82.1, target: 70, met: true },
  { po: 'PO3', attainment: 74.5, target: 70, met: true },
  { po: 'PO4', attainment: 65.2, target: 70, met: false },
  { po: 'PO5', attainment: 71.8, target: 70, met: true },
  { po: 'PO6', attainment: 68.9, target: 70, met: false },
  { po: 'PO7', attainment: 55.3, target: 70, met: false },
  { po: 'PO8', attainment: 77.2, target: 70, met: true },
  { po: 'PO9', attainment: 83.6, target: 70, met: true },
  { po: 'PO10', attainment: 79.1, target: 70, met: true },
  { po: 'PO11', attainment: 62.4, target: 70, met: false },
  { po: 'PO12', attainment: 48.7, target: 70, met: false },
];

const GAP_ACTIONS: Record<string, string> = {
  PO4: 'Strengthen CO4 practical assessments; add lab-component evaluation to OOP course',
  PO6: 'Increase CO6 mapped assessment weight; introduce ethics case study module',
  PO7: 'Add CO-PO direct instruction sessions; map CO6 to environmental sustainability lab',
  PO11: 'Introduce project-based CO4 mini-projects; increase CO6 industry mentor sessions',
  PO12: 'Design CO3/CO6 capstone project with lifelong learning component; add reflective journals',
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

function cellStyle(val: number): { background: string; color: string; label: string } {
  if (val === 3) return { background: COLORS.teal, color: '#fff', label: 'H' };
  if (val === 2) return { background: COLORS.amber + '40', color: COLORS.amber, label: 'M' };
  if (val === 1) return { background: COLORS.purple + '22', color: COLORS.purple, label: 'L' };
  return { background: 'transparent', color: COLORS.border, label: '' };
}

function avgForPO(po: string): number {
  const vals = COURSE_OUTCOMES.map(co => MAPPING[co.code][po]).filter(v => v > 0);
  if (vals.length === 0) return 0;
  return Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100;
}

export function OBEPage() {
  const [activeTab, setActiveTab] = useState<'matrix' | 'attainment' | 'gaps' | 'export'>('matrix');

  const tabs = [
    { key: 'matrix', label: 'CO-PO Matrix' },
    { key: 'attainment', label: 'Attainment Report' },
    { key: 'gaps', label: 'Gap Analysis' },
    { key: 'export', label: 'NBA Export' },
  ] as const;

  const gapPOs = ATTAINMENT.filter(a => !a.met);

  return (
    <div style={{ minHeight: '100vh', background: COLORS.bg, color: COLORS.text, fontFamily: 'Inter, system-ui, sans-serif', padding: 32 }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: COLORS.text, margin: 0 }}>OBE / CO-PO Mapping Studio</h1>
          <p style={{ color: COLORS.muted, marginTop: 6, fontSize: 14 }}>E20 — B.Tech CSE &bull; AY 2025–26 &bull; Outcome-Based Education Compliance</p>
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
            {/* Legend */}
            <div style={{ display: 'flex', gap: 16, marginBottom: 18, alignItems: 'center' }}>
              <span style={{ fontSize: 12, color: COLORS.muted }}>Mapping Strength:</span>
              {[
                { label: 'H — High (3)', bg: COLORS.teal, color: '#fff' },
                { label: 'M — Medium (2)', bg: COLORS.amber + '40', color: COLORS.amber },
                { label: 'L — Low (1)', bg: COLORS.purple + '22', color: COLORS.purple },
                { label: 'No Mapping', bg: COLORS.surface, color: COLORS.muted },
              ].map(l => (
                <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <div style={{ width: 26, height: 18, borderRadius: 3, background: l.bg, border: `1px solid ${COLORS.border}` }} />
                  <span style={{ fontSize: 12, color: COLORS.muted }}>{l.label}</span>
                </div>
              ))}
            </div>

            <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 900 }}>
                <thead>
                  <tr style={{ background: COLORS.surface }}>
                    <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: 12, color: COLORS.muted, borderBottom: `1px solid ${COLORS.border}`, borderRight: `1px solid ${COLORS.border}`, minWidth: 200 }}>
                      Course Outcome
                    </th>
                    {PROGRAM_OUTCOMES.map(po => (
                      <th key={po} style={{ padding: '10px 8px', textAlign: 'center', fontSize: 12, color: COLORS.muted, borderBottom: `1px solid ${COLORS.border}`, borderRight: `1px solid ${COLORS.border}20`, minWidth: 52 }}>
                        {po}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {COURSE_OUTCOMES.map((co, ri) => (
                    <tr key={co.code} style={{ background: ri % 2 === 0 ? 'transparent' : COLORS.surface + '55' }}>
                      <td style={{ padding: '10px 16px', borderRight: `1px solid ${COLORS.border}`, borderBottom: `1px solid ${COLORS.border}20` }}>
                        <span style={{ fontWeight: 700, color: COLORS.teal, fontSize: 13 }}>{co.code}</span>
                        <div style={{ fontSize: 11, color: COLORS.muted, marginTop: 2, maxWidth: 200, lineHeight: 1.4 }}>{co.description}</div>
                      </td>
                      {PROGRAM_OUTCOMES.map(po => {
                        const val = MAPPING[co.code][po];
                        const cs = cellStyle(val);
                        return (
                          <td key={po} style={{ padding: 4, textAlign: 'center', borderRight: `1px solid ${COLORS.border}20`, borderBottom: `1px solid ${COLORS.border}20` }}>
                            <div style={{
                              width: 36,
                              height: 28,
                              margin: '0 auto',
                              borderRadius: 4,
                              background: cs.background,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: 11,
                              fontWeight: 700,
                              color: cs.color,
                            }}>{cs.label}</div>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                  {/* Average row */}
                  <tr style={{ background: COLORS.surface }}>
                    <td style={{ padding: '10px 16px', borderRight: `1px solid ${COLORS.border}`, fontSize: 12, fontWeight: 700, color: COLORS.text }}>
                      Avg. PO Mapping
                    </td>
                    {PROGRAM_OUTCOMES.map(po => {
                      const avg = avgForPO(po);
                      return (
                        <td key={po} style={{ padding: 4, textAlign: 'center', borderRight: `1px solid ${COLORS.border}20` }}>
                          <div style={{ fontSize: 12, fontWeight: 700, color: avg >= 2.5 ? COLORS.teal : avg >= 1.5 ? COLORS.amber : avg > 0 ? COLORS.purple : COLORS.muted }}>
                            {avg > 0 ? avg.toFixed(1) : '—'}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 2 — Attainment Report */}
        {activeTab === 'attainment' && (
          <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 28 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 22 }}>
              <div>
                <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>PO-Level Attainment</h3>
                <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 4 }}>Target: 70% &bull; AY 2025–26</div>
              </div>
              <div style={{ display: 'flex', gap: 14, fontSize: 13 }}>
                <span style={{ color: COLORS.teal }}>&#9646; Met target ({ATTAINMENT.filter(a => a.met).length})</span>
                <span style={{ color: COLORS.red }}>&#9646; Below target ({ATTAINMENT.filter(a => !a.met).length})</span>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {ATTAINMENT.map(a => (
                <div key={a.po}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                    <span style={{ fontWeight: 600, fontSize: 14 }}>{a.po}</span>
                    <div style={{ display: 'flex', gap: 12, alignItems: 'center', fontSize: 13 }}>
                      <span style={{ color: COLORS.muted }}>Target: {a.target}%</span>
                      <span style={{ fontWeight: 700, color: a.met ? COLORS.teal : COLORS.red }}>{a.attainment.toFixed(1)}%</span>
                    </div>
                  </div>
                  <div style={{ position: 'relative', height: 16, background: COLORS.surface, borderRadius: 99 }}>
                    <div style={{
                      width: `${Math.min(a.attainment, 100)}%`,
                      height: '100%',
                      background: a.met ? COLORS.teal : COLORS.red,
                      borderRadius: 99,
                      transition: 'width 0.4s',
                    }} />
                    {/* Target line */}
                    <div style={{
                      position: 'absolute',
                      left: `${a.target}%`,
                      top: -3,
                      bottom: -3,
                      width: 2,
                      background: COLORS.amber,
                      borderRadius: 2,
                    }} />
                  </div>
                </div>
              ))}
            </div>

            <div style={{ marginTop: 20, fontSize: 12, color: COLORS.muted, fontStyle: 'italic' }}>
              Orange line indicates target threshold (70%). Bars extend to actual attainment %.
            </div>
          </div>
        )}

        {/* Tab 3 — Gap Analysis */}
        {activeTab === 'gaps' && (
          <div>
            <div style={{
              background: COLORS.red + '12',
              border: `1px solid ${COLORS.red}33`,
              borderRadius: 8,
              padding: '12px 18px',
              marginBottom: 20,
              fontSize: 14,
              color: COLORS.red,
              fontWeight: 600,
            }}>
              {gapPOs.length} Program Outcomes are below the 70% attainment target and require intervention.
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {gapPOs.map(a => {
                const gap = a.target - a.attainment;
                return (
                  <div key={a.po} style={{
                    background: COLORS.card,
                    border: `1px solid ${COLORS.border}`,
                    borderLeft: `4px solid ${COLORS.red}`,
                    borderRadius: 10,
                    padding: 20,
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                      <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
                        <span style={{ fontWeight: 800, fontSize: 18, color: COLORS.red }}>{a.po}</span>
                        <span style={{
                          background: COLORS.red + '22',
                          color: COLORS.red,
                          border: `1px solid ${COLORS.red}44`,
                          borderRadius: 6,
                          padding: '2px 10px',
                          fontSize: 11,
                          fontWeight: 700,
                        }}>GAP: -{gap.toFixed(1)}%</span>
                      </div>
                      <div style={{ textAlign: 'right', fontSize: 13, color: COLORS.muted }}>
                        <div>Attainment: <span style={{ color: COLORS.red, fontWeight: 700 }}>{a.attainment.toFixed(1)}%</span></div>
                        <div>Target: <span style={{ color: COLORS.text }}>{a.target}%</span></div>
                      </div>
                    </div>

                    {/* Gap bar */}
                    <div style={{ position: 'relative', height: 10, background: COLORS.surface, borderRadius: 99, marginBottom: 12 }}>
                      <div style={{ width: `${a.attainment}%`, height: '100%', background: COLORS.red + '88', borderRadius: 99 }} />
                      <div style={{
                        position: 'absolute',
                        left: `${a.attainment}%`,
                        width: `${gap}%`,
                        height: '100%',
                        background: COLORS.red + '33',
                        borderRadius: '0 99px 99px 0',
                        borderRight: `2px dashed ${COLORS.red}`,
                      }} />
                    </div>

                    <div style={{ fontSize: 13, color: COLORS.muted }}>
                      <strong style={{ color: COLORS.amber }}>Recommended Action: </strong>
                      <span>{GAP_ACTIONS[a.po] ?? 'Review CO-PO mapping and assessment alignment for this outcome.'}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Tab 4 — NBA Export */}
        {activeTab === 'export' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 28 }}>
              <div style={{ marginBottom: 24 }}>
                <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>NBA OBE Report</h3>
                <div style={{ color: COLORS.muted, fontSize: 14, marginTop: 6 }}>B.Tech CSE &bull; AY 2025–26 &bull; Accreditation Cycle 3</div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {[
                  { label: 'Download CO-PO Matrix', subtitle: 'Mapping matrix with H/M/L strength values', format: 'CSV', color: COLORS.teal },
                  { label: 'Download Attainment Report', subtitle: 'PO-level attainment data with target comparison', format: 'PDF', color: COLORS.purple },
                  { label: 'Download NBA Exhibit 2.6', subtitle: 'Formatted NBA Tier-1 submission document', format: 'DOCX', color: COLORS.amber },
                ].map(item => (
                  <div key={item.label} style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    background: COLORS.surface,
                    border: `1px solid ${COLORS.border}`,
                    borderRadius: 8,
                    padding: '16px 20px',
                  }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 15 }}>{item.label}</div>
                      <div style={{ fontSize: 13, color: COLORS.muted, marginTop: 3 }}>{item.subtitle}</div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <span style={{
                        background: item.color + '22',
                        color: item.color,
                        border: `1px solid ${item.color}44`,
                        borderRadius: 4,
                        padding: '2px 8px',
                        fontSize: 11,
                        fontWeight: 700,
                      }}>{item.format}</span>
                      <button style={{
                        background: item.color,
                        color: '#fff',
                        border: 'none',
                        borderRadius: 6,
                        padding: '8px 18px',
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}>{item.label}</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div style={{
              background: COLORS.surface,
              border: `1px solid ${COLORS.border}`,
              borderRadius: 8,
              padding: 16,
              fontSize: 13,
              color: COLORS.muted,
            }}>
              <strong style={{ color: COLORS.text }}>Note:</strong> All exports are generated from the current CO-PO mapping and attainment data. Ensure attainment calculation is complete before submitting to NBA. Last updated: 19 Mar 2026.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
