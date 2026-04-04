/**
 * PermissionPicker — grouped, searchable permission selector.
 * Used in onboarding wizard (manager setup) and TeamManagementPage (sub-role creation).
 *
 * Props:
 *   selected     — Set<string> of currently selected permission strings
 *   onChange     — callback when selection changes
 *   available    — optional whitelist (for delegation: only show perms the caller holds)
 *   compact      — smaller layout for sub-role creation
 */

import { useState, useMemo } from 'react'
import { Search, ChevronDown, CheckCircle } from 'lucide-react'

export const PERMISSION_GROUPS: Array<{
  key: string
  label: string
  color: string
  perms: Array<{ value: string; label: string; desc: string }>
}> = [
  {
    key: 'students', label: 'Students', color: '#818cf8',
    perms: [
      { value: 'student:read',     label: 'View Students',         desc: 'Browse student profiles' },
      { value: 'student:create',   label: 'Enrol Students',        desc: 'Create new student records' },
      { value: 'student:update',   label: 'Update Students',       desc: 'Edit student profile data' },
      { value: 'student:read_pii', label: 'View PII',              desc: 'Access personal identifiable info' },
    ],
  },
  {
    key: 'academics', label: 'Academics', color: '#60a5fa',
    perms: [
      { value: 'academics:read',    label: 'View Academics',        desc: 'Read academic data' },
      { value: 'academics:manage',  label: 'Manage Academics',      desc: 'Full academic management' },
      { value: 'course:read',       label: 'View Courses',          desc: 'Browse course catalogue' },
      { value: 'course:create',     label: 'Create Courses',        desc: 'Add new courses' },
      { value: 'course:update',     label: 'Edit Courses',          desc: 'Modify course details' },
      { value: 'marks:read',        label: 'View Marks',            desc: 'See student marks' },
      { value: 'marks:entry',       label: 'Enter Marks',           desc: 'Record marks for students' },
      { value: 'marks:finalize',    label: 'Finalize Marks',        desc: 'Lock and publish marks' },
    ],
  },
  {
    key: 'finance', label: 'Finance', color: '#fbbf24',
    perms: [
      { value: 'fee:read',          label: 'View Fees',             desc: 'Browse fee structures' },
      { value: 'fee:create',        label: 'Create Fee Structures', desc: 'Define new fee heads' },
      { value: 'payment:process',   label: 'Process Payments',      desc: 'Record and verify payments' },
      { value: 'ledger:read',       label: 'View Ledger',           desc: 'Access financial ledger' },
    ],
  },
  {
    key: 'examinations', label: 'Examinations', color: '#34d399',
    perms: [
      { value: 'exam_paper:read',      label: 'View Exam Papers',   desc: 'Access question papers' },
      { value: 'exam_paper:create',    label: 'Create Exam Papers', desc: 'Upload question papers' },
      { value: 'hall_ticket:generate', label: 'Hall Tickets',       desc: 'Generate and issue hall tickets' },
      { value: 'result:publish',       label: 'Publish Results',    desc: 'Release exam results' },
    ],
  },
  {
    key: 'hr', label: 'HR & Staff', color: '#f472b6',
    perms: [
      { value: 'staff:read',      label: 'View Staff',            desc: 'Browse staff profiles' },
      { value: 'staff:create',    label: 'Add Staff',             desc: 'Onboard new staff members' },
      { value: 'staff:update',    label: 'Edit Staff',            desc: 'Update staff records' },
      { value: 'leave:approve',   label: 'Approve Leave',         desc: 'Review and approve leave requests' },
      { value: 'payroll:read',    label: 'View Payroll',          desc: 'See payroll data' },
      { value: 'payroll:process', label: 'Process Payroll',       desc: 'Run payroll computations' },
    ],
  },
  {
    key: 'services', label: 'Student Services', color: '#a78bfa',
    perms: [
      { value: 'service:read',     label: 'View Services',        desc: 'Browse service requests' },
      { value: 'service:manage',   label: 'Manage Services',      desc: 'Handle service requests' },
      { value: 'hostel:manage',    label: 'Manage Hostel',        desc: 'Hostel allotment and transfers' },
      { value: 'transport:manage', label: 'Manage Transport',     desc: 'Route and bus management' },
    ],
  },
  {
    key: 'comms', label: 'Communications', color: '#22d3ee',
    perms: [
      { value: 'notification:read',   label: 'View Notifications', desc: 'See notification history' },
      { value: 'notification:manage', label: 'Send Notifications', desc: 'Send targeted notifications' },
      { value: 'announcement:create', label: 'Post Announcements', desc: 'Create institution-wide announcements' },
      { value: 'bulk_message:send',   label: 'Bulk Messaging',     desc: 'Send batch SMS/WhatsApp' },
    ],
  },
  {
    key: 'reports', label: 'Reports & Analytics', color: '#fb923c',
    perms: [
      { value: 'report:read',   label: 'View Reports',    desc: 'Access dashboards and reports' },
      { value: 'report:create', label: 'Create Reports',  desc: 'Build custom reports' },
      { value: 'report:export', label: 'Export Reports',  desc: 'Download data exports' },
    ],
  },
  {
    key: 'alumni', label: 'Alumni & Placement', color: '#4ade80',
    perms: [
      { value: 'alumni:read',      label: 'View Alumni',          desc: 'Browse alumni network' },
      { value: 'alumni:manage',    label: 'Manage Alumni',        desc: 'Update alumni profiles' },
      { value: 'placement:manage', label: 'Manage Placement',     desc: 'Run placement drives' },
    ],
  },
  {
    key: 'regulatory', label: 'Regulatory', color: '#e879f9',
    perms: [
      { value: 'compliance:read',   label: 'View Compliance',     desc: 'Read regulatory data' },
      { value: 'compliance:submit', label: 'Submit Compliance',   desc: 'Submit reports to regulators' },
      { value: 'grievance:manage',  label: 'Manage Grievances',   desc: 'Handle student grievances' },
    ],
  },
  {
    key: 'admin', label: 'Admin & Overrides', color: '#f87171',
    perms: [
      { value: 'override:request',  label: 'Request Overrides',   desc: 'Submit override requests' },
      { value: 'override:approve',  label: 'Approve Overrides',   desc: 'Grant override approvals' },
      { value: 'audit_log:read',    label: 'View Audit Logs',     desc: 'Access full audit trail' },
      { value: 'config:read',       label: 'View Config',         desc: 'See system configuration' },
      { value: 'config:write',      label: 'Edit Config',         desc: 'Change system settings' },
      { value: 'user:read',         label: 'View Users',          desc: 'Browse user accounts' },
      { value: 'user:create',       label: 'Create Users',        desc: 'Add new user accounts' },
      { value: 'user:update',       label: 'Edit Users',          desc: 'Modify user profiles' },
    ],
  },
  {
    key: 'delegation', label: 'Role & Team Management', color: '#1D9E75',
    perms: [
      { value: 'role:create',  label: 'Create Roles',      desc: 'Create sub-roles for your team' },
      { value: 'role:manage',  label: 'Manage Roles',      desc: 'Edit and assign roles' },
      { value: 'role:approve', label: 'Approve Permissions', desc: 'Approve cross-module permission requests' },
      { value: 'ai:invoke',    label: 'Use AI Features',   desc: 'Access AI agent capabilities' },
    ],
  },
]

