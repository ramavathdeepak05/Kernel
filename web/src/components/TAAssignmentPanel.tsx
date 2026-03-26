/**
 * TAAssignmentPanel — Faculty UI for managing course and session TAs
 *
 * - Multiple TAs can be active simultaneously (add as many as needed)
 * - Scope selected per-assignment via checkbox: Course-wide or Session-only
 * - Student must be enrolled in the course (backend enforces, frontend shows error)
 * - Revoke individual TAs at any time — others remain unaffected
 */

import { useState, useEffect } from 'react'
import { UserPlus, X, ShieldCheck, RefreshCw, Search, ChevronDown, BookOpen, Hash } from 'lucide-react'

type Scope = 'COURSE' | 'SESSION'

interface TAAssignment {
  id: string
  student_id: string
  full_name: string
  email: string
  roll_number: string
  assigned_at: string
  notes?: string
  scope: Scope
}

interface Props {
  courseId: string
  courseCode: string
  courseName: string
  /** Optional: if provided, enables session-scope assignment */
  sessionRef?: string
}

const SCOPE_CONFIG: Record<Scope, { label: string; desc: string; color: string; bg: string }> = {
  COURSE: {
    label: 'Course-wide',
    desc: 'Can take attendance for all sessions this semester',
    color: '#1D9E75',
    bg: 'rgba(29,158,117,0.10)',
  },
  SESSION: {
    label: 'This session only',
    desc: 'Permission expires after this attendance session ends',
    color: '#60a5fa',
    bg: 'rgba(96,165,250,0.10)',
  },
}

