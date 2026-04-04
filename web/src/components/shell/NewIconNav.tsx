/**
 * IconNav — Collapsible icon nav per §5.2 of ALIS_FRONTEND_SPEC.md
 *
 * Collapsed: 56px icons only. Expanded on hover: 220px with labels.
 * Sections from ROLE_NAV. Lucide icons. User avatar at bottom.
 */

import { useLocation, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import * as LucideIcons from 'lucide-react'
import { ROLE_NAV, ROLE_DISPLAY, type FrontendRole, type NavItem } from '../../config/roleConfig'

interface IconNavProps {
  role: FrontendRole
}

function getIcon(name: string, size = 18) {
  const Icon = (LucideIcons as Record<string, React.ComponentType<{ size?: number }>>)[name]
  return Icon ? <Icon size={size} /> : <span style={{ width: size, height: size, display: 'inline-block' }} />
}

export function NewIconNav({ role }: IconNavProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { user } = useAuthStore()
  const sections = ROLE_NAV[role] || []
  const display = ROLE_DISPLAY[role]

  return (
    <nav
      className="group"
      style={{
        width: 'var(--nav-width-collapsed)',
        minWidth: 'var(--nav-width-collapsed)',
        height: '100vh',
        background: 'var(--color-bg-surface)',
        borderRight: '1px solid var(--color-border)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        transition: `width var(--nav-transition)`,
        flexShrink: 0,
        zIndex: 20,
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.width = 'var(--nav-width-expanded)' }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.width = 'var(--nav-width-collapsed)' }}
    >
      {/* Logo */}
      <div style={{ padding: '14px 12px', display: 'flex', alignItems: 'center', gap: 10, borderBottom: '1px solid var(--color-border)', height: 56 }}>
        <div style={{
          width: 28, height: 28, borderRadius: 6,
          background: 'var(--color-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontWeight: 700, fontSize: 13, flexShrink: 0,
        }}>
          A
        </div>
        <span className="nav-label" style={{
          fontWeight: 700, fontSize: 15, color: 'var(--color-text-primary)',
          opacity: 0, transition: 'opacity 150ms', whiteSpace: 'nowrap', overflow: 'hidden',
        }}>
          ALIS OS
        </span>
      </div>

      {/* Nav sections */}
      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '8px 0' }}>
        {sections.map((section, si) => (
          <div key={si} style={{ marginBottom: 8 }}>
            {/* Section header — visible only when expanded */}
            <div className="nav-label" style={{
              padding: '4px 16px', fontSize: 10, fontWeight: 600,
              color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em',
              opacity: 0, transition: 'opacity 150ms', whiteSpace: 'nowrap', height: 20,
            }}>
              {section.section}
            </div>

            {/* Items */}
            {section.items.map((item, ii) => {
              const active = location.pathname === item.path || (item.path !== '/dashboard' && location.pathname.startsWith(item.path))
              return (
                <button
                  key={ii}
                  onClick={() => navigate(item.path)}
                  style={{
                    width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                    padding: '8px 14px', border: 'none', cursor: 'pointer',
                    background: active ? 'var(--color-primary-light)' : 'transparent',
                    color: active ? 'var(--color-primary)' : 'var(--color-text-secondary)',
                    fontSize: 'var(--text-sm)', fontWeight: active ? 600 : 400,
                    borderRadius: 0, position: 'relative',
                    transition: 'background 100ms, color 100ms',
                  }}
                  title={item.label}
                >
                  <span style={{ flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', width: 28 }}>
                    {getIcon(item.icon, 18)}
                  </span>
                  <span className="nav-label" style={{
                    opacity: 0, transition: 'opacity 150ms', whiteSpace: 'nowrap', overflow: 'hidden',
                    flex: 1, textAlign: 'left',
                  }}>
                    {item.label}
                  </span>
                  {item.badge != null && item.badge > 0 && (
                    <span style={{
                      position: 'absolute', top: 6, right: 8,
                      minWidth: 16, height: 16, borderRadius: 8,
                      background: 'var(--color-danger)', color: '#fff',
                      fontSize: 9, fontWeight: 700,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      padding: '0 4px',
                    }}>
                      {item.badge}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        ))}
      </div>

      {/* User avatar at bottom */}
      <div style={{
        padding: '12px 14px', borderTop: '1px solid var(--color-border)',
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <div style={{
          width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
          background: 'var(--color-primary-light)', color: 'var(--color-primary-dark)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 12, fontWeight: 700,
        }}>
          {display?.initials || 'U'}
        </div>
        <div className="nav-label" style={{ opacity: 0, transition: 'opacity 150ms', overflow: 'hidden', whiteSpace: 'nowrap' }}>
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-text-primary)' }}>
            {user?.display_name || user?.username || 'User'}
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>
            {display?.name || role}
          </div>
        </div>
      </div>

      {/* CSS to reveal labels on hover */}
      <style>{`
        nav.group:hover .nav-label { opacity: 1 !important; }
      `}</style>
    </nav>
  )
}
