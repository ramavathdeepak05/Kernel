import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore, type AuthState } from '../store/authStore'

// Backend URL — in production this is configurable via an env var
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export default function LoginPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s: AuthState) => s.setAuth)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [tenantSlug, setTenantSlug] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleLogin = async () => {
    if (!email.trim() || !password || !tenantSlug.trim()) {
      setError('All fields are required')
      return
    }
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), password, tenant_slug: tenantSlug.trim() }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail ?? 'Login failed')
        return
      }
      setAuth(data.access_token, data.tenant_id, data.user)
      navigate('/', { replace: true })
    } catch {
      setError('Cannot connect to ALIS server. Check your network.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '100dvh', background: 'var(--bg)',
    }}>
      <div className="card" style={{ width: 360 }}>
        {/* Logo / title */}
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{
            width: 48, height: 48, borderRadius: 14, margin: '0 auto 12px',
            background: 'var(--green-bg)', border: '1px solid rgba(29,158,117,0.25)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 22, fontWeight: 800, color: 'var(--green)',
          }}>A</div>
          <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text)' }}>ALIS Attendance</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>Faculty WiFi Session Tool</div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <input
            value={tenantSlug}
            onChange={(e) => setTenantSlug(e.target.value)}
            placeholder="Institution slug (e.g. woxsen)"
            autoComplete="off"
          />
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Faculty email"
            autoComplete="username"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            autoComplete="current-password"
            onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
          />

          {error && (
            <div style={{ fontSize: 11, color: 'var(--red)', padding: '6px 0' }}>{error}</div>
          )}

          <button
            onClick={handleLogin}
            disabled={loading}
            style={{
              marginTop: 4, padding: '11px 0', borderRadius: 8, border: 'none',
              background: loading ? 'rgba(29,158,117,0.08)' : 'rgba(29,158,117,0.15)',
              color: 'var(--green)', fontWeight: 600, fontSize: 13,
              cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'background 0.12s',
            }}
          >
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </div>

        <div style={{ marginTop: 16, fontSize: 10, color: 'var(--text-muted)', textAlign: 'center' }}>
          ALIS Desktop v1.0 · QUAICU Pvt. Ltd.
        </div>
      </div>
    </div>
  )
}