export function TAAssignmentPanel({ courseId, courseCode, courseName, sessionRef }: Props) {
  const [assignments, setAssignments] = useState<TAAssignment[]>([])
  const [loading, setLoading] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [identifier, setIdentifier] = useState('')
  const [notes, setNotes] = useState('')
  const [scope, setScope] = useState<Scope>('COURSE')
  const [assigning, setAssigning] = useState(false)
  const [error, setError] = useState('')
  const [revoking, setRevoking] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(true)

  const token = localStorage.getItem('token') ?? ''
  const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }

  const fetchTAs = async () => {
    setLoading(true)
    try {
      const res = await fetch(`/api/v1/academics/courses/${courseId}/ta-assignments`, { headers })
      if (res.ok) setAssignments(await res.json())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchTAs() }, [courseId])

  const resetForm = () => {
    setIdentifier('')
    setNotes('')
    setScope('COURSE')
    setError('')
    setShowForm(false)
  }

  const handleAssign = async () => {
    if (!identifier.trim()) return
    setAssigning(true)
    setError('')
    try {
      const endpoint = scope === 'SESSION' && sessionRef
        ? `/api/v1/academics/sessions/${sessionRef}/ta-assignments`
        : `/api/v1/academics/courses/${courseId}/ta-assignments`

      const body: Record<string, string> = { student_identifier: identifier.trim() }
      if (notes) body.notes = notes
      if (scope === 'SESSION') body.session_type = 'WIFI'

      const res = await fetch(endpoint, { method: 'POST', headers, body: JSON.stringify(body) })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || 'Failed to assign TA')
        return
      }
      resetForm()
      await fetchTAs()
    } finally {
      setAssigning(false)
    }
  }

  const handleRevoke = async (assignmentId: string, name: string, taScope: Scope) => {
    if (!confirm(`Revoke ${name}'s ${taScope === 'COURSE' ? 'course' : 'session'} TA access for ${courseCode}?`)) return
    setRevoking(assignmentId)
    try {
      await fetch(`/api/v1/academics/courses/${courseId}/ta-assignments/${assignmentId}`, {
        method: 'DELETE', headers,
      })
      await fetchTAs()
    } finally {
      setRevoking(null)
    }
  }

  const sc = SCOPE_CONFIG[scope]

  return (
    <div style={{ borderRadius: 12, border: '1px solid rgba(255,255,255,0.07)', background: 'rgba(255,255,255,0.02)', overflow: 'hidden' }}>

      {/* Header */}
      <button onClick={() => setExpanded((p) => !p)} style={{
        width: '100%', padding: '12px 16px', display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', background: 'none', border: 'none', cursor: 'pointer',
        borderBottom: expanded ? '1px solid rgba(255,255,255,0.06)' : 'none',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <ShieldCheck size={15} color="#1D9E75" />
          <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>Teaching Assistants</span>
          {assignments.length > 0 && (
            <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 20, background: 'rgba(29,158,117,0.12)', color: '#1D9E75', fontWeight: 600 }}>
              {assignments.length} active
            </span>
          )}
        </div>
        <ChevronDown size={14} color="#475569" style={{ transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
      </button>

      {expanded && (
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* Active TAs list */}
          {loading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#475569', fontSize: 12 }}>
              <RefreshCw size={12} className="animate-spin" /> Loading...
            </div>
          )}

          {!loading && assignments.length === 0 && (
            <p style={{ fontSize: 12, color: '#475569', margin: 0 }}>No TAs assigned yet.</p>
          )}

          {assignments.map((ta) => {
            const cfg = SCOPE_CONFIG[ta.scope ?? 'COURSE']
            return (
              <div key={ta.id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '10px 12px', borderRadius: 10,
                background: cfg.bg.replace('0.10', '0.04'),
                border: `1px solid ${cfg.color}22`,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{
                    width: 34, height: 34, borderRadius: '50%', background: `${cfg.color}22`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 13, fontWeight: 700, color: cfg.color,
                  }}>
                    {ta.full_name?.charAt(0) ?? 'T'}
                  </div>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>{ta.full_name}</div>
                    <div style={{ fontSize: 11, color: '#475569' }}>
                      {ta.roll_number} &middot; {ta.email}
                    </div>
                    {ta.notes && (
                      <div style={{ fontSize: 10, color: '#64748b', marginTop: 2, fontStyle: 'italic' }}>{ta.notes}</div>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                  <span style={{
                    fontSize: 9, padding: '2px 7px', borderRadius: 20, fontWeight: 600,
                    background: cfg.bg, color: cfg.color,
                    textTransform: 'uppercase', letterSpacing: '0.5px', whiteSpace: 'nowrap',
                  }}>
                    {cfg.label}
                  </span>
                  <button
                    onClick={() => handleRevoke(ta.id, ta.full_name, ta.scope)}
                    disabled={revoking === ta.id}
                    title={`Revoke ${ta.full_name}'s TA access`}
                    style={{
                      background: 'none', border: 'none', cursor: 'pointer',
                      color: revoking === ta.id ? '#475569' : '#f87171',
                      padding: 4, borderRadius: 6, opacity: revoking === ta.id ? 0.5 : 1,
                    }}
                  >
                    <X size={14} />
                  </button>
                </div>
              </div>
            )
          })}

          {/* Assign form */}
          {showForm ? (
            <div style={{
              padding: 14, borderRadius: 10,
              border: '1px solid rgba(255,255,255,0.08)',
              background: 'rgba(255,255,255,0.02)',
              display: 'flex', flexDirection: 'column', gap: 10,
            }}>
              {/* Student identifier input */}
              <div style={{ position: 'relative' }}>
                <Search size={13} color="#475569" style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }} />
                <input
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAssign()}
                  placeholder="Student ID, roll number, or email..."
                  style={{
                    width: '100%', padding: '9px 12px 9px 30px', borderRadius: 8,
                    background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
                    color: '#e2e8f0', fontSize: 12, outline: 'none', boxSizing: 'border-box',
                  }}
                />
              </div>

              {/* Scope selector */}
              <div>
                <p style={{ fontSize: 10, fontWeight: 500, color: '#64748b', margin: '0 0 6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  Permission Scope
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                  {(['COURSE', 'SESSION'] as Scope[]).map((s) => {
                    const c = SCOPE_CONFIG[s]
                    const isSelected = scope === s
                    const disabled = s === 'SESSION' && !sessionRef
                    return (
                      <button
                        key={s}
                        onClick={() => !disabled && setScope(s)}
                        disabled={disabled}
                        style={{
                          padding: '8px 10px', borderRadius: 8, textAlign: 'left', cursor: disabled ? 'not-allowed' : 'pointer',
                          background: isSelected ? c.bg : 'rgba(255,255,255,0.02)',
                          border: `1px solid ${isSelected ? c.color + '44' : 'rgba(255,255,255,0.07)'}`,
                          opacity: disabled ? 0.4 : 1, transition: 'all 0.12s',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 2 }}>
                          {s === 'COURSE' ? <BookOpen size={11} color={isSelected ? c.color : '#64748b'} /> : <Hash size={11} color={isSelected ? c.color : '#64748b'} />}
                          <span style={{ fontSize: 11, fontWeight: 600, color: isSelected ? c.color : '#94a3b8' }}>{c.label}</span>
                        </div>
                        <p style={{ fontSize: 9, color: '#475569', margin: 0, lineHeight: 1.4 }}>{c.desc}</p>
                        {disabled && <p style={{ fontSize: 9, color: '#f87171', margin: '2px 0 0' }}>Start a session first</p>}
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* Notes */}
              <input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Notes (optional) — e.g. Lab section TA"
                style={{
                  width: '100%', padding: '8px 12px', borderRadius: 8,
                  background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
                  color: '#e2e8f0', fontSize: 12, outline: 'none', boxSizing: 'border-box',
                }}
              />

              {error && <p style={{ fontSize: 11, color: '#f87171', margin: 0 }}>{error}</p>}

              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  onClick={handleAssign}
                  disabled={assigning || !identifier.trim()}
                  style={{
                    flex: 1, padding: '9px 0', borderRadius: 8, fontSize: 12, fontWeight: 600,
                    background: assigning ? 'rgba(29,158,117,0.06)' : 'rgba(29,158,117,0.15)',
                    color: '#1D9E75', border: '1px solid rgba(29,158,117,0.25)',
                    cursor: assigning || !identifier.trim() ? 'not-allowed' : 'pointer',
                    opacity: !identifier.trim() ? 0.5 : 1,
                  }}
                >
                  {assigning ? 'Assigning...' : `Assign as ${sc.label} TA`}
                </button>
                <button
                  onClick={resetForm}
                  style={{
                    padding: '9px 14px', borderRadius: 8, fontSize: 12,
                    background: 'rgba(255,255,255,0.04)', color: '#64748b',
                    border: '1px solid rgba(255,255,255,0.07)', cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowForm(true)}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                padding: '9px 0', borderRadius: 8, fontSize: 12, fontWeight: 500,
                background: 'transparent', color: '#1D9E75',
                border: '1px dashed rgba(29,158,117,0.3)',
                cursor: 'pointer', transition: 'all 0.12s',
              }}
            >
              <UserPlus size={13} />
              {assignments.length > 0 ? 'Add Another TA' : 'Assign Teaching Assistant'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
