/**
 * SessionCard — displays session token, SSID, password, and countdown timer.
 * Faculty shows this on their screen; students connect to the hotspot and enter the token.
 */
import { useState, useEffect } from 'react'
import { Wifi, Key, Clock } from 'lucide-react'

interface Props {
  token: string
  ssid: string
  wifiPassword: string
  durationMinutes: number
  startedAt: string   // ISO timestamp
}

export function SessionCard({ token, ssid, wifiPassword, durationMinutes, startedAt }: Props) {
  const [secondsLeft, setSecondsLeft] = useState(() => {
    const elapsed = (Date.now() - new Date(startedAt).getTime()) / 1000
    return Math.max(0, durationMinutes * 60 - elapsed)
  })

  useEffect(() => {
    const id = setInterval(() => {
      setSecondsLeft((s) => Math.max(0, s - 1))
    }, 1000)
    return () => clearInterval(id)
  }, [])

  const mins = Math.floor(secondsLeft / 60)
  const secs = Math.floor(secondsLeft % 60)
  const expired = secondsLeft === 0
  const pct = Math.max(0, secondsLeft / (durationMinutes * 60))

  return (
    <div className="card" style={{ textAlign: 'center' }}>
      {/* Session token — large and readable */}
      <div style={{ marginBottom: 6, fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
        Session Token
      </div>
      <div style={{
        fontSize: 42, fontWeight: 900, letterSpacing: '0.3em',
        color: expired ? 'var(--text-muted)' : 'var(--green)',
        fontVariantNumeric: 'tabular-nums', lineHeight: 1,
        marginBottom: 20,
      }}>
        {token}
      </div>

      {/* Countdown ring / bar */}
      <div style={{ marginBottom: 16 }}>
        <div style={{
          height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.06)',
          overflow: 'hidden', marginBottom: 6,
        }}>
          <div style={{
            height: '100%', borderRadius: 2,
            width: `${pct * 100}%`,
            background: expired ? 'var(--red)' : pct < 0.25 ? 'var(--amber)' : 'var(--green)',
            transition: 'width 1s linear, background 0.3s',
          }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, fontSize: 12, color: expired ? 'var(--red)' : 'var(--text-muted)' }}>
          <Clock size={11} />
          {expired ? 'Session expired' : `${mins}:${String(secs).padStart(2, '0')} remaining`}
        </div>
      </div>

      {/* SSID + password */}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
        <InfoChip icon={<Wifi size={11} />} label="SSID" value={ssid} />
        <InfoChip icon={<Key size={11} />} label="Password" value={wifiPassword} />
      </div>

      <div style={{ marginTop: 12, fontSize: 10, color: 'var(--text-muted)' }}>
        Students connect to <strong style={{ color: 'var(--text)' }}>{ssid}</strong> then open ALIS and enter the token above
      </div>
    </div>
  )
}

function InfoChip({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div style={{
      padding: '6px 12px', borderRadius: 8,
      background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)',
      minWidth: 100,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 2, color: 'var(--text-muted)', fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        {icon} {label}
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', wordBreak: 'break-all' }}>{value || '—'}</div>
    </div>
  )
}
