/**
 * TeamManagementPage — Manager's staff hierarchy builder
 * Route: /admin/team
 * Access: anyone with role:create permission
 *
 * Panels:
 *   Left  — Sub-roles created by this manager (custom roles they own)
 *   Right — Assign users to a selected role / create new sub-roles
 */

import { useState, useEffect } from 'react'
import { Plus, Users, ShieldCheck, Trash2, UserPlus, ChevronRight, RefreshCw, X } from 'lucide-react'
import { PermissionPicker } from '../../components/PermissionPicker'

interface CustomRole {
  id: string
  role_name: string
  description?: string
  module: string
  status: string
  permissions: Array<{ permission: string; status: string }>
}

interface UserEntry {
  id: string
  display_name: string
  email: string
  role: string
}

const TOKEN = () => sessionStorage.getItem('token') ?? ''
const H = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${TOKEN()}` })

async function apiFetch(path: string, method = 'GET', body?: object) {
  const res = await fetch(path, { method, headers: H(), body: body ? JSON.stringify(body) : undefined })
  return res.ok ? res.json() : null
}

const CARD: React.CSSProperties = {
  borderRadius: 12, border: '1px solid rgba(255,255,255,0.07)',
  background: 'rgba(255,255,255,0.025)',
}
const INPUT: React.CSSProperties = {
  width: '100%', padding: '8px 12px', borderRadius: 8, fontSize: 12,
  background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
  color: '#e2e8f0', outline: 'none', boxSizing: 'border-box',
}
const BTN_G: React.CSSProperties = {
  padding: '8px 16px', borderRadius: 8, fontSize: 12, cursor: 'pointer',
  background: 'rgba(29,158,117,0.12)', color: '#1D9E75', border: '1px solid rgba(29,158,117,0.25)', fontWeight: 600,
}
export function TeamManagementPage() {
  const [myRoles, setMyRoles]         = useState<CustomRole[]>([])
  const [delegatable, setDelegatable] = useState<Set<string>>(new Set())
  const [selected, setSelected]       = useState<CustomRole | null>(null)
  const [assignedUsers, setAssignedUsers] = useState<UserEntry[]>([])
  const [loading, setLoading]         = useState(true)

  // New role form
  const [showForm, setShowForm]   = useState(false)
  const [roleName, setRoleName]   = useState('')
  const [roleDesc, setRoleDesc]   = useState('')
  const [rolePerms, setRolePerms] = useState<Set<string>>(new Set())
  const [saving, setSaving]       = useState(false)

  // Invite user form
  const [showInvite, setShowInvite] = useState(false)
  const [inviteName, setInviteName] = useState('')
  const [inviteEmail, setInviteEmail] = useState('')
  const [invitePwd, setInvitePwd]   = useState(`ALIS@${Math.floor(1000 + Math.random() * 9000)}!`)
  const [inviting, setInviting]     = useState(false)

  const load = async () => {
    setLoading(true)
    const [rolesData, permsData] = await Promise.all([
      apiFetch('/api/roles'),
      apiFetch('/api/roles/my-permissions'),
    ])
    // Filter to roles this user created
    if (rolesData?.roles) setMyRoles(rolesData.roles)
    if (permsData?.permissions) setDelegatable(new Set(permsData.permissions))
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const loadAssigned = async (roleId: string) => {
    const data = await apiFetch(`/api/users?custom_role_id=${roleId}`)
    setAssignedUsers(data?.users ?? [])
  }

  const selectRole = (role: CustomRole) => {
    setSelected(role)
    setShowInvite(false)
    loadAssigned(role.id)
  }

  const createRole = async () => {
    if (!roleName.trim() || rolePerms.size === 0) return
    setSaving(true)
    const roleData = await apiFetch('/api/roles', 'POST', { role_name: roleName, description: roleDesc })
    if (roleData?.id) {
      await apiFetch(`/api/roles/${roleData.id}/permissions`, 'POST', { permissions: [...rolePerms] })
    }
    setSaving(false)
    setShowForm(false)
    setRoleName(''); setRoleDesc(''); setRolePerms(new Set())
    load()
  }

  const deleteRole = async (roleId: string) => {
    if (!confirm('Archive this role? Users will lose these permissions.')) return
    await apiFetch(`/api/roles/${roleId}`, 'DELETE')
    if (selected?.id === roleId) setSelected(null)
    load()
  }

  const inviteUser = async () => {
    if (!selected || !inviteEmail.trim() || !inviteName.trim()) return
    setInviting(true)
    // Create user account
    const userData = await apiFetch('/api/auth/register', 'POST', {
      username: inviteEmail, email: inviteEmail, display_name: inviteName,
      password: invitePwd, role: 'admin',
    })
    if (userData?.id) {
      // Assign custom role
      await apiFetch(`/api/users/${userData.id}/roles`, 'POST', { role_id: selected.id })
    }
    setInviting(false)
    setShowInvite(false)
    setInviteName(''); setInviteEmail('')
    loadAssigned(selected.id)
  }

  const removeUser = async (userId: string) => {
    if (!selected) return
    await apiFetch(`/api/users/${userId}/roles/${selected.id}`, 'DELETE')
    loadAssigned(selected.id)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0, height: '100%' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <p style={{ fontSize: 10, fontWeight: 700, color: '#1D9E75', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 4 }}>
          Team Management
        </p>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: '#e2e8f0', letterSpacing: '-0.02em', margin: 0 }}>
          Roles & Staff Hierarchy
        </h1>
        <p style={{ fontSize: 12, color: '#475569', marginTop: 4 }}>
          Create roles from your permission set and assign them to your team members.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 16, flex: 1 }}>
        {/* Left: Role list */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              Sub-Roles ({myRoles.length})
            </span>
            <button onClick={() => load()} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#334155', padding: 4 }}>
              <RefreshCw size={12} />
            </button>
          </div>

          {loading && <p style={{ fontSize: 11, color: '#475569' }}>Loading...</p>}

          {!loading && myRoles.map(role => {
            const approvedCount = role.permissions?.filter(p => p.status === 'APPROVED').length ?? 0
            const isActive = selected?.id === role.id
            return (
              <div
                key={role.id}
                onClick={() => selectRole(role)}
                style={{
                  ...CARD, padding: '12px 14px', cursor: 'pointer',
                  background: isActive ? 'rgba(29,158,117,0.08)' : 'rgba(255,255,255,0.025)',
                  borderColor: isActive ? 'rgba(29,158,117,0.3)' : 'rgba(255,255,255,0.07)',
                  transition: 'all 0.12s',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                    <ShieldCheck size={14} color={isActive ? '#1D9E75' : '#475569'} style={{ flexShrink: 0 }} />
                    <span style={{ fontSize: 12, fontWeight: 600, color: isActive ? '#e2e8f0' : '#94a3b8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {role.role_name}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 9, color: '#334155' }}>{approvedCount}p</span>
                    <button onClick={e => { e.stopPropagation(); deleteRole(role.id) }}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#475569', padding: 2, opacity: 0.6 }}>
                      <Trash2 size={11} />
                    </button>
                    <ChevronRight size={12} color={isActive ? '#1D9E75' : '#334155'} />
                  </div>
                </div>
                {role.description && (
                  <p style={{ fontSize: 10, color: '#475569', margin: '4px 0 0 22px' }}>{role.description}</p>
                )}
              </div>
            )
          })}

          {/* Create role button */}
          <button onClick={() => setShowForm(p => !p)} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            padding: '9px 0', borderRadius: 10, fontSize: 12, fontWeight: 500,
            background: 'transparent', color: '#1D9E75', border: '1px dashed rgba(29,158,117,0.3)', cursor: 'pointer',
          }}>
            <Plus size={13} /> {showForm ? 'Cancel' : 'Create Sub-Role'}
          </button>

          {/* Create role form */}
          {showForm && (
            <div style={{ ...CARD, padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <input value={roleName} onChange={e => setRoleName(e.target.value)} placeholder="Role name (e.g. Lab Coordinator)" style={INPUT} />
              <input value={roleDesc} onChange={e => setRoleDesc(e.target.value)} placeholder="Description (optional)" style={INPUT} />
              <div style={{ maxHeight: 320, overflowY: 'auto' }}>
                <PermissionPicker
                  selected={rolePerms}
                  onChange={setRolePerms}
                  available={delegatable}
                  compact
                />
              </div>
              <button onClick={createRole} disabled={saving || !roleName.trim() || rolePerms.size === 0}
                style={{ ...BTN_G, opacity: saving || !roleName.trim() || rolePerms.size === 0 ? 0.5 : 1 }}>
                {saving ? 'Creating...' : `Create Role (${rolePerms.size} permissions)`}
              </button>
            </div>
          )}
        </div>

        {/* Right: Role detail + assigned users */}
        {selected ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Role info */}
            <div style={{ ...CARD, padding: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <div>
                  <h2 style={{ fontSize: 16, fontWeight: 700, color: '#e2e8f0', margin: 0 }}>{selected.role_name}</h2>
                  {selected.description && <p style={{ fontSize: 12, color: '#475569', margin: '4px 0 0' }}>{selected.description}</p>}
                </div>
                <span style={{ fontSize: 9, padding: '3px 10px', borderRadius: 20, background: 'rgba(29,158,117,0.12)', color: '#1D9E75', fontWeight: 600 }}>
                  {selected.permissions?.filter(p => p.status === 'APPROVED').length ?? 0} permissions
                </span>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {selected.permissions?.filter(p => p.status === 'APPROVED').map(p => (
                  <span key={p.permission} style={{
                    fontSize: 9, padding: '2px 8px', borderRadius: 20, fontFamily: 'monospace',
                    background: 'rgba(255,255,255,0.05)', color: '#64748b', border: '1px solid rgba(255,255,255,0.07)',
                  }}>
                    {p.permission}
                  </span>
                ))}
              </div>
            </div>

            {/* Assigned users */}
            <div style={{ ...CARD, padding: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Users size={14} color="#60a5fa" />
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>
                    Staff assigned ({assignedUsers.length})
                  </span>
                </div>
                <button onClick={() => setShowInvite(p => !p)} style={BTN_G}>
                  <UserPlus size={12} style={{ display: 'inline', marginRight: 5 }} />
                  {showInvite ? 'Cancel' : 'Add Member'}
                </button>
              </div>

              {showInvite && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: 8, marginBottom: 14, padding: 12, borderRadius: 10, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.07)' }}>
                  <input value={inviteName} onChange={e => setInviteName(e.target.value)} placeholder="Full name" style={INPUT} />
                  <input value={inviteEmail} onChange={e => setInviteEmail(e.target.value)} placeholder="Email" type="email" style={INPUT} />
                  <input value={invitePwd} onChange={e => setInvitePwd(e.target.value)} placeholder="Temp password" style={INPUT} />
                  <button onClick={inviteUser} disabled={inviting} style={{ ...BTN_G, whiteSpace: 'nowrap' }}>
                    {inviting ? '...' : 'Add'}
                  </button>
                </div>
              )}

              {assignedUsers.length === 0 && !showInvite && (
                <p style={{ fontSize: 12, color: '#475569' }}>No staff assigned to this role yet.</p>
              )}

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {assignedUsers.map(u => (
                  <div key={u.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', borderRadius: 10, background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'rgba(96,165,250,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, color: '#60a5fa' }}>
                        {u.display_name?.charAt(0) ?? 'U'}
                      </div>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>{u.display_name}</div>
                        <div style={{ fontSize: 11, color: '#475569' }}>{u.email}</div>
                      </div>
                    </div>
                    <button onClick={() => removeUser(u.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#475569', padding: 6 }}>
                      <X size={13} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#334155', fontSize: 13 }}>
            &larr; Select a role to manage its members
          </div>
        )}
      </div>

    </div>
  )
}