interface Props {
  selected: Set<string>
  onChange: (next: Set<string>) => void
  available?: Set<string>   // whitelist — undefined means all
  compact?: boolean
}

export function PermissionPicker({ selected, onChange, available, compact }: Props) {
  const [search, setSearch]       = useState('')
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  const toggle = (val: string) => {
    const next = new Set(selected)
    if (next.has(val)) next.delete(val); else next.add(val)
    onChange(next)
  }

  const toggleGroup = (groupKey: string, perms: string[]) => {
    const eligible = available ? perms.filter(p => available.has(p)) : perms
    const allSelected = eligible.every(p => selected.has(p))
    const next = new Set(selected)
    eligible.forEach(p => allSelected ? next.delete(p) : next.add(p))
    onChange(next)
  }

  const toggleCollapse = (key: string) =>
    setCollapsed(p => { const n = new Set(p); if (n.has(key)) n.delete(key); else n.add(key); return n })

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return PERMISSION_GROUPS.map(g => ({
      ...g,
      perms: g.perms.filter(p =>
        (!available || available.has(p.value)) &&
        (!q || p.label.toLowerCase().includes(q) || p.desc.toLowerCase().includes(q) || p.value.includes(q))
      ),
    })).filter(g => g.perms.length > 0)
  }, [search, available])

  const totalSelected = selected.size

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: compact ? 8 : 12 }}>
      {/* Search + count */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ position: 'relative', flex: 1 }}>
          <Search size={12} color="#475569" style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search permissions..."
            style={{
              width: '100%', padding: '7px 12px 7px 28px', borderRadius: 8, fontSize: 11,
              background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
              color: '#e2e8f0', outline: 'none', boxSizing: 'border-box',
            }}
          />
        </div>
        {totalSelected > 0 && (
          <span style={{ fontSize: 10, padding: '3px 8px', borderRadius: 20, background: 'rgba(29,158,117,0.12)', color: '#1D9E75', fontWeight: 600, whiteSpace: 'nowrap' }}>
            {totalSelected} selected
          </span>
        )}
      </div>

      {/* Groups */}
      {filtered.map(group => {
        const isCollapsed  = collapsed.has(group.key)
        const groupPerms   = group.perms.map(p => p.value)
        const eligible     = available ? groupPerms.filter(p => available.has(p)) : groupPerms
        const selectedInGroup = eligible.filter(p => selected.has(p)).length
        const allInGroup   = eligible.length > 0 && selectedInGroup === eligible.length

        return (
          <div key={group.key} style={{ borderRadius: 10, border: '1px solid rgba(255,255,255,0.07)', overflow: 'hidden' }}>
            {/* Group header */}
            <div
              style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: compact ? '8px 12px' : '10px 14px',
                background: allInGroup ? `${group.color}0e` : 'rgba(255,255,255,0.025)',
                cursor: 'pointer', userSelect: 'none',
              }}
            >
              <div onClick={() => toggleCollapse(group.key)} style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
                <ChevronDown size={13} color={group.color} style={{ transform: isCollapsed ? 'rotate(-90deg)' : 'none', transition: 'transform 0.15s', flexShrink: 0 }} />
                <span style={{ fontSize: compact ? 11 : 12, fontWeight: 600, color: allInGroup ? group.color : '#94a3b8' }}>{group.label}</span>
                {selectedInGroup > 0 && (
                  <span style={{ fontSize: 9, padding: '1px 6px', borderRadius: 20, background: `${group.color}22`, color: group.color, fontWeight: 600 }}>
                    {selectedInGroup}/{eligible.length}
                  </span>
                )}
              </div>
              {/* Select all toggle */}
              {eligible.length > 0 && (
                <button
                  onClick={() => toggleGroup(group.key, groupPerms)}
                  style={{
                    fontSize: 9, padding: '2px 8px', borderRadius: 5, cursor: 'pointer',
                    background: allInGroup ? `${group.color}22` : 'rgba(255,255,255,0.04)',
                    color: allInGroup ? group.color : '#475569',
                    border: `1px solid ${allInGroup ? group.color + '44' : 'rgba(255,255,255,0.08)'}`,
                    fontWeight: 600,
                  }}
                >
                  {allInGroup ? 'Clear' : 'All'}
                </button>
              )}
            </div>

            {/* Permission rows */}
            {!isCollapsed && (
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {group.perms.map((perm, i) => {
                  const isSelected  = selected.has(perm.value)
                  const isAvailable = !available || available.has(perm.value)
                  return (
                    <div
                      key={perm.value}
                      onClick={() => isAvailable && toggle(perm.value)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: compact ? '6px 12px' : '8px 14px',
                        borderTop: i > 0 ? '1px solid rgba(255,255,255,0.04)' : 'none',
                        background: isSelected ? `${group.color}08` : 'transparent',
                        cursor: isAvailable ? 'pointer' : 'not-allowed',
                        opacity: isAvailable ? 1 : 0.35,
                        transition: 'background 0.1s',
                      }}
                    >
                      <div style={{
                        width: 16, height: 16, borderRadius: 4, flexShrink: 0,
                        background: isSelected ? `${group.color}22` : 'rgba(255,255,255,0.05)',
                        border: `1.5px solid ${isSelected ? group.color : 'rgba(255,255,255,0.1)'}`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                        {isSelected && <CheckCircle size={10} color={group.color} />}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: compact ? 11 : 12, fontWeight: isSelected ? 600 : 400, color: isSelected ? '#e2e8f0' : '#94a3b8' }}>{perm.label}</div>
                        {!compact && <div style={{ fontSize: 10, color: '#475569' }}>{perm.desc}</div>}
                      </div>
                      <span style={{ fontSize: 9, fontFamily: 'monospace', color: '#334155', flexShrink: 0 }}>{perm.value}</span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}

      {filtered.length === 0 && (
        <p style={{ fontSize: 11, color: '#475569', textAlign: 'center', padding: 16 }}>No permissions match your search.</p>
      )}
    </div>
  )
}
