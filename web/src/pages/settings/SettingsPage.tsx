/**
 * SettingsPage — SUPER_ADMIN / Admin settings hub
 *
 * Tabs:
 *   1. Roles — view all custom roles, their permissions, and assigned members
 *   2. WhatsApp Templates — set MSG91 DLT template IDs per notification type
 *   3. Feature Flags — toggle system capabilities (read-only view for now)
 */

import { useState, useEffect } from 'react'
import { useAuthStore } from '../../store/authStore'
import { alisApi } from '../../lib/alis-api'

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

interface CustomRole {
  id: string
  role_name: string
  module: string
  description: string
  status: string
  created_at: string
  permissions?: string[]
  member_count?: number
}

interface NotifTemplate {
  id: string
  key: string
  name: string
  channel: string
  whatsapp_template_id: string | null
  is_active: boolean
}

// ─────────────────────────────────────────────
// Tab: Roles
// ─────────────────────────────────────────────

function RolesTab() {
  const { token } = useAuthStore()
  const [roles, setRoles] = useState<CustomRole[]>([])
  const [selected, setSelected] = useState<CustomRole | null>(null)
  const [permissions, setPermissions] = useState<string[]>([])
  const [members, setMembers] = useState<{ user_id: string; email: string; name: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [archiving, setArchiving] = useState(false)

  useEffect(() => {
    fetch('/api/roles', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(d => setRoles(d.roles ?? []))
      .finally(() => setLoading(false))
  }, [token])

  const selectRole = async (role: CustomRole) => {
    setSelected(role)
    // Fetch permissions
    const [pRes, mRes] = await Promise.all([
      fetch(`/api/roles/${role.id}/permissions`, { headers: { Authorization: `Bearer ${token}` } }),
      fetch(`/api/roles/${role.id}/members`,     { headers: { Authorization: `Bearer ${token}` } }),
    ])
    const pData = await pRes.json()
    const mData = await mRes.json()
    setPermissions(pData.permissions?.map((p: { permission: string }) => p.permission) ?? [])
    setMembers(mData.members ?? [])
  }

  const archiveRole = async (roleId: string) => {
    if (!confirm('Archive this role? Assigned users will lose it immediately.')) return
    setArchiving(true)
    await fetch(`/api/roles/${roleId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    })
    setRoles(prev => prev.filter(r => r.id !== roleId))
    if (selected?.id === roleId) { setSelected(null); setPermissions([]); setMembers([]) }
    setArchiving(false)
  }

  const MODULE_COLORS: Record<string, string> = {
    M1: '#3b82f6', M2: '#10b981', M3: '#f59e0b', M4: '#8b5cf6',
    M5: '#ef4444', M6: '#06b6d4', M7: '#84cc16', M8: '#f97316',
    DELEGATED: '#6b7280',
  }

  if (loading) return <div style={styles.empty}>Loading roles...</div>

  return (
    <div style={styles.splitPane}>
      {/* Left — role list */}
      <div style={styles.leftPanel}>
        <div style={styles.panelHeader}>
          <span style={styles.panelTitle}>Custom Roles</span>
          <span style={styles.badge}>{roles.length}</span>
        </div>
        {roles.length === 0 && (
          <div style={styles.empty}>No custom roles yet. Run the onboarding wizard to create managers.</div>
        )}
        {roles.map(role => (
          <div
            key={role.id}
            onClick={() => selectRole(role)}
            style={{
              ...styles.roleCard,
              borderLeft: `3px solid ${MODULE_COLORS[role.module] ?? '#6b7280'}`,
              background: selected?.id === role.id ? '#1e293b' : '#0f172a',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={styles.roleName}>{role.role_name}</span>
              <span style={{ ...styles.modulePill, background: MODULE_COLORS[role.module] ?? '#6b7280' }}>
                {role.module}
              </span>
            </div>
            {role.description && (
              <div style={styles.roleDesc}>{role.description}</div>
            )}
            <div style={styles.roleMeta}>
              {new Date(role.created_at).toLocaleDateString()}
            </div>
          </div>
        ))}
      </div>

      {/* Right — role detail */}
      <div style={styles.rightPanel}>
        {!selected ? (
          <div style={styles.empty}>Select a role to view details</div>
        ) : (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
              <div>
                <div style={styles.detailTitle}>{selected.role_name}</div>
                <div style={styles.detailMeta}>Module: {selected.module} · Status: {selected.status}</div>
                {selected.description && <div style={styles.detailDesc}>{selected.description}</div>}
              </div>
              <button
                onClick={() => archiveRole(selected.id)}
                disabled={archiving}
                style={styles.archiveBtn}
              >
                Archive Role
              </button>
            </div>

            <div style={styles.section}>
              <div style={styles.sectionTitle}>Permissions ({permissions.length})</div>
              <div style={styles.permGrid}>
                {permissions.length === 0
                  ? <span style={styles.empty}>No approved permissions</span>
                  : permissions.map(p => (
                      <span key={p} style={styles.permPill}>{p}</span>
                    ))
                }
              </div>
            </div>

            <div style={styles.section}>
              <div style={styles.sectionTitle}>Assigned Users ({members.length})</div>
              {members.length === 0
                ? <div style={styles.empty}>No users assigned</div>
                : members.map(m => (
                    <div key={m.user_id} style={styles.memberRow}>
                      <div style={styles.avatar}>{(m.name || m.email)[0].toUpperCase()}</div>
                      <div>
                        <div style={styles.memberName}>{m.name || '—'}</div>
                        <div style={styles.memberEmail}>{m.email}</div>
                      </div>
                    </div>
                  ))
              }
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Tab: WhatsApp DLT Templates
// ─────────────────────────────────────────────

function WhatsAppTab() {
  const { token } = useAuthStore()
  const [templates, setTemplates] = useState<NotifTemplate[]>([])
  const [editing, setEditing] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/v1/comms/templates?channel=WHATSAPP', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.json())
      .then(d => setTemplates(d.templates ?? []))
      .finally(() => setLoading(false))
  }, [token])

  const save = async (templateId: string) => {
    const val = editing[templateId]
    if (val === undefined) return
    setSaving(templateId)
    await fetch(`/api/v1/comms/templates/${templateId}`, {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ whatsapp_template_id: val }),
    })
    setTemplates(prev => prev.map(t =>
      t.id === templateId ? { ...t, whatsapp_template_id: val } : t
    ))
    setEditing(prev => { const n = { ...prev }; delete n[templateId]; return n })
    setSaving(null)
  }

  if (loading) return <div style={styles.empty}>Loading templates...</div>

  return (
    <div>
      <div style={styles.infoBox}>
        <strong>How to configure:</strong> Register each template with MSG91's DLT portal.
        You'll receive a 19-digit numeric template ID (e.g. <code>1507161245247669634</code>).
        Paste it in the field below and save. WhatsApp notifications won't send until the ID is set.
      </div>

      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Template</th>
            <th style={styles.th}>Key</th>
            <th style={styles.th}>DLT Template ID</th>
            <th style={styles.th}></th>
          </tr>
        </thead>
        <tbody>
          {templates.map(t => {
            const val = editing[t.id] ?? t.whatsapp_template_id ?? ''
            const isDirty = editing[t.id] !== undefined && editing[t.id] !== (t.whatsapp_template_id ?? '')
            return (
              <tr key={t.id} style={{ borderBottom: '1px solid #1e293b' }}>
                <td style={styles.td}>{t.name}</td>
                <td style={{ ...styles.td, fontFamily: 'monospace', fontSize: 12, color: '#94a3b8' }}>{t.key}</td>
                <td style={styles.td}>
                  <input
                    value={val}
                    onChange={e => setEditing(prev => ({ ...prev, [t.id]: e.target.value }))}
                    placeholder="Enter MSG91 DLT template ID"
                    style={{
                      ...styles.input,
                      borderColor: isDirty ? '#3b82f6' : '#334155',
                    }}
                  />
                </td>
                <td style={{ ...styles.td, width: 80 }}>
                  {isDirty && (
                    <button
                      onClick={() => save(t.id)}
                      disabled={saving === t.id}
                      style={styles.saveBtn}
                    >
                      {saving === t.id ? '...' : 'Save'}
                    </button>
                  )}
                  {!isDirty && t.whatsapp_template_id && (
                    <span style={{ color: '#22c55e', fontSize: 12 }}>✓</span>
                  )}
                </td>
              </tr>
            )
          })}
          {templates.length === 0 && (
            <tr><td colSpan={4} style={{ ...styles.td, textAlign: 'center', color: '#64748b' }}>
              No WhatsApp templates found. Run seed.py to initialize templates.
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

// ─────────────────────────────────────────────
// Main SettingsPage
// ─────────────────────────────────────────────

export function SettingsPage() {
  const [tab, setTab] = useState<'roles' | 'whatsapp' | 'flags'>('roles')

  const tabs: { key: typeof tab; label: string }[] = [
    { key: 'roles',    label: 'Roles & Permissions' },
    { key: 'whatsapp', label: 'WhatsApp DLT Templates' },
    { key: 'flags',    label: 'Feature Flags' },
  ]

  return (
    <div style={styles.page}>
      <div style={styles.pageHeader}>
        <h1 style={styles.pageTitle}>Settings</h1>
        <p style={styles.pageSubtitle}>System configuration — Super Admin only</p>
      </div>

      <div style={styles.tabBar}>
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{ ...styles.tabBtn, ...(tab === t.key ? styles.tabActive : {}) }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div style={styles.tabContent}>
        {tab === 'roles'    && <RolesTab />}
        {tab === 'whatsapp' && <WhatsAppTab />}
        {tab === 'flags'    && <FeatureFlagsTab />}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Tab: Feature Flags (read-only overview)
// ─────────────────────────────────────────────

function FeatureFlagsTab() {
  const { token } = useAuthStore()
  const [flags, setFlags] = useState<{ key: string; enabled: boolean; description: string }[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/v1/feature-flags', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(d => setFlags(d.flags ?? []))
      .finally(() => setLoading(false))
  }, [token])

  if (loading) return <div style={styles.empty}>Loading flags...</div>

  return (
    <div>
      <div style={styles.infoBox}>
        Feature flags are managed via the API or by your platform administrator.
        Contact support to enable/disable flags for your institution.
      </div>
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Flag</th>
            <th style={styles.th}>Status</th>
            <th style={styles.th}>Description</th>
          </tr>
        </thead>
        <tbody>
          {flags.map(f => (
            <tr key={f.key} style={{ borderBottom: '1px solid #1e293b' }}>
              <td style={{ ...styles.td, fontFamily: 'monospace', fontSize: 12 }}>{f.key}</td>
              <td style={styles.td}>
                <span style={{
                  ...styles.statusPill,
                  background: f.enabled ? '#16a34a22' : '#dc262622',
                  color: f.enabled ? '#22c55e' : '#f87171',
                }}>
                  {f.enabled ? 'Enabled' : 'Disabled'}
                </span>
              </td>
              <td style={{ ...styles.td, color: '#94a3b8', fontSize: 13 }}>{f.description}</td>
            </tr>
          ))}
          {flags.length === 0 && (
            <tr><td colSpan={3} style={{ ...styles.td, textAlign: 'center', color: '#64748b' }}>
              No feature flags configured.
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

// ─────────────────────────────────────────────
// Styles
// ─────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  page:        { padding: 32, maxWidth: 1200, margin: '0 auto', color: '#e2e8f0' },
  pageHeader:  { marginBottom: 24 },
  pageTitle:   { fontSize: 24, fontWeight: 700, color: '#f1f5f9', margin: 0 },
  pageSubtitle:{ color: '#64748b', marginTop: 4, fontSize: 14 },
  tabBar:      { display: 'flex', gap: 4, borderBottom: '1px solid #1e293b', marginBottom: 24 },
  tabBtn:      { background: 'none', border: 'none', color: '#94a3b8', padding: '10px 16px', cursor: 'pointer', fontSize: 14, borderBottom: '2px solid transparent' },
  tabActive:   { color: '#3b82f6', borderBottom: '2px solid #3b82f6' },
  tabContent:  { minHeight: 400 },
  splitPane:   { display: 'flex', gap: 24, minHeight: 500 },
  leftPanel:   { width: 300, flexShrink: 0, overflowY: 'auto' },
  rightPanel:  { flex: 1, background: '#0f172a', borderRadius: 8, padding: 24, border: '1px solid #1e293b' },
  panelHeader: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 },
  panelTitle:  { fontSize: 14, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' },
  badge:       { background: '#1e293b', color: '#64748b', borderRadius: 12, padding: '2px 8px', fontSize: 12 },
  roleCard:    { padding: '12px 14px', borderRadius: 8, marginBottom: 8, cursor: 'pointer', border: '1px solid #1e293b', transition: 'background 0.15s' },
  roleName:    { fontWeight: 600, fontSize: 14, color: '#f1f5f9' },
  modulePill:  { fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 4, color: '#fff', letterSpacing: '0.05em' },
  roleDesc:    { fontSize: 12, color: '#64748b', marginTop: 4 },
  roleMeta:    { fontSize: 11, color: '#475569', marginTop: 6 },
  detailTitle: { fontSize: 20, fontWeight: 700, color: '#f1f5f9' },
  detailMeta:  { fontSize: 13, color: '#64748b', marginTop: 4 },
  detailDesc:  { fontSize: 14, color: '#94a3b8', marginTop: 8 },
  archiveBtn:  { background: '#7f1d1d', color: '#fca5a5', border: '1px solid #991b1b', borderRadius: 6, padding: '6px 12px', cursor: 'pointer', fontSize: 13 },
  section:     { marginTop: 24 },
  sectionTitle:{ fontSize: 13, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12 },
  permGrid:    { display: 'flex', flexWrap: 'wrap', gap: 6 },
  permPill:    { background: '#1e3a5f', color: '#93c5fd', fontSize: 12, padding: '4px 10px', borderRadius: 20, border: '1px solid #1d4ed8' },
  memberRow:   { display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: '1px solid #1e293b' },
  avatar:      { width: 32, height: 32, borderRadius: '50%', background: '#1d4ed8', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, flexShrink: 0 },
  memberName:  { fontSize: 14, color: '#e2e8f0' },
  memberEmail: { fontSize: 12, color: '#64748b' },
  empty:       { color: '#475569', fontSize: 14, padding: '24px 0', textAlign: 'center' },
  infoBox:     { background: '#0c1a2e', border: '1px solid #1e3a5f', borderRadius: 8, padding: '12px 16px', fontSize: 13, color: '#94a3b8', marginBottom: 20, lineHeight: 1.6 },
  table:       { width: '100%', borderCollapse: 'collapse' },
  th:          { textAlign: 'left', padding: '10px 12px', fontSize: 12, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid #1e293b' },
  td:          { padding: '12px 12px', fontSize: 14, color: '#e2e8f0', verticalAlign: 'middle' },
  input:       { background: '#1e293b', border: '1px solid #334155', borderRadius: 6, color: '#f1f5f9', padding: '6px 10px', fontSize: 13, width: '100%', outline: 'none', fontFamily: 'monospace' },
  saveBtn:     { background: '#1d4ed8', color: '#fff', border: 'none', borderRadius: 6, padding: '5px 12px', cursor: 'pointer', fontSize: 13 },
  statusPill:  { padding: '3px 8px', borderRadius: 12, fontSize: 12, fontWeight: 600 },
}
