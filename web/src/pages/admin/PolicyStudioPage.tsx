/**
 * PolicyStudioPage — Admin Console / Policy Studio
 * Route: /settings (or /admin/policies)
 *
 * 3-panel layout: Categories (left 200px) | Policy List (centre) | Policy Editor (right 320px)
 * Current policy value + version history
 * Edit form: value + justification
 * "Draft with AI" button → calls AI gateway
 */

import { useState, useEffect, useCallback } from 'react';
import { alisApi } from '@/lib/alis-api';

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
  { key: 'admissions', label: 'Admissions', module: 'M1' },
  { key: 'academics', label: 'Academics', module: 'M2' },
  { key: 'finance', label: 'Finance', module: 'M4' },
  { key: 'examinations', label: 'Examinations', module: 'M3' },
  { key: 'phd', label: 'PhD & Research', module: 'M8' },
  { key: 'obe', label: 'OBE / CO-PO', module: 'M2' },
  { key: 'convocation', label: 'Convocation', module: 'M2' },
  { key: 'platform', label: 'Platform', module: null },
];

type Policy = {
  id?: string;
  policy_type: string;
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  status: string;
  version?: number;
  effective_from?: string;
  updated_at?: string;
  module?: string;
  // Derived fields for display
  category?: string;
};

type VersionEntry = {
  id: string;
  version?: number;
  status: string;
  effective_from?: string;
  updated_at?: string;
};

function typeLabel(parameters: Record<string, unknown>): string {
  const v = Object.values(parameters)[0];
  if (typeof v === 'number') return Number.isInteger(v) ? 'INTEGER' : 'DECIMAL';
  if (typeof v === 'boolean') return 'BOOLEAN';
  return 'STRING';
}

function typeColor(parameters: Record<string, unknown>): string {
  const t = typeLabel(parameters);
  return t === 'INTEGER' ? COLORS.purple : COLORS.amber;
}

function primaryValue(parameters: Record<string, unknown>): string {
  const entries = Object.entries(parameters);
  if (entries.length === 0) return '—';
  return String(entries[0][1]);
}

