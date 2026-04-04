/**
 * RegulatoryPage — E14 Regulatory & Accreditation
 * Route: /regulatory
 *
 * 4-up stats: NAAC score, NIRF rank estimate, compliance items, pending evidence
 * NAAC criteria tabs (C1–C7) with progress bars + evidence count
 * NIRF parameter breakdown (TLR, RPC, GO, OI, PERCEPTION) with fill bars
 * Evidence upload modal placeholder
 */

import { useState, useEffect } from 'react';
import { ALISTabs, ALISTabsList, ALISTabsTrigger, ALISTabsContent } from '@/components/ui/alis-tabs';

// ── Types ──────────────────────────────────────────────────────────────────

interface NaacCriterion {
  code: string;
  name: string;
  score: number;
  evidence: number;
  pct: number;
}

interface NirfParam {
  key: string;
  label: string;
  score: number;
  delta: number;
  up: boolean;
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

const CRITERION_NAMES: Record<string, string> = {
  criterion_1: 'Curricular Aspects',
  criterion_2: 'Teaching-Learning',
  criterion_3: 'Research & Innovation',
  criterion_4: 'Infrastructure',
  criterion_5: 'Student Support',
  criterion_6: 'Governance',
  criterion_7: 'Institutional Values',
};

const NIRF_LABELS: Record<string, string> = {
  TLR: 'Teaching, Learning & Resources',
  RPC: 'Research & Professional Practice',
  GO: 'Graduation Outcomes',
  OI: 'Outreach & Inclusivity',
  PERCEPTION: 'Peer Perception',
};

// Static compliance items — no dedicated API endpoint exists for this
const COMPLIANCE_ITEMS = [
  { id: 'c1',  name: 'UGC Affiliation Renewal',        status: 'SUBMITTED',   due: '2026-06-30', officer: 'Registrar' },
  { id: 'c2',  name: 'NBA Accreditation (CSE)',         status: 'IN_PROGRESS', due: '2026-09-15', officer: 'HOD-CSE' },
  { id: 'c3',  name: 'NAAC AQAR 2024-25',              status: 'DRAFT',       due: '2026-04-30', officer: 'IQAC Coordinator' },
  { id: 'c4',  name: 'Fire Safety NOC',                 status: 'VALID',       due: '2027-01-15', officer: 'Estate Manager' },
  { id: 'c5',  name: 'AICTE Extension of Approval',    status: 'SUBMITTED',   due: '2026-07-31', officer: 'Principal' },
  { id: 'c6',  name: 'Environmental Compliance Cert',   status: 'IN_PROGRESS', due: '2026-05-31', officer: 'Admin Officer' },
  { id: 'c7',  name: 'Hostel NOC (State Govt)',         status: 'PENDING',     due: '2026-04-15', officer: 'Dean Students' },
  { id: 'c8',  name: 'Grievance Committee Disclosure',  status: 'VALID',       due: '2026-12-31', officer: 'IQAC Coordinator' },
  { id: 'c9',  name: 'Anti-Ragging Committee Report',   status: 'SUBMITTED',   due: '2026-04-01', officer: 'Proctor' },
  { id: 'c10', name: 'SC/ST Committee Annual Report',   status: 'DRAFT',       due: '2026-04-30', officer: 'Liaison Officer' },
  { id: 'c11', name: 'RTI Disclosure Update',           status: 'VALID',       due: '2026-06-01', officer: 'Registrar' },
  { id: 'c12', name: 'Annual Accounts Audit',           status: 'IN_PROGRESS', due: '2026-09-30', officer: 'Finance Controller' },
  { id: 'c13', name: 'Mandatory Disclosure (AICTE)',    status: 'SUBMITTED',   due: '2026-06-30', officer: 'Principal' },
  { id: 'c14', name: 'Intellectual Property Cell Report',status: 'PENDING',    due: '2026-05-15', officer: 'IPR Coordinator' },
];

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

// ── Helpers ────────────────────────────────────────────────────────────────

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

// Parse NAAC dashboard API response into NaacCriterion array
function parseNaacCriteria(data: Record<string, Record<string, { value?: number | null }>>): NaacCriterion[] {
  return Array.from({ length: 7 }, (_, i) => {
    const key = `criterion_${i + 1}`;
    const metrics = data[key] ?? {};
    const score = metrics['score']?.value ?? metrics['naac_score']?.value ?? 0;
    const evidence = Math.round(metrics['evidence_count']?.value ?? metrics['evidence']?.value ?? 0);
    const pct = Math.round(metrics['completion_pct']?.value ?? metrics['completion']?.value ?? (score / 4) * 100);
    return {
      code: `C${i + 1}`,
      name: CRITERION_NAMES[key] ?? key,
      score: Number(score.toFixed(2)),
      evidence,
      pct: Math.min(100, pct),
    };
  });
}

// Parse NIRF API response into NirfParam array
function parseNirfParams(data: Record<string, unknown>): NirfParam[] {
  const paramMap = data.params as Record<string, unknown> | undefined ?? data as Record<string, unknown>;
  return Object.entries(NIRF_LABELS).map(([key, label]) => {
    const raw = paramMap[key] as Record<string, number> | number | undefined;
    const score = typeof raw === 'number' ? raw : (raw as Record<string, number> | undefined)?.score ?? 0;
    const prev = typeof raw === 'number' ? raw : (raw as Record<string, number> | undefined)?.prev_score ?? score;
    const delta = Number((score - prev).toFixed(1));
    return { key, label, score: Number(score.toFixed(1)), delta, up: delta >= 0 };
  });
}

// ── Component ──────────────────────────────────────────────────────────────

export function RegulatoryPage() {
  const [showModal, setShowModal] = useState(false);

  const [naacCriteria, setNaacCriteria] = useState<NaacCriterion[]>([]);
  const [nirfParams, setNirfParams] = useState<NirfParam[]>([]);
  const [loading, setLoading] = useState(true);

  const currentYear = new Date().getFullYear();
  const academicYear = `${currentYear - 1}-${String(currentYear).slice(-2)}`;

  useEffect(() => {
    Promise.all([
      apiFetch<{ criteria: Record<string, Record<string, { value?: number | null }>> }>('/regulatory/naac/dashboard'),
      apiFetch<Record<string, unknown>>(`/regulatory/nirf/${currentYear}`),
    ]).then(([naac, nirf]) => {
      if (naac?.criteria) {
        setNaacCriteria(parseNaacCriteria(naac.criteria));
      }
      if (nirf) {
        const parsed = parseNirfParams(nirf);
        if (parsed.some(p => p.score > 0)) setNirfParams(parsed);
      }
      setLoading(false);
    });
  }, [currentYear]);

  // Computed stats from live data (fall back to compliance item counts)
  const avgNaacScore = naacCriteria.length > 0
    ? (naacCriteria.reduce((s, c) => s + c.score, 0) / naacCriteria.length).toFixed(2)
    : '—';
  const totalEvidence = naacCriteria.reduce((s, c) => s + c.evidence, 0);
  const completeItems = COMPLIANCE_ITEMS.filter(c => c.status === 'SUBMITTED' || c.status === 'VALID').length;

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
          { label: 'NAAC Score',       value: naacCriteria.length > 0 ? `${avgNaacScore} / 4.0` : '—',  sub: 'Avg across 7 criteria',  accent: COLORS.teal   },
          { label: 'NIRF Rank Est.',   value: nirfParams.length > 0 ? '~87' : '—',                       sub: 'Engineering Category',   accent: COLORS.purple },
          { label: 'Compliance Items', value: `${completeItems} / ${COMPLIANCE_ITEMS.length}`,             sub: 'Complete',               accent: COLORS.amber  },
          { label: 'Total Evidence',   value: totalEvidence > 0 ? String(totalEvidence) : '—',            sub: 'NAAC documents uploaded', accent: COLORS.red    },
        ].map((s) => (
          <div key={s.label} style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: '16px 20px' }}>
            <p style={{ margin: 0, fontSize: 12, color: COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{s.label}</p>
            <p style={{ margin: '8px 0 2px', fontSize: 26, fontWeight: 700, color: s.accent }}>{s.value}</p>
            <p style={{ margin: 0, fontSize: 12, color: COLORS.muted }}>{s.sub}</p>
          </div>
        ))}
      </div>

      <ALISTabs defaultValue="naac">
        <ALISTabsList>
          {tabs.map((t) => (
            <ALISTabsTrigger key={t.key} value={t.key}>{t.label}</ALISTabsTrigger>
          ))}
        </ALISTabsList>

      {/* Tab 1: NAAC Criteria */}
      <ALISTabsContent value="naac">
      {loading ? (
          <p style={{ color: COLORS.muted, fontSize: 13 }}>Loading NAAC data…</p>
        ) : naacCriteria.length === 0 ? (
          <p style={{ color: COLORS.muted, fontSize: 13 }}>No NAAC metrics available. Ensure the regulatory feature flag is enabled and metrics have been recorded.</p>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
            {naacCriteria.map((c) => {
              const color = criteriaColor(c.score);
              return (
                <div key={c.code} style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                    <div>
                      <span style={{ fontSize: 11, fontWeight: 700, color: COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{c.code}</span>
                      <p style={{ margin: '2px 0 0', fontSize: 14, fontWeight: 600, color: COLORS.text }}>{c.name}</p>
                    </div>
                    {c.evidence > 0 && (
                      <span style={{ background: `${color}22`, color, fontSize: 11, fontWeight: 700, padding: '3px 8px', borderRadius: 20, whiteSpace: 'nowrap' }}>
                        {c.evidence} evidence
                      </span>
                    )}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 10 }}>
                    <span style={{ fontSize: 28, fontWeight: 700, color }}>{c.score > 0 ? c.score : '—'}</span>
                    {c.score > 0 && <span style={{ fontSize: 13, color: COLORS.muted }}>/ 4.0</span>}
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
        )
      }
      </ALISTabsContent>

      <ALISTabsContent value="nirf">
      {
        loading ? (
          <p style={{ color: COLORS.muted, fontSize: 13 }}>Loading NIRF data…</p>
        ) : nirfParams.length === 0 ? (
          <p style={{ color: COLORS.muted, fontSize: 13 }}>No NIRF submission found for {currentYear}. Use the compute endpoint to generate NIRF data.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {nirfParams.map((p) => (
              <div key={p.key} style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: '18px 22px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, background: COLORS.purple + '33', color: COLORS.purple, padding: '3px 8px', borderRadius: 4 }}>{p.key}</span>
                    <span style={{ fontSize: 14, color: COLORS.text }}>{p.label}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    {p.delta !== 0 && (
                      <span style={{
                        fontSize: 12, fontWeight: 600,
                        color: p.up ? COLORS.teal : COLORS.red,
                        background: (p.up ? COLORS.teal : COLORS.red) + '22',
                        padding: '2px 8px', borderRadius: 12,
                      }}>
                        {p.up ? '▲' : '▼'} {Math.abs(p.delta)}
                      </span>
                    )}
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
        )
      }
      </ALISTabsContent>

      <ALISTabsContent value="compliance">
      {(
        <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: `1px solid ${COLORS.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 600, fontSize: 14, color: COLORS.text }}>Compliance Items ({COMPLIANCE_ITEMS.length})</span>
            <span style={{ fontSize: 12, color: COLORS.muted }}>{completeItems} / {COMPLIANCE_ITEMS.length} complete</span>
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
      </ALISTabsContent>
      </ALISTabs>

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
                {Array.from({ length: 7 }, (_, i) => (
                  <option key={i + 1}>C{i + 1} — {CRITERION_NAMES[`criterion_${i + 1}`]}</option>
                ))}
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
