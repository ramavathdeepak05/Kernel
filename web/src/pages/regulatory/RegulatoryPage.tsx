/**
 * RegulatoryPage — E14 Regulatory & Accreditation
 * Route: /regulatory
 *
 * 4-up stats: NAAC score, NIRF rank estimate, compliance items, pending evidence
 * NAAC criteria tabs (C1–C7) with progress bars + evidence count
 * NIRF parameter breakdown (TLR, RPC, GO, OI, PERCEPTION) with fill bars
 * Evidence upload modal placeholder
 */

import { useState } from 'react';

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

const NAAC_CRITERIA = [
  { code: 'C1', name: 'Curricular Aspects', score: 3.45, evidence: 12, pct: 85 },
  { code: 'C2', name: 'Teaching-Learning', score: 3.28, evidence: 24, pct: 78 },
  { code: 'C3', name: 'Research & Innovation', score: 3.12, evidence: 18, pct: 72 },
  { code: 'C4', name: 'Infrastructure', score: 3.67, evidence: 8, pct: 91 },
  { code: 'C5', name: 'Student Support', score: 3.01, evidence: 16, pct: 68 },
  { code: 'C6', name: 'Governance', score: 3.44, evidence: 10, pct: 82 },
  { code: 'C7', name: 'Institutional Values', score: 3.18, evidence: 6, pct: 74 },
];

const NIRF_PARAMS = [
  { key: 'TLR', label: 'Teaching, Learning & Resources', score: 78.4, delta: +2.1, up: true },
  { key: 'RPC', label: 'Research & Professional Practice', score: 62.1, delta: -1.3, up: false },
  { key: 'GO', label: 'Graduation Outcomes', score: 85.2, delta: +3.4, up: true },
  { key: 'OI', label: 'Outreach & Inclusivity', score: 71.3, delta: +0.8, up: true },
  { key: 'PERCEPTION', label: 'Peer Perception', score: 45.8, delta: -4.2, up: false },
];

const COMPLIANCE_ITEMS = [
  { id: 'c1', name: 'UGC Affiliation Renewal', status: 'SUBMITTED', due: '2026-06-30', officer: 'Registrar' },
  { id: 'c2', name: 'NBA Accreditation (CSE)', status: 'IN_PROGRESS', due: '2026-09-15', officer: 'HOD-CSE' },
  { id: 'c3', name: 'NAAC AQAR 2024-25', status: 'DRAFT', due: '2026-04-30', officer: 'IQAC Coordinator' },
  { id: 'c4', name: 'Fire Safety NOC', status: 'VALID', due: '2027-01-15', officer: 'Estate Manager' },
  { id: 'c5', name: 'AICTE Extension of Approval', status: 'SUBMITTED', due: '2026-07-31', officer: 'Principal' },
  { id: 'c6', name: 'Environmental Compliance Cert', status: 'IN_PROGRESS', due: '2026-05-31', officer: 'Admin Officer' },
  { id: 'c7', name: 'Hostel NOC (State Govt)', status: 'PENDING', due: '2026-04-15', officer: 'Dean Students' },
  { id: 'c8', name: 'Grievance Committee Disclosure', status: 'VALID', due: '2026-12-31', officer: 'IQAC Coordinator' },
  { id: 'c9', name: 'Anti-Ragging Committee Report', status: 'SUBMITTED', due: '2026-04-01', officer: 'Proctor' },
  { id: 'c10', name: 'SC/ST Committee Annual Report', status: 'DRAFT', due: '2026-04-30', officer: 'Liaison Officer' },
  { id: 'c11', name: 'RTI Disclosure Update', status: 'VALID', due: '2026-06-01', officer: 'Registrar' },
  { id: 'c12', name: 'Annual Accounts Audit', status: 'IN_PROGRESS', due: '2026-09-30', officer: 'Finance Controller' },
  { id: 'c13', name: 'Mandatory Disclosure (AICTE)', status: 'SUBMITTED', due: '2026-06-30', officer: 'Principal' },
  { id: 'c14', name: 'Intellectual Property Cell Report', status: 'PENDING', due: '2026-05-15', officer: 'IPR Coordinator' },
];

function criteriaColor(score: number): string {
  if (score > 3.5) return COLORS.teal;
  if (score > 3.0) return COLORS.amber;
  return COLORS.red;
}

function statusIcon(status: string): string {
  switch (status) {
    case 'SUBMITTED':
    case 'VALID': return '✅';
    case 'IN_PROGRESS': return '🔄';
    case 'DRAFT': return '⚠';
    case 'PENDING': return '⏳';
    default: return '—';
  }
}

