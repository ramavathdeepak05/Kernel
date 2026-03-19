/**
 * PolicyStudioPage — Admin Console / Policy Studio
 * Route: /settings (or /admin/policies)
 *
 * 3-panel layout: Categories (left 200px) | Policy List (centre) | Policy Editor (right 320px)
 * Current policy value + version history
 * Edit form: value + justification
 * "Draft with AI" button placeholder
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

const POLICY_CATEGORIES = [
  { key: 'admissions', label: 'Admissions', count: 12 },
  { key: 'academics', label: 'Academics', count: 8 },
  { key: 'finance', label: 'Finance', count: 15 },
  { key: 'examinations', label: 'Examinations', count: 6 },
  { key: 'phd', label: 'PhD & Research', count: 4 },
  { key: 'obe', label: 'OBE / CO-PO', count: 3 },
  { key: 'convocation', label: 'Convocation', count: 3 },
  { key: 'platform', label: 'Platform', count: 5 },
];

type Policy = {
  key: string;
  type: string;
  value: string;
  description: string;
  version: number;
  status: string;
  category: string;
  updatedAt: string;
};

const POLICIES: Policy[] = [
  { key: 'admissions.readmission_max_gap_years', type: 'INTEGER', value: '5', description: 'Maximum gap years for re-admission', version: 2, status: 'APPROVED', category: 'admissions', updatedAt: '2026-03-01' },
  { key: 'admissions.credit_transfer_max_pct', type: 'DECIMAL', value: '50', description: 'Max % program credits transferable', version: 1, status: 'APPROVED', category: 'admissions', updatedAt: '2026-02-15' },
  { key: 'finance.einvoice_threshold_inr', type: 'DECIMAL', value: '500000', description: 'GST e-Invoice threshold (INR)', version: 1, status: 'APPROVED', category: 'finance', updatedAt: '2026-03-10' },
  { key: 'phd.supervisor_max_scholars', type: 'INTEGER', value: '8', description: 'Maximum PhD scholars per supervisor', version: 1, status: 'APPROVED', category: 'phd', updatedAt: '2026-03-15' },
  { key: 'phd.plagiarism_max_pct', type: 'DECIMAL', value: '25', description: 'Max plagiarism % for thesis submission', version: 1, status: 'APPROVED', category: 'phd', updatedAt: '2026-03-15' },
  { key: 'obe.attainment_threshold_pct', type: 'DECIMAL', value: '60', description: 'Min % students to attain CO', version: 1, status: 'APPROVED', category: 'obe', updatedAt: '2026-03-15' },
  { key: 'convocation.distinction_cgpa_threshold', type: 'DECIMAL', value: '8.5', description: 'Min CGPA for distinction', version: 1, status: 'APPROVED', category: 'convocation', updatedAt: '2026-03-15' },
  { key: 'academics.late_joiner_catchup_weeks', type: 'INTEGER', value: '3', description: 'Weeks for late joiner catch-up', version: 1, status: 'APPROVED', category: 'academics', updatedAt: '2026-01-20' },
  { key: 'examinations.rubber_stamp_threshold', type: 'DECIMAL', value: '0.95', description: 'Faculty override rate that triggers rubber stamp alert', version: 1, status: 'APPROVED', category: 'examinations', updatedAt: '2026-02-01' },
  { key: 'finance.scholarship_dispute_window_days', type: 'INTEGER', value: '30', description: 'Days student can dispute scholarship revocation', version: 1, status: 'APPROVED', category: 'finance', updatedAt: '2026-02-20' },
];

function typeColor(type: string): string {
  return type === 'INTEGER' ? COLORS.purple : COLORS.amber;
}

function buildVersionHistory(policy: Policy): { v: number; date: string; status: string }[] {
  const history = [];
  for (let i = policy.version; i >= 1; i--) {
    history.push({ v: i, date: policy.updatedAt, status: 'APPROVED' });
  }
  return history;
}

export function PolicyStudioPage() {
  const [selectedCategory, setSelectedCategory] = useState<string>('admissions');
  const [selectedPolicy, setSelectedPolicy] = useState<Policy | null>(null);
  const [editValue, setEditValue] = useState('');
  const [editJustification, setEditJustification] = useState('');
  const [showAIDraft, setShowAIDraft] = useState(false);
  const [aiDescription, setAiDescription] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiDraftResult, setAiDraftResult] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState(false);

  const filteredPolicies = POLICIES.filter((p) => p.category === selectedCategory);

  function handleSelectPolicy(p: Policy) {
    setSelectedPolicy(p);
    setEditValue(p.value);
    setEditJustification('');
    setShowAIDraft(false);
    setAiDraftResult(null);
    setSavedMsg(false);
  }

  function handleSave() {
    if (!selectedPolicy) return;
    setSavedMsg(true);
    setTimeout(() => setSavedMsg(false), 2500);
  }

  function handleGenerateDraft() {
    setAiLoading(true);
    setAiDraftResult(null);
    setTimeout(() => {
      setAiLoading(false);
      setAiDraftResult(
        `Based on your description, the suggested value is: ${selectedPolicy?.value ?? '—'}. ` +
        `AI rationale: Policy aligns with UGC guidelines and institutional precedent. ` +
        `Proposed effective date: 2026-04-01. Requires registrar approval.`
      );
    }, 1400);
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: COLORS.bg, color: COLORS.text, fontFamily: 'Inter, system-ui, sans-serif' }}>
      {/* Header */}
      <div style={{ padding: '20px 24px 16px', borderBottom: `1px solid ${COLORS.border}`, flexShrink: 0 }}>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Policy Studio</h1>
        <p style={{ margin: '3px 0 0', color: COLORS.muted, fontSize: 13 }}>View, version, and update system-wide operational policies</p>
      </div>

      {/* 3-column body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* LEFT: Category list — 200px */}
        <div style={{ width: 200, flexShrink: 0, borderRight: `1px solid ${COLORS.border}`, background: COLORS.surface, overflowY: 'auto', padding: '12px 0' }}>
          {POLICY_CATEGORIES.map((cat) => (
            <button
              key={cat.key}
              onClick={() => { setSelectedCategory(cat.key); setSelectedPolicy(null); }}
              style={{
                display: 'flex',
                width: '100%',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '9px 16px',
                border: 'none',
                background: selectedCategory === cat.key ? `${COLORS.purple}22` : 'transparent',
                borderLeft: selectedCategory === cat.key ? `3px solid ${COLORS.purple}` : '3px solid transparent',
                color: selectedCategory === cat.key ? COLORS.text : COLORS.muted,
                fontSize: 13,
                fontWeight: selectedCategory === cat.key ? 600 : 400,
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'all 0.12s',
              }}
            >
              <span>{cat.label}</span>
              <span style={{
                fontSize: 11, background: selectedCategory === cat.key ? COLORS.purple : COLORS.border,
                color: selectedCategory === cat.key ? '#fff' : COLORS.muted,
                borderRadius: 10, padding: '1px 7px', minWidth: 20, textAlign: 'center',
              }}>
                {cat.count}
              </span>
            </button>
          ))}
        </div>

        {/* CENTRE: Policy list */}
        <div style={{ flex: 1, overflowY: 'auto', background: COLORS.bg, padding: '16px 20px' }}>
          <p style={{ margin: '0 0 14px', fontSize: 12, color: COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
            {POLICY_CATEGORIES.find((c) => c.key === selectedCategory)?.label} — {filteredPolicies.length} policies
          </p>
          {filteredPolicies.length === 0 && (
            <p style={{ color: COLORS.muted, fontSize: 14 }}>No policies in this category.</p>
          )}
          {filteredPolicies.map((p) => (
            <div
              key={p.key}
              onClick={() => handleSelectPolicy(p)}
              style={{
                background: selectedPolicy?.key === p.key ? `${COLORS.purple}18` : COLORS.card,
                border: `1px solid ${selectedPolicy?.key === p.key ? COLORS.purple : COLORS.border}`,
                borderRadius: 8,
                padding: '13px 16px',
                marginBottom: 10,
                cursor: 'pointer',
                transition: 'all 0.12s',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <code style={{ fontSize: 12, color: COLORS.purple, fontFamily: 'monospace', wordBreak: 'break-all' }}>{p.key}</code>
                <span style={{ fontSize: 11, fontWeight: 700, color: typeColor(p.type), background: typeColor(p.type) + '22', padding: '2px 7px', borderRadius: 4, marginLeft: 8, whiteSpace: 'nowrap' }}>
                  {p.type}
                </span>
              </div>
              <p style={{ margin: '6px 0 4px', fontSize: 13, color: COLORS.text }}>{p.description}</p>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 12, color: COLORS.muted }}>Value: <strong style={{ color: COLORS.text }}>{p.value}</strong></span>
                <span style={{ fontSize: 11, color: COLORS.muted }}>v{p.version} · {p.updatedAt}</span>
              </div>
            </div>
          ))}
        </div>

        {/* RIGHT: Policy editor — 320px */}
        <div style={{ width: 320, flexShrink: 0, borderLeft: `1px solid ${COLORS.border}`, background: COLORS.surface, overflowY: 'auto', padding: 20 }}>
          {!selectedPolicy ? (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 8 }}>
              <span style={{ fontSize: 28 }}>⚙️</span>
              <p style={{ color: COLORS.muted, fontSize: 13, textAlign: 'center', margin: 0 }}>Select a policy to view and edit</p>
            </div>
          ) : (
            <div>
              {/* Policy key */}
              <code style={{ fontSize: 11, color: COLORS.purple, fontFamily: 'monospace', wordBreak: 'break-all', display: 'block', marginBottom: 10 }}>
                {selectedPolicy.key}
              </code>

              {/* Type + status badges */}
              <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: typeColor(selectedPolicy.type), background: typeColor(selectedPolicy.type) + '22', padding: '3px 8px', borderRadius: 4 }}>
                  {selectedPolicy.type}
                </span>
                <span style={{ fontSize: 11, fontWeight: 600, color: COLORS.teal, background: COLORS.teal + '22', padding: '3px 8px', borderRadius: 4 }}>
                  {selectedPolicy.status}
                </span>
              </div>

              <p style={{ fontSize: 12, color: COLORS.muted, margin: '0 0 16px' }}>{selectedPolicy.description}</p>

              {/* Current value */}
              <div style={{ marginBottom: 14 }}>
                <label style={{ fontSize: 12, color: COLORS.muted, display: 'block', marginBottom: 5 }}>Current Value</label>
                <input
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  style={{
                    width: '100%', padding: '10px 12px',
                    background: COLORS.card, border: `1px solid ${COLORS.border}`,
                    borderRadius: 7, color: COLORS.text, fontSize: 18, fontWeight: 700,
                    boxSizing: 'border-box', outline: 'none',
                  }}
                />
              </div>

              {/* Justification */}
              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 12, color: COLORS.muted, display: 'block', marginBottom: 5 }}>Change Justification</label>
                <textarea
                  rows={3}
                  value={editJustification}
                  onChange={(e) => setEditJustification(e.target.value)}
                  placeholder="Briefly explain why this value is changing..."
                  style={{
                    width: '100%', padding: '9px 12px',
                    background: COLORS.card, border: `1px solid ${COLORS.border}`,
                    borderRadius: 7, color: COLORS.text, fontSize: 13,
                    resize: 'vertical', boxSizing: 'border-box', outline: 'none',
                  }}
                />
              </div>

              {/* Version history */}
              <div style={{ marginBottom: 18 }}>
                <p style={{ fontSize: 12, color: COLORS.muted, margin: '0 0 8px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Version History</p>
                {buildVersionHistory(selectedPolicy).map((h) => (
                  <div key={h.v} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: `1px solid ${COLORS.border}` }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: COLORS.purple, minWidth: 24 }}>v{h.v}</span>
                    <span style={{ fontSize: 12, color: COLORS.muted }}>{h.date}</span>
                    <span style={{ fontSize: 11, color: COLORS.teal, marginLeft: 'auto' }}>{h.status}</span>
                  </div>
                ))}
              </div>

              {/* Action buttons */}
              <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                <button
                  onClick={handleSave}
                  style={{ flex: 1, padding: '9px 0', background: COLORS.teal, border: 'none', borderRadius: 7, color: '#fff', fontWeight: 600, fontSize: 13, cursor: 'pointer' }}
                >
                  {savedMsg ? '✓ Saved' : 'Save Changes'}
                </button>
                <button
                  onClick={() => { setShowAIDraft(!showAIDraft); setAiDraftResult(null); }}
                  style={{ flex: 1, padding: '9px 0', background: `${COLORS.purple}22`, border: `1px solid ${COLORS.purple}`, borderRadius: 7, color: COLORS.purple, fontWeight: 600, fontSize: 13, cursor: 'pointer' }}
                >
                  Draft with AI
                </button>
              </div>

              {/* AI Draft section */}
              {showAIDraft && (
                <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: 14 }}>
                  <p style={{ margin: '0 0 8px', fontSize: 12, color: COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>AI Policy Drafter</p>
                  <textarea
                    rows={3}
                    value={aiDescription}
                    onChange={(e) => setAiDescription(e.target.value)}
                    placeholder="Describe in plain English what you want to change and why..."
                    style={{
                      width: '100%', padding: '9px 12px',
                      background: COLORS.surface, border: `1px solid ${COLORS.border}`,
                      borderRadius: 6, color: COLORS.text, fontSize: 13,
                      resize: 'vertical', boxSizing: 'border-box', outline: 'none',
                      marginBottom: 10,
                    }}
                  />
                  <button
                    onClick={handleGenerateDraft}
                    disabled={aiLoading}
                    style={{
                      width: '100%', padding: '9px 0',
                      background: aiLoading ? COLORS.border : COLORS.purple,
                      border: 'none', borderRadius: 6,
                      color: aiLoading ? COLORS.muted : '#fff',
                      fontWeight: 600, fontSize: 13, cursor: aiLoading ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {aiLoading ? 'Generating…' : 'Generate Draft'}
                  </button>
                  {aiDraftResult && (
                    <div style={{ marginTop: 12, padding: 12, background: `${COLORS.teal}14`, border: `1px solid ${COLORS.teal}44`, borderRadius: 6 }}>
                      <p style={{ margin: 0, fontSize: 12, color: COLORS.teal, fontWeight: 600, marginBottom: 6 }}>AI Draft Result</p>
                      <p style={{ margin: 0, fontSize: 12, color: COLORS.text, lineHeight: 1.6 }}>{aiDraftResult}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
