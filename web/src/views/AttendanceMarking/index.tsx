/**
 * AttendanceMarking — Offline-capable faculty attendance marking view
 *
 * Feature flag: academics.offline_attendance_pwa
 *
 * Behaviour:
 *  - Online: fetches student roster from API, marks sent directly to API
 *  - Offline: reads cached roster from IndexedDB, marks queued locally
 *  - On reconnect: background sync triggers automatically
 *
 * The component handles both the "attend now" session flow and
 * the pending-sync badge so faculty always know what's waiting.
 */
import { useState, useEffect, useCallback } from 'react'
import { Wifi, WifiOff, RefreshCw, CheckCircle2, XCircle, Clock, CloudUpload } from 'lucide-react'
import {
  markAttendanceOffline,
  cacheSession,
  getCachedSession,
  pendingSyncCount,
  type PendingMark,
  type CachedStudent,
} from './offline-store'
import { syncPendingMarks, syncWhenOnline } from './sync'

type MarkStatus = 'PRESENT' | 'ABSENT' | 'LATE'

interface Props {
  sessionId: string
  courseCode: string
  courseName: string
  date: string           // YYYY-MM-DD
  tenantId: string
  authToken: string
}

const STATUS_CONFIG: Record<MarkStatus, { label: string; color: string; bg: string; icon: React.ElementType }> = {
  PRESENT: { label: 'Present', color: '#1D9E75', bg: 'rgba(29,158,117,0.12)', icon: CheckCircle2 },
  ABSENT:  { label: 'Absent',  color: '#f87171', bg: 'rgba(248,113,113,0.10)', icon: XCircle },
  LATE:    { label: 'Late',    color: '#fbbf24', bg: 'rgba(251,191,36,0.10)',  icon: Clock },
}

