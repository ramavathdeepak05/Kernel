/**
 * IconNav — 52px left sidebar with role-adaptive module icons
 * Reference: ALIS-skills/references/frontend.md §13
 *
 * Only shows modules the current role has permission to access.
 * ALIS wordmark: 28×28 teal square with white "A".
 */

import { useNavigate, useLocation } from 'react-router-dom'
import { useALISRole } from '../hooks/useALISRole'
import { MODULE_ICONS, MODULE_LABELS, MODULE_ROUTES } from '../lib/role-config'
import type { ALISModule } from '../lib/canvas-actions'

export function IconNav() {
  const navigate = useNavigate()
  const location = useLocation()
  const { visibleModules } = useALISRole()

  const isActive = (mod: ALISModule) =>
    location.pathname.startsWith(MODULE_ROUTES[mod])

  return (
    <nav
      style={{
        width: 52,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        borderRight: 'var(--border)',
        background: 'var(--color-background-primary)',
        paddingTop: 8,
        paddingBottom: 8,
        gap: 2,
        flexShrink: 0,
        height: '100vh',
        position: 'sticky',
        top: 0,
        overflowY: 'auto',
      }}
    >
      {/* ALIS wordmark */}
      <div
        style={{
          width: 28,
          height: 28,
          borderRadius: 6,
          background: '#1D9E75',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: 12,
          flexShrink: 0,
        }}
      >
        <span style={{ fontSize: 14, fontWeight: 700, color: '#fff' }}>A</span>
      </div>

      {/* Module icons */}
      {visibleModules.map((mod) => {
        const active = isActive(mod)
        return (
          <button
            key={mod}
            onClick={() => navigate(MODULE_ROUTES[mod])}
            title={MODULE_LABELS[mod]}
            style={{
              width: 36,
              height: 36,
              borderRadius: 8,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 16,
              background: active ? 'rgba(29,158,117,0.12)' : 'transparent',
              color: active ? '#1D9E75' : '#94a3b8',
              border: active
                ? '0.5px solid rgba(29,158,117,0.3)'
                : '0.5px solid transparent',
              cursor: 'pointer',
              transition: 'background 0.12s, color 0.12s',
              flexShrink: 0,
            }}
            onMouseEnter={(e) => {
              if (!active) {
                (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.04)'
                ;(e.currentTarget as HTMLButtonElement).style.color = '#e2e8f0'
              }
            }}
            onMouseLeave={(e) => {
              if (!active) {
                (e.currentTarget as HTMLButtonElement).style.background = 'transparent'
                ;(e.currentTarget as HTMLButtonElement).style.color = '#94a3b8'
              }
            }}
          >
            {MODULE_ICONS[mod]}
          </button>
        )
      })}
    </nav>
  )
}
