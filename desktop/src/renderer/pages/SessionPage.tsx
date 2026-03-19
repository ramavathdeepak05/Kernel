/**
 * SessionPage — Faculty WiFi attendance session management
 *
 * Flow:
 *  1. Mount → POST /attendance/wifi/start → get session_id + token
 *  2. Display SessionCard (token + SSID + countdown)
 *  3. LiveRoster polls every 3s
 *  4. "End Session" → POST .../end → summary screen
 */
import { useState, useEffect, useRef } from 'react'
import { useNavigate, useParams, useLocation } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { ArrowLeft, StopCircle } from 'lucide-react'
import { SessionCard } from '../components/SessionCard'
import { LiveRoster } from '../components/LiveRoster'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

interface Course {
  id: string
  code: string
  name: string
}

interface SessionInfo {
  session_id: string
  session_token: string
  ssid: string
  wifi_password: string
  duration_minutes: number
  started_at: string
}

type Phase = 'starting' | 'active' | 'ended' | 'error'

export default function SessionPage() {
  const { courseId } = useParams<{ courseId: string }>()
  const { state } = useLocation()
  const course: Course = state?.course ?? { id: courseId!, code: '—', name: '—' }
  const navigate = useNavigate()

  const { token, tenantId } = useAuthStore()
  const headers = {
    Authorization: `Bearer ${token}`,
    'X-Tenant-ID': tenantId ?? '',
    'Content-Type': 'application/json',
  }

  const [phase, setPhase] = useState<Phase>('starting')
  const [session, setSession] = useState<SessionInfo | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [ending, setEnding] = useState(false)
  const [summary, setSummary] = useState<{ present: number; absent: number } | null>(null)

  // SSID + password inputs (faculty fills in before starting)
  const [ssid, setSsid] = useState('')
  const [wifiPw, setWifiPw] = useState('')
  const [duration, setDuration] = useState(15)
  const [configDone, setConfigDone] = useState(false)

  const startSession = async () => {
    if (!ssid.trim()) return
    setPhase('starting')
    try {
      const res = await fetch(`${API_BASE}/api/v1/attendance/wifi/start`, {
        method: 'POST', headers,
        body: JSON.stringify({
          course_id: courseId,
          ssid: ssid.trim(),
          wifi_password: wifiPw.trim(),
          duration_minutes: duration,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail ?? 'Failed to start session')
      setSession(data)
      setPhase('active')
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : 'Failed to start')
      setPhase('error')
    }
  }

  const endSession = async () => {
    if (!session) return
    setEnding(true)
    try {
      const res = await fetch(
        `${API_BASE}/api/v1/attendance/wifi/sessions/${session.session_id}/end`,
        { method: 'POST', headers },
      )
      const data = await res.json()
      setSummary({ present: data.present_count, absent: data.absent_count })
      setPhase('ended')
    } catch {
      setErrorMsg('Failed to end session')
    } finally {
      setEnding(false)
    }
  }

  // ── Config screen (before starting) ────────────────────────────────────
  if (!configDone) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh' }}>
        <Header course={course} onBack={() => navigate('/')} />
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
          <div className="card" style={{ width: 380 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 16 }}>
              WiFi Session Setup
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <input value={ssid} onChange={(e) => setSsid(e.target.value)} placeholder="Hotspot SSID (e.g. ALIS-Room12)" />
              <input value={wifiPw} onChange={(e) => setWifiPw(e.target.value)} placeholder="WiFi password (shown to students)" />
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>Duration (min):</span>
                <input
                  type="number" value={duration} min={5} max={120}
                  onChange={(e) => setDuration(Number(e.target.value))}
                  style={{ width: 80 }}
                />
              </div>
              <button
                onClick={() => { setConfigDone(true); startSession() }}
                disabled={!ssid.trim()}
                style={{
                  marginTop: 6, padding: '11px 0', borderRadius: 8, border: 'none',
                  background: ssid.trim() ? 'rgba(29,158,117,0.15)' : 'rgba(255,255,255,0.03)',
                  color: ssid.trim() ? 'var(--green)' : 'var(--text-muted)',
                  fontWeight: 600, fontSize: 13,
                  cursor: ssid.trim() ? 'pointer' : 'not-allowed',
                }}
              >
                Start Attendance Session
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ── Starting ─────────────────────────────────────────────────────────────
  if (phase === 'starting') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh' }}>
        <Header course={course} onBack={() => navigate('/')} />
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
          Starting session…
        </div>
      </div>
    )
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  if (phase === 'error') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh' }}>
        <Header course={course} onBack={() => navigate('/')} />
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12 }}>
          <div style={{ color: 'var(--red)', fontSize: 13 }}>{errorMsg}</div>
          <button onClick={() => { setConfigDone(false); setPhase('starting') }} style={{
            padding: '8px 16px', borderRadius: 8, background: 'rgba(29,158,117,0.10)',
            color: 'var(--green)', border: '1px solid rgba(29,158,117,0.2)', fontSize: 12,
          }}>Try Again</button>
        </div>
      </div>
    )
  }

  // ── Ended — summary ───────────────────────────────────────────────────────
  if (phase === 'ended' && summary) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh' }}>
        <Header course={course} onBack={() => navigate('/')} />
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 20 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>Session Ended</div>
          <div style={{ display: 'flex', gap: 32 }}>
            <Stat label="Present" value={summary.present} color="var(--green)" />
            <Stat label="Absent"  value={summary.absent}  color="var(--red)" />
          </div>
          <button onClick={() => navigate('/')} style={{
            padding: '10px 24px', borderRadius: 8, background: 'rgba(29,158,117,0.12)',
            color: 'var(--green)', border: '1px solid rgba(29,158,117,0.2)', fontWeight: 600, fontSize: 13,
          }}>Back to Courses</button>
        </div>
      </div>
    )
  }

  // ── Active session ────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh' }}>
      <Header course={course} onBack={undefined} />

      <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {session && (
          <SessionCard
            token={session.session_token}
            ssid={session.ssid}
            wifiPassword={session.wifi_password}
            durationMinutes={session.duration_minutes}
            startedAt={session.started_at}
          />
        )}
        {session && <LiveRoster sessionId={session.session_id} token={token!} tenantId={tenantId!} />}
      </div>

      {/* End session button */}
      <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)' }}>
        <button
          onClick={endSession}
          disabled={ending}
          style={{
            width: '100%', padding: '11px 0', borderRadius: 8, border: 'none',
            background: ending ? 'rgba(248,113,113,0.05)' : 'rgba(248,113,113,0.10)',
            color: 'var(--red)', fontWeight: 600, fontSize: 13,
            cursor: ending ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
          }}
        >
          <StopCircle size={14} />
          {ending ? 'Ending…' : 'End Session & Mark Absent'}
        </button>
      </div>
    </div>
  )
}

// ── Small sub-components ──────────────────────────────────────────────────

function Header({ course, onBack }: { course: Course; onBack?: () => void }) {
  return (
    <div style={{
      padding: '12px 16px', borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', gap: 10,
    }}>
      {onBack && (
        <button onClick={onBack} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', padding: 4 }}>
          <ArrowLeft size={16} />
        </button>
      )}
      <div>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{course.code} — {course.name}</div>
        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>WiFi Attendance Session</div>
      </div>
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: 32, fontWeight: 800, color }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
    </div>
  )
}