export function AttendanceMarking({ sessionId, courseCode, courseName, date, tenantId, authToken }: Props) {
  const [online, setOnline] = useState(navigator.onLine)
  const [students, setStudents] = useState<CachedStudent[]>([])
  const [marks, setMarks] = useState<Record<string, MarkStatus>>({})
  const [pendingCount, setPendingCount] = useState(0)
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState('')
  const [loading, setLoading] = useState(true)
  const [saved, setSaved] = useState<Set<string>>(new Set())

  const headers = { Authorization: `Bearer ${authToken}`, 'X-Tenant-ID': tenantId }

  // ── Network status tracking ──────────────────────────────────────────────
  useEffect(() => {
    const goOnline  = () => setOnline(true)
    const goOffline = () => setOnline(false)
    window.addEventListener('online',  goOnline)
    window.addEventListener('offline', goOffline)
    return () => {
      window.removeEventListener('online',  goOnline)
      window.removeEventListener('offline', goOffline)
    }
  }, [])

  // ── Load student roster ──────────────────────────────────────────────────
  const loadStudents = useCallback(async () => {
    setLoading(true)
    try {
      if (online) {
        const res = await fetch(`/api/v1/attendance/sessions/${sessionId}/students`, { headers })
        if (res.ok) {
          const data: CachedStudent[] = await res.json()
          setStudents(data)
          // Pre-cache for offline use
          await cacheSession({ sessionId, courseCode, courseName, date, cachedAt: new Date().toISOString(), students: data })
        }
      } else {
        const cached = await getCachedSession(sessionId)
        if (cached) setStudents(cached.students)
      }
    } finally {
      setLoading(false)
    }
  }, [sessionId, online])

  useEffect(() => { loadStudents() }, [loadStudents])

  // ── Pending sync badge ───────────────────────────────────────────────────
  const refreshPendingCount = useCallback(async () => {
    setPendingCount(await pendingSyncCount())
  }, [])

  useEffect(() => {
    refreshPendingCount()
    // Register online listener for auto-sync
    syncWhenOnline(tenantId, authToken)
  }, [online])

  // ── Mark a student ───────────────────────────────────────────────────────
  const handleMark = async (studentId: string, status: MarkStatus) => {
    setMarks((prev) => ({ ...prev, [studentId]: status }))

    const mark: Omit<PendingMark, 'synced' | 'failCount'> = {
      id: crypto.randomUUID(),
      sessionId,
      studentId,
      status,
      markedAt: new Date().toISOString(),
    }

    if (online) {
      try {
        const res = await fetch(`/api/v1/attendance/sessions/${sessionId}/mark`, {
          method: 'POST',
          headers: { ...headers, 'Content-Type': 'application/json' },
          body: JSON.stringify({ student_id: studentId, status }),
        })
        if (res.ok) {
          setSaved((prev) => new Set([...prev, studentId]))
          return
        }
      } catch { /* fall through to offline queue */ }
    }

    // Queue offline
    await markAttendanceOffline(mark)
    await refreshPendingCount()
  }

  // ── Manual sync ──────────────────────────────────────────────────────────
  const handleSync = async () => {
    setSyncing(true)
    setSyncMsg('')
    try {
      const result = await syncPendingMarks(tenantId, authToken)
      setSyncMsg(`Synced ${result.synced} mark${result.synced !== 1 ? 's' : ''}${result.failed ? `, ${result.failed} failed` : ''}`)
      await refreshPendingCount()
    } finally {
      setSyncing(false)
    }
  }

  // ── Bulk actions ─────────────────────────────────────────────────────────
  const markAll = async (status: MarkStatus) => {
    for (const s of students) await handleMark(s.studentId, status)
  }

  const unmarked = students.filter((s) => !marks[s.studentId]).length
  const presentCount = Object.values(marks).filter((v) => v === 'PRESENT').length
  const absentCount  = Object.values(marks).filter((v) => v === 'ABSENT').length
  const lateCount    = Object.values(marks).filter((v) => v === 'LATE').length

  return (
    <div style={{ background: '#0f172a', minHeight: '100dvh', color: '#e2e8f0', fontFamily: 'system-ui, sans-serif' }}>

      {/* Header */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', position: 'sticky', top: 0, background: '#0f172a', zIndex: 10 }}>
        <div>
          <div style={{ fontSize: 11, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{courseCode} · {date}</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#e2e8f0', marginTop: 2 }}>{courseName}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* Network badge */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, padding: '4px 10px', borderRadius: 20, background: online ? 'rgba(29,158,117,0.10)' : 'rgba(248,113,113,0.10)', color: online ? '#1D9E75' : '#f87171', border: `1px solid ${online ? 'rgba(29,158,117,0.2)' : 'rgba(248,113,113,0.2)'}` }}>
            {online ? <Wifi size={11} /> : <WifiOff size={11} />}
            {online ? 'Online' : 'Offline'}
          </div>
          {/* Pending sync badge */}
          {pendingCount > 0 && (
            <button
              onClick={handleSync}
              disabled={syncing || !online}
              title="Sync pending marks"
              style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, padding: '4px 10px', borderRadius: 20, background: 'rgba(251,191,36,0.10)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.2)', cursor: online ? 'pointer' : 'not-allowed' }}
            >
              <CloudUpload size={11} />
              {syncing ? 'Syncing…' : `${pendingCount} pending`}
            </button>
          )}
        </div>
      </div>

      {syncMsg && (
        <div style={{ padding: '8px 20px', fontSize: 11, color: '#64748b', background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          {syncMsg}
        </div>
      )}

      {/* Summary bar */}
      <div style={{ padding: '12px 20px', display: 'flex', gap: 12, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        {[
          { label: 'Present', value: presentCount, color: '#1D9E75' },
          { label: 'Absent',  value: absentCount,  color: '#f87171' },
          { label: 'Late',    value: lateCount,     color: '#fbbf24' },
          { label: 'Unmarked',value: unmarked,      color: '#475569' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 18, fontWeight: 700, color }}>{value}</div>
            <div style={{ fontSize: 9, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
          </div>
        ))}
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6 }}>
          <button onClick={() => markAll('PRESENT')} style={{ fontSize: 11, padding: '5px 10px', borderRadius: 6, background: 'rgba(29,158,117,0.10)', color: '#1D9E75', border: '1px solid rgba(29,158,117,0.2)', cursor: 'pointer' }}>All Present</button>
          <button onClick={loadStudents} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#475569', padding: 4 }}><RefreshCw size={13} /></button>
        </div>
      </div>

      {/* Student list */}
      <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {loading && (
          <div style={{ textAlign: 'center', padding: 32, color: '#475569', fontSize: 13 }}>
            <RefreshCw size={16} style={{ display: 'inline', marginRight: 6 }} />
            Loading roster…
          </div>
        )}

        {!loading && students.length === 0 && (
          <div style={{ textAlign: 'center', padding: 32, color: '#475569', fontSize: 13 }}>
            {online ? 'No students enrolled in this session.' : 'No cached roster available. Connect to load the student list.'}
          </div>
        )}

        {students.map((student) => {
          const currentMark = marks[student.studentId]
          const isSaved = saved.has(student.studentId)

          return (
            <div key={student.studentId} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '10px 14px', borderRadius: 10,
              background: currentMark ? STATUS_CONFIG[currentMark].bg : 'rgba(255,255,255,0.02)',
              border: `1px solid ${currentMark ? STATUS_CONFIG[currentMark].color + '22' : 'rgba(255,255,255,0.06)'}`,
              transition: 'all 0.12s',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: '50%',
                  background: currentMark ? STATUS_CONFIG[currentMark].bg : 'rgba(255,255,255,0.05)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, fontWeight: 700,
                  color: currentMark ? STATUS_CONFIG[currentMark].color : '#64748b',
                }}>
                  {student.fullName.charAt(0)}
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>{student.fullName}</div>
                  <div style={{ fontSize: 11, color: '#475569' }}>
                    {student.rollNumber}
                    {isSaved && <span style={{ marginLeft: 6, color: '#1D9E75', fontSize: 10 }}>✓ saved</span>}
                    {!isSaved && currentMark && !online && <span style={{ marginLeft: 6, color: '#fbbf24', fontSize: 10 }}>⏸ queued</span>}
                  </div>
                </div>
              </div>

              {/* Mark buttons */}
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                {(['PRESENT', 'ABSENT', 'LATE'] as MarkStatus[]).map((s) => {
                  const cfg = STATUS_CONFIG[s]
                  const active = currentMark === s
                  const Icon = cfg.icon
                  return (
                    <button
                      key={s}
                      onClick={() => handleMark(student.studentId, s)}
                      title={cfg.label}
                      style={{
                        width: 34, height: 34, borderRadius: 8, border: 'none', cursor: 'pointer',
                        background: active ? cfg.bg : 'rgba(255,255,255,0.04)',
                        color: active ? cfg.color : '#475569',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        transition: 'all 0.1s',
                        outline: active ? `1.5px solid ${cfg.color}44` : 'none',
                      }}
                    >
                      <Icon size={15} />
                    </button>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>

      {/* Bottom padding for mobile safe area */}
      <div style={{ height: 40 }} />
    </div>
  )
}