export function PolicyStudioPage() {
  const [selectedCategory, setSelectedCategory] = useState<string>('admissions');
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loadingPolicies, setLoadingPolicies] = useState(false);
  const [selectedPolicy, setSelectedPolicy] = useState<Policy | null>(null);
  const [editValue, setEditValue] = useState('');
  const [editJustification, setEditJustification] = useState('');
  const [versionHistory, setVersionHistory] = useState<VersionEntry[]>([]);
  const [showAIDraft, setShowAIDraft] = useState(false);
  const [aiDescription, setAiDescription] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiDraftResult, setAiDraftResult] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [saveError, setSaveError] = useState<string | null>(null);

  // Load policies when category changes
  useEffect(() => {
    setLoadingPolicies(true);
    setSelectedPolicy(null);
    alisApi
      .get<{ policies: Policy[] }>('/policy/', {
        params: { limit: 100 },
      })
      .then((res) => {
        // Filter client-side by category prefix in policy_type
        const all = res.policies ?? [];
        const filtered = all.filter((p) => p.policy_type?.startsWith(selectedCategory + '.') || p.module === POLICY_CATEGORIES.find((c) => c.key === selectedCategory)?.module);
        setPolicies(filtered.length > 0 ? filtered : all.filter((p) => p.policy_type?.startsWith(selectedCategory)));
      })
      .catch(() => setPolicies([]))
      .finally(() => setLoadingPolicies(false));
  }, [selectedCategory]);

  const handleSelectPolicy = useCallback((p: Policy) => {
    setSelectedPolicy(p);
    setEditValue(primaryValue(p.parameters ?? {}));
    setEditJustification('');
    setShowAIDraft(false);
    setAiDraftResult(null);
    setSaveState('idle');
    setSaveError(null);
    setVersionHistory([]);

    // Load version history
    alisApi
      .get<{ history: VersionEntry[] }>(`/policy/history/${encodeURIComponent(p.policy_type)}`)
      .then((res) => setVersionHistory(res.history ?? []))
      .catch(() => setVersionHistory([]));
  }, []);

  const handleSave = useCallback(async () => {
    if (!selectedPolicy || saveState === 'saving') return;
    setSaveState('saving');
    setSaveError(null);
    try {
      // Determine the parameter key from existing policy
      const paramKey = Object.keys(selectedPolicy.parameters ?? {})[0] ?? 'value';
      const numVal = Number(editValue);
      const parsedValue = isNaN(numVal) ? editValue : numVal;

      await alisApi.post('/policy/draft', {
        policy_type: selectedPolicy.policy_type,
        name: selectedPolicy.name,
        description: editJustification || selectedPolicy.description,
        parameters: { [paramKey]: parsedValue },
        effective_from: new Date().toISOString(),
        module: selectedPolicy.module ?? null,
      });

      setSaveState('saved');
      setTimeout(() => setSaveState('idle'), 2500);

      // Refresh version history
      alisApi
        .get<{ history: VersionEntry[] }>(`/policy/history/${encodeURIComponent(selectedPolicy.policy_type)}`)
        .then((res) => setVersionHistory(res.history ?? []))
        .catch(() => null);
    } catch (err: unknown) {
      setSaveState('error');
      setSaveError(err instanceof Error ? err.message : 'Save failed.');
    }
  }, [selectedPolicy, editValue, editJustification, saveState]);

  const handleGenerateDraft = useCallback(async () => {
    if (!selectedPolicy) return;
    setAiLoading(true);
    setAiDraftResult(null);
    try {
      const userId = localStorage.getItem('user_id') ?? 'system';
      const tenantId = localStorage.getItem('tenant_id') ?? 'demo';
      const res = await alisApi.post<{ content?: string; error?: string }>('/ai/invoke', {
        actor_id: userId,
        actor_role: 'admin',
        org_id: tenantId,
        module: 'RAIL',
        agent_name: 'context_advisor_v1',
        input_data: {
          policy_type: selectedPolicy.policy_type,
          current_value: editValue,
          description_prompt: aiDescription,
        },
      });
      setAiDraftResult(res.content ?? 'AI did not return a suggestion. Try refining your prompt.');
    } catch (err: unknown) {
      setAiDraftResult(`AI unavailable: ${err instanceof Error ? err.message : 'Unknown error.'}`);
    } finally {
      setAiLoading(false);
    }
  }, [selectedPolicy, editValue, aiDescription]);

  const filteredPolicies = policies;

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
                display: 'flex', width: '100%', alignItems: 'center',
                justifyContent: 'space-between', padding: '9px 16px', border: 'none',
                background: selectedCategory === cat.key ? `${COLORS.purple}22` : 'transparent',
                borderLeft: selectedCategory === cat.key ? `3px solid ${COLORS.purple}` : '3px solid transparent',
                color: selectedCategory === cat.key ? COLORS.text : COLORS.muted,
                fontSize: 13, fontWeight: selectedCategory === cat.key ? 600 : 400,
                cursor: 'pointer', textAlign: 'left', transition: 'all 0.12s',
              }}
            >
              <span>{cat.label}</span>
            </button>
          ))}
        </div>

        {/* CENTRE: Policy list */}
        <div style={{ flex: 1, overflowY: 'auto', background: COLORS.bg, padding: '16px 20px' }}>
          <p style={{ margin: '0 0 14px', fontSize: 12, color: COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
            {POLICY_CATEGORIES.find((c) => c.key === selectedCategory)?.label}
            {loadingPolicies ? ' — Loading…' : ` — ${filteredPolicies.length} policies`}
          </p>
          {!loadingPolicies && filteredPolicies.length === 0 && (
            <p style={{ color: COLORS.muted, fontSize: 14 }}>No policies found for this category.</p>
          )}
          {filteredPolicies.map((p) => (
            <div
              key={p.id ?? p.policy_type}
              onClick={() => handleSelectPolicy(p)}
              style={{
                background: selectedPolicy?.policy_type === p.policy_type ? `${COLORS.purple}18` : COLORS.card,
                border: `1px solid ${selectedPolicy?.policy_type === p.policy_type ? COLORS.purple : COLORS.border}`,
                borderRadius: 8, padding: '13px 16px', marginBottom: 10, cursor: 'pointer', transition: 'all 0.12s',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <code style={{ fontSize: 12, color: COLORS.purple, fontFamily: 'monospace', wordBreak: 'break-all' }}>{p.policy_type}</code>
                <span style={{
                  fontSize: 11, fontWeight: 700,
                  color: typeColor(p.parameters ?? {}),
                  background: typeColor(p.parameters ?? {}) + '22',
                  padding: '2px 7px', borderRadius: 4, marginLeft: 8, whiteSpace: 'nowrap',
                }}>
                  {typeLabel(p.parameters ?? {})}
                </span>
              </div>
              <p style={{ margin: '6px 0 4px', fontSize: 13, color: COLORS.text }}>{p.name}</p>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 12, color: COLORS.muted }}>
                  Value: <strong style={{ color: COLORS.text }}>{primaryValue(p.parameters ?? {})}</strong>
                </span>
                <span style={{ fontSize: 11, color: COLORS.muted }}>
                  {p.status} · {p.updated_at ? new Date(p.updated_at).toLocaleDateString('en-IN') : '—'}
                </span>
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
              <code style={{ fontSize: 11, color: COLORS.purple, fontFamily: 'monospace', wordBreak: 'break-all', display: 'block', marginBottom: 10 }}>
                {selectedPolicy.policy_type}
              </code>

              <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: typeColor(selectedPolicy.parameters ?? {}), background: typeColor(selectedPolicy.parameters ?? {}) + '22', padding: '3px 8px', borderRadius: 4 }}>
                  {typeLabel(selectedPolicy.parameters ?? {})}
                </span>
                <span style={{ fontSize: 11, fontWeight: 600, color: COLORS.teal, background: COLORS.teal + '22', padding: '3px 8px', borderRadius: 4 }}>
                  {selectedPolicy.status}
                </span>
              </div>

              <p style={{ fontSize: 12, color: COLORS.muted, margin: '0 0 16px' }}>{selectedPolicy.description}</p>

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
              {versionHistory.length > 0 && (
                <div style={{ marginBottom: 18 }}>
                  <p style={{ fontSize: 12, color: COLORS.muted, margin: '0 0 8px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Version History</p>
                  {versionHistory.slice(0, 5).map((h, i) => (
                    <div key={h.id ?? i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: `1px solid ${COLORS.border}` }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: COLORS.purple, minWidth: 24 }}>v{h.version ?? (versionHistory.length - i)}</span>
                      <span style={{ fontSize: 12, color: COLORS.muted }}>
                        {h.updated_at ? new Date(h.updated_at).toLocaleDateString('en-IN') : '—'}
                      </span>
                      <span style={{ fontSize: 11, color: COLORS.teal, marginLeft: 'auto' }}>{h.status}</span>
                    </div>
                  ))}
                </div>
              )}

              {saveError && (
                <p style={{ fontSize: 12, color: COLORS.red, margin: '0 0 10px' }}>{saveError}</p>
              )}

              {/* Action buttons */}
              <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                <button
                  onClick={handleSave}
                  disabled={saveState === 'saving'}
                  style={{
                    flex: 1, padding: '9px 0',
                    background: saveState === 'saved' ? COLORS.teal : saveState === 'error' ? COLORS.red : COLORS.teal,
                    border: 'none', borderRadius: 7, color: '#fff', fontWeight: 600, fontSize: 13,
                    cursor: saveState === 'saving' ? 'not-allowed' : 'pointer', opacity: saveState === 'saving' ? 0.6 : 1,
                  }}
                >
                  {saveState === 'saving' ? 'Saving…' : saveState === 'saved' ? '✓ Saved' : 'Save Changes'}
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
                      resize: 'vertical', boxSizing: 'border-box', outline: 'none', marginBottom: 10,
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
