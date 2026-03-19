/**
 * LiveRoster — polls GET /attendance/wifi/sessions/:id every 3 seconds.
 * Displays each enrolled student with their verification status.
 */
import { useState, useEffect, useRef } from 'react'
import { CheckCircle2, Clock, XCircle, AlertTriangle } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'
const POLL_INTERVAL = 3000

interface StudentRow {
  student_id: string
  full_name: string
  roll_number: string
  status: 'PENDING' | 'PRESENT' | 'ABSENT' | 'IP_MISMATCH'
  verified_at: string | null
  ip_matched: boolean | null
}

interface SessionStatus {
  present_count: number
  absent_count: number
  student_count: number
  roster: StudentRow[]
}

const STATUS_CONFIG = {
  PRESENT:    { color: '#1D9E75', icon: CheckCircle2, label: 'Present' },
  ABSENT:     { color: '#f87171', icon: XCircle,      label: 'Absent' },
  IP_MISMATCH:{ color: '#fbbf24', icon: AlertTriangle, label: 'IP mismatch' },
  PENDING:    { color: '#475569', icon: Clock,         label: 'Waiting' },
}

interface Props {
  sessionId: string
  token: string
  tenantId: string
}

export function LiveRoster({ sessionId, token, tenantId }: Props) {
  const [data, setData] = useState<SessionStatus | null>(null)
  const [error, setError] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const poll = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/attendance/wifi/sessions/${sessionId}`, {
        headers: { Authorization: `Bearer ${token}`, 'X-Tenant-ID': tenantId },
      })
      if (res.ok) {
        setData(await res.json())
        setError(false)
      } else {
        setError(true)
      }
    } catch {
      setError(true)
    }
  }

  useEffect(() => {
    poll()
    intervalRef.current = setInterval(poll, POLL_INTERVAL)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [sessionId])

  if (!data) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
        {error ? 'Could not load roster' : 'Loading roster…'}
      </div>
    )
  }

  const present = data.roster.filter((r) => r.status === 'PRESENT').length
  const pending = data.roster.filter((r) => r.status === 'PENDING').length

  return (
    <div>
      {/* Summary */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 10, padding: '0 2px' }}>
        <Pill label="Present" value={present} color="#1D9E75" />
        <Pill label="Waiting" value={pending} color="#475569" />
        <Pill label="Mismatch" value={data.roster.filter(r => r.status === 'IP_MISMATCH').length} color="#fbbf24" />
        <Pill label="Total" value={data.student_count} color="#64748b" />
      </div>

      {/* Roster */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {data.roster.map((student) => {
          const cfg = STATUS_CONFIG[student.status] ?? STATUS_CONFIG.PENDING
          const Icon = cfg.icon
          return (
            <div key={student.student_id} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '8px 12px', borderRadius: 8,
              background: 'var(--bg-card)', border: '1px solid var(--border)',
            }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)' }}>{student.full_name}</div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{student.roll_number}</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, color: cfg.color, fontSize: 11 }}>
                <Icon size={13} />
                {cfg.label}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Pill({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: 16, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 9, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
    </div>
  )
}
