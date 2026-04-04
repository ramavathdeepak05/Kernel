/**
 * IconNav — collapsible left sidebar
 * Collapsed: 52px (icons only)
 * Expanded:  200px (icons + labels) — triggered by hover or pin toggle
 */

import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useALISRole } from '../hooks/useALISRole'
import { MODULE_ICONS, MODULE_LABELS, MODULE_ROUTES } from '../lib/role-config'
import type { ALISModule } from '../lib/canvas-actions'

export function IconNav() {
  const navigate = useNavigate()
  const location = useLocation()
  const { visibleModules } = useALISRole()
  const [hovered, setHovered] = useState(false)
  const [pinned, setPinned] = useState(false)

  const expanded = hovered || pinned

  const isActive = (mod: ALISModule) =>
    location.pathname.startsWith(MODULE_ROUTES[mod])

  return (
    <nav
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        width: expanded ? 200 : 52,
        minWidth: expanded ? 200 : 52,
        display: 'flex',
        flexDirection: 'column',
        alignItems: expanded ? 'flex-start' : 'center',
        borderRight: '0.5px solid rgba(0,0,0,0.08)',
        background: '#ffffff',
        paddingTop: 10,
        paddingBottom: 10,
        paddingLeft: expanded ? 10 : 0,
        paddingRight: expanded ? 10 : 0,
        gap: 2,
        flexShrink: 0,
        height: '100vh',
        position: 'sticky',
        top: 0,
        overflowY: 'auto',
        overflowX: 'hidden',
        transition: 'width 0.22s cubic-bezier(0.4,0,0.2,1), min-width 0.22s cubic-bezier(0.4,0,0.2,1), padding 0.22s cubic-bezier(0.4,0,0.2,1), align-items 0.22s',
        zIndex: 50,
      }}
    >
      {/* ALIS wordmark */}
      <div
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          marginBottom: 14,
          flexShrink: 0,
          paddingLeft: expanded ? 2 : 0,
          justifyContent: expanded ? 'flex-start' : 'center',
          transition: 'padding 0.22s, justify-content 0.22s',
          cursor: pinned ? 'default' : 'pointer',
        }}
        onClick={() => setPinned(p => !p)}
        title={pinned ? 'Unpin sidebar' : 'Pin sidebar open'}
      >
        <div
          style={{
            width: 28,
            height: 28,
            minWidth: 28,
            borderRadius: 5,
            background: '#1D9E75',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 0 12px rgba(29,158,117,0.35)',
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 800, color: '#ffffff', fontFamily: 'var(--font-family-display)' }}>A</span>
        </div>
        <span
          style={{
            fontSize: 13,
            fontWeight: 800,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            color: '#0a0a0a',
            fontFamily: 'var(--font-family-display)',
            whiteSpace: 'nowrap',
            opacity: expanded ? 1 : 0,
            transform: expanded ? 'translateX(0)' : 'translateX(-6px)',
            transition: 'opacity 0.18s 0.04s, transform 0.18s 0.04s',
            pointerEvents: 'none',
            userSelect: 'none',
          }}
        >
          ALIS
        </span>
        {/* Pin indicator dot */}
        {expanded && (
          <div
            style={{
              marginLeft: 'auto',
              marginRight: 4,
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: pinned ? '#1D9E75' : 'rgba(0,0,0,0.12)',
              boxShadow: pinned ? '0 0 6px rgba(29,158,117,0.6)' : 'none',
              transition: 'background 0.15s, box-shadow 0.15s',
              flexShrink: 0,
            }}
            title={pinned ? 'Pinned' : 'Click logo to pin'}
          />
        )}
      </div>

      {/* Divider */}
      <div style={{
        width: expanded ? 'calc(100% - 4px)' : 28,
        height: '0.5px',
        background: 'rgba(0,0,0,0.07)',
        marginBottom: 6,
        flexShrink: 0,
        transition: 'width 0.22s',
        alignSelf: 'center',
      }} />

      {/* Module items */}
      {visibleModules.map((mod: ALISModule) => {
        const active = isActive(mod)
        return (
          <button
            key={mod}
            onClick={() => navigate(MODULE_ROUTES[mod])}
            title={expanded ? undefined : MODULE_LABELS[mod]}
            style={{
              width: expanded ? '100%' : 34,
              height: 34,
              borderRadius: 7,
              display: 'flex',
              alignItems: 'center',
              justifyContent: expanded ? 'flex-start' : 'center',
              gap: 10,
              paddingLeft: expanded ? 8 : 0,
              paddingRight: expanded ? 8 : 0,
              fontSize: 15,
              background: active ? 'rgba(29,158,117,0.12)' : 'transparent',
              color: active ? '#1D9E75' : '#aaaaaa',
              border: active
                ? '0.5px solid rgba(29,158,117,0.28)'
                : '0.5px solid transparent',
              cursor: 'pointer',
              transition: 'all 0.15s',
              flexShrink: 0,
              overflow: 'hidden',
            }}
            onMouseEnter={(e) => {
              if (!active) {
                (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0,0,0,0.05)'
                ;(e.currentTarget as HTMLButtonElement).style.color = '#333'
              }
            }}
            onMouseLeave={(e) => {
              if (!active) {
                (e.currentTarget as HTMLButtonElement).style.background = 'transparent'
                ;(e.currentTarget as HTMLButtonElement).style.color = '#aaaaaa'
              }
            }}
          >
            {/* Icon — fixed width so it doesn't shift */}
            <span style={{ flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', width: 18, fontSize: 15 }}>
              {MODULE_ICONS[mod]}
            </span>

            {/* Label */}
            <span
              style={{
                fontSize: 12,
                fontWeight: active ? 600 : 400,
                letterSpacing: '0.01em',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                opacity: expanded ? 1 : 0,
                transform: expanded ? 'translateX(0)' : 'translateX(-8px)',
                transition: 'opacity 0.16s 0.05s, transform 0.16s 0.05s',
                color: 'inherit',
                fontFamily: 'var(--font-family-sans)',
              }}
            >
              {MODULE_LABELS[mod]}
            </span>
          </button>
        )
      })}
    </nav>
  )
}