function statusColor(status: string): string {
  switch (status) {
    case 'SUBMITTED':
    case 'VALID': return COLORS.teal;
    case 'IN_PROGRESS': return COLORS.purple;
    case 'DRAFT': return COLORS.amber;
    case 'PENDING': return COLORS.red;
    default: return COLORS.muted;
  }
}

export function RegulatoryPage() {
  const [activeTab, setActiveTab] = useState<'naac' | 'nirf' | 'compliance'>('naac');
  const [showModal, setShowModal] = useState(false);

  const tabs = [
    { key: 'naac', label: 'NAAC Criteria' },
    { key: 'nirf', label: 'NIRF Parameters' },
    { key: 'compliance', label: 'Compliance Tracker' },
  ] as const;

  return (
    <div style={{ minHeight: '100vh', background: COLORS.bg, color: COLORS.text, fontFamily: 'Inter, system-ui, sans-serif', padding: '24px' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, color: COLORS.text }}>Regulatory & Accreditation</h1>
        <p style={{ margin: '4px 0 0', color: COLORS.muted, fontSize: 13 }}>E14 — NAAC, NIRF & Statutory Compliance Dashboard</p>
      </div>

      {/* Stats Strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: 'NAAC Score', value: '3.21 / 4.0', sub: 'Grade A+', accent: COLORS.teal },
          { label: 'NIRF Rank Est.', value: '~87', sub: 'Engineering Category', accent: COLORS.purple },
          { label: 'Compliance Items', value: '14 / 18', sub: 'Complete', accent: COLORS.amber },
          { label: 'Pending Evidence', value: '6', sub: 'Requires Upload', accent: COLORS.red },
        ].map((s) => (
          <div key={s.label} style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: '16px 20px' }}>
            <p style={{ margin: 0, fontSize: 12, color: COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{s.label}</p>
            <p style={{ margin: '8px 0 2px', fontSize: 26, fontWeight: 700, color: s.accent }}>{s.value}</p>
            <p style={{ margin: 0, fontSize: 12, color: COLORS.muted }}>{s.sub}</p>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, background: COLORS.surface, borderRadius: 8, padding: 4, width: 'fit-content' }}>
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            style={{
              padding: '7px 18px',
              borderRadius: 6,
              border: 'none',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 500,
              background: activeTab === t.key ? COLORS.purple : 'transparent',
              color: activeTab === t.key ? '#fff' : COLORS.muted,
              transition: 'all 0.15s',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab 1: NAAC Criteria */}
      {activeTab === 'naac' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {NAAC_CRITERIA.map((c) => {
            const color = criteriaColor(c.score);
            return (
              <div key={c.code} style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                  <div>
                    <span style={{ fontSize: 11, fontWeight: 700, color: COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{c.code}</span>
                    <p style={{ margin: '2px 0 0', fontSize: 14, fontWeight: 600, color: COLORS.text }}>{c.name}</p>
                  </div>
                  <span style={{ background: `${color}22`, color, fontSize: 11, fontWeight: 700, padding: '3px 8px', borderRadius: 20, whiteSpace: 'nowrap' }}>
                    {c.evidence} evidence
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 10 }}>
                  <span style={{ fontSize: 28, fontWeight: 700, color }}>{c.score}</span>
                  <span style={{ fontSize: 13, color: COLORS.muted }}>/ 4.0</span>
                </div>

                {/* Progress bar */}
                <div style={{ height: 6, background: COLORS.border, borderRadius: 3, marginBottom: 14 }}>
                  <div style={{ height: '100%', width: `${c.pct}%`, background: color, borderRadius: 3, transition: 'width 0.3s' }} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
                  <span style={{ fontSize: 12, color: COLORS.muted }}>Completion</span>
                  <span style={{ fontSize: 12, fontWeight: 600, color }}>{c.pct}%</span>
                </div>

                <button style={{ width: '100%', padding: '8px 0', background: 'transparent', border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.muted, fontSize: 13, cursor: 'pointer' }}>
                  View Evidence
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Tab 2: NIRF Parameters */}
      {activeTab === 'nirf' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {NIRF_PARAMS.map((p) => (
            <div key={p.key} style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: '18px 22px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, background: COLORS.purple + '33', color: COLORS.purple, padding: '3px 8px', borderRadius: 4 }}>{p.key}</span>
                  <span style={{ fontSize: 14, color: COLORS.text }}>{p.label}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{
                    fontSize: 12, fontWeight: 600,
                    color: p.up ? COLORS.teal : COLORS.red,
                    background: (p.up ? COLORS.teal : COLORS.red) + '22',
                    padding: '2px 8px', borderRadius: 12,
                  }}>
                    {p.up ? '▲' : '▼'} {Math.abs(p.delta)}
                  </span>
                  <span style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, minWidth: 60, textAlign: 'right' }}>{p.score}</span>
                  <span style={{ fontSize: 13, color: COLORS.muted }}>/100</span>
                </div>
              </div>
              {/* Fill bar */}
              <div style={{ height: 8, background: COLORS.border, borderRadius: 4 }}>
                <div style={{
                  height: '100%',
                  width: `${p.score}%`,
                  background: p.score >= 75 ? COLORS.teal : p.score >= 60 ? COLORS.amber : COLORS.red,
                  borderRadius: 4,
                  transition: 'width 0.4s ease',
                }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Tab 3: Compliance Tracker */}
      {activeTab === 'compliance' && (
        <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: `1px solid ${COLORS.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 600, fontSize: 14, color: COLORS.text }}>Compliance Items ({COMPLIANCE_ITEMS.length})</span>
            <span style={{ fontSize: 12, color: COLORS.muted }}>14 / 18 complete</span>
          </div>
          <div style={{ maxHeight: 480, overflowY: 'auto' }}>
            {COMPLIANCE_ITEMS.map((item, idx) => (
              <div key={item.id} style={{
                padding: '14px 20px',
                borderBottom: idx < COMPLIANCE_ITEMS.length - 1 ? `1px solid ${COLORS.border}` : 'none',
                display: 'grid',
                gridTemplateColumns: '1fr auto auto auto',
                gap: 16,
                alignItems: 'center',
              }}>
                <div>
                  <span style={{ fontSize: 14, color: COLORS.text }}>{statusIcon(item.status)} {item.name}</span>
                </div>
                <span style={{
                  fontSize: 11, fontWeight: 600,
                  color: statusColor(item.status),
                  background: statusColor(item.status) + '22',
                  padding: '3px 8px', borderRadius: 10, whiteSpace: 'nowrap',
                }}>
                  {item.status.replace('_', ' ')}
                </span>
                <span style={{ fontSize: 12, color: COLORS.muted, whiteSpace: 'nowrap' }}>Due: {item.due}</span>
                <span style={{ fontSize: 12, color: COLORS.muted, whiteSpace: 'nowrap' }}>{item.officer}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Floating Upload Button */}
      <button
        onClick={() => setShowModal(true)}
        style={{
          position: 'fixed',
          bottom: 32,
          right: 32,
          background: COLORS.teal,
          color: '#fff',
          border: 'none',
          borderRadius: 40,
          padding: '12px 22px',
          fontSize: 14,
          fontWeight: 600,
          cursor: 'pointer',
          boxShadow: `0 4px 20px ${COLORS.teal}55`,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        + Upload Evidence
      </button>

      {/* Modal Overlay */}
      {showModal && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
          }}
          onClick={() => setShowModal(false)}
        >
          <div
            style={{
              background: COLORS.card, border: `1px solid ${COLORS.border}`,
              borderRadius: 12, padding: 28, width: 420,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: COLORS.text }}>Upload Evidence</h3>
              <button onClick={() => setShowModal(false)} style={{ background: 'none', border: 'none', color: COLORS.muted, fontSize: 20, cursor: 'pointer', lineHeight: 1 }}>×</button>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 12, color: COLORS.muted, display: 'block', marginBottom: 6 }}>Criterion / Category</label>
              <select style={{ width: '100%', padding: '9px 12px', background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 13 }}>
                {NAAC_CRITERIA.map((c) => <option key={c.code}>{c.code} — {c.name}</option>)}
              </select>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 12, color: COLORS.muted, display: 'block', marginBottom: 6 }}>Evidence File</label>
              <div style={{ border: `2px dashed ${COLORS.border}`, borderRadius: 8, padding: '28px 0', textAlign: 'center', color: COLORS.muted, fontSize: 13 }}>
                <input type="file" style={{ display: 'none' }} id="evidence-file" />
                <label htmlFor="evidence-file" style={{ cursor: 'pointer', color: COLORS.purple }}>Click to select file</label>
                <span> or drag & drop</span>
              </div>
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={{ fontSize: 12, color: COLORS.muted, display: 'block', marginBottom: 6 }}>Description</label>
              <textarea rows={3} style={{ width: '100%', padding: '9px 12px', background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 6, color: COLORS.text, fontSize: 13, resize: 'vertical', boxSizing: 'border-box' }} placeholder="Brief description of this evidence..." />
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button style={{ flex: 1, padding: '10px 0', background: COLORS.teal, border: 'none', borderRadius: 7, color: '#fff', fontWeight: 600, fontSize: 14, cursor: 'pointer' }}>
                Upload
              </button>
              <button onClick={() => setShowModal(false)} style={{ flex: 1, padding: '10px 0', background: 'transparent', border: `1px solid ${COLORS.border}`, borderRadius: 7, color: COLORS.muted, fontSize: 14, cursor: 'pointer' }}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
