/**
 * ALISShell — three-column layout root
 *
 * Desktop (≥768px):
 * ┌──────┬─────────────────────────────────────┬──────────────────┐
 * │ 52px │          PRIMARY CANVAS             │   AGENT RAIL     │
 * │ Icon │          (flex: 1)                  │   (320px fixed)  │
 * │ nav  │                                     │                  │
 * └──────┴─────────────────────────────────────┴──────────────────┘
 *
 * Mobile (<768px):
 * ┌──────────────────────────────────────────────────────────────┐
 * │ Hamburger header bar                                         │
 * ├──────────────────────────────────────────────────────────────┤
 * │ PRIMARY CANVAS (full width)                                  │
 * │                                                    [FAB ✦]   │
 * └──────────────────────────────────────────────────────────────┘
 * FAB tap → bottom sheet (50vh) with agent chat + quick actions
 *
 * Reference: ALIS-skills/references/frontend.md §1
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { IconNav } from './IconNav'
import { PrimaryCanvas } from './PrimaryCanvas'
import { AgentRail } from './AgentRail/AgentRail'
import { AgentBottomSheet } from './AgentBottomSheet'
import { useALISRole } from '../hooks/useALISRole'
import { useAgentContext } from '../hooks/useAgentContext'
import { useAgentCanvasSync } from '../hooks/useAgentCanvasSync'
import { MODULE_ICONS, MODULE_LABELS, MODULE_ROUTES } from '../lib/role-config'
import { CampusSwitcher } from '../components/CampusSwitcher'

function useMobile() {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < 768 : false
  )
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)')
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mq.addEventListener('change', handler)
    setIsMobile(mq.matches)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return isMobile
}

function MobileHeader({ onHamburger }: { onHamburger: () => void }) {
  return (
    <header
      style={{
        height: 48,
        display: 'flex',
        alignItems: 'center',
        padding: '0 12px',
        borderBottom: 'var(--border)',
        background: 'var(--color-background-primary)',
        gap: 12,
        flexShrink: 0,
        position: 'sticky',
        top: 0,
        zIndex: 100,
      }}
    >
      <button
        onClick={onHamburger}
        aria-label="Open navigation"
        style={{
          width: 36,
          height: 36,
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          gap: 5,
          padding: 6,
          borderRadius: 6,
        }}
      >
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            style={{
              display: 'block',
              height: 2,
              background: 'var(--color-text-primary)',
              borderRadius: 1,
            }}
          />
        ))}
      </button>

      {/* ALIS wordmark */}
      <div
        style={{
          width: 26,
          height: 26,
          borderRadius: 5,
          background: '#1D9E75',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <span style={{ color: '#fff', fontWeight: 700, fontSize: 13 }}>A</span>
      </div>
      <span style={{ fontWeight: 600, fontSize: 14, letterSpacing: 0.5 }}>ALIS</span>
      <div style={{ marginLeft: 'auto' }}>
        <CampusSwitcher compact={false} />
      </div>
    </header>
  )
}

function MobileNavDrawer({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const { visibleModules } = useALISRole()

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.4)',
          zIndex: 200,
        }}
      />
      {/* Drawer */}
      <nav
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          bottom: 0,
          width: 240,
          background: 'var(--color-background-primary)',
          borderRight: 'var(--border)',
          zIndex: 201,
          display: 'flex',
          flexDirection: 'column',
          padding: '16px 0',
          overflowY: 'auto',
        }}
      >
        {/* Wordmark */}
        <div style={{ padding: '0 16px 16px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: 6,
              background: '#1D9E75',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <span style={{ color: '#fff', fontWeight: 700, fontSize: 14 }}>A</span>
          </div>
          <span style={{ fontWeight: 700, fontSize: 15 }}>ALIS</span>
        </div>

        {/* Module list */}
        {visibleModules.map((mod) => {
          const active = location.pathname.startsWith(MODULE_ROUTES[mod])
          return (
            <button
              key={mod}
              onClick={() => {
                navigate(MODULE_ROUTES[mod])
                onClose()
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '10px 16px',
                background: active ? 'var(--color-brand-subtle, rgba(29,158,117,0.12))' : 'none',
                border: 'none',
                cursor: 'pointer',
                width: '100%',
                textAlign: 'left',
                fontSize: 14,
                color: active ? '#1D9E75' : 'var(--color-text-primary)',
                fontWeight: active ? 600 : 400,
              }}
            >
              <span style={{ fontSize: 16, width: 20, textAlign: 'center' }}>
                {MODULE_ICONS[mod]}
              </span>
              <span>{MODULE_LABELS[mod]}</span>
            </button>
          )
        })}
      </nav>
    </>
  )
}

function AgentFAB({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-label="Open ALIS agent"
      style={{
        position: 'fixed',
        bottom: 24,
        right: 20,
        width: 52,
        height: 52,
        borderRadius: '50%',
        background: '#1D9E75',
        border: 'none',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        boxShadow: '0 4px 16px rgba(29,158,117,0.45)',
        zIndex: 150,
        fontSize: 22,
        color: '#fff',
        transition: 'transform 0.15s',
      }}
      onMouseDown={(e) => {
        ;(e.currentTarget as HTMLButtonElement).style.transform = 'scale(0.92)'
      }}
      onMouseUp={(e) => {
        ;(e.currentTarget as HTMLButtonElement).style.transform = 'scale(1)'
      }}
    >
      ✦
    </button>
  )
}

export function ALISShell() {
  const isMobile = useMobile()
  const [navOpen, setNavOpen] = useState(false)
  const [sheetOpen, setSheetOpen] = useState(false)

  const closeNav = useCallback(() => setNavOpen(false), [])
  const closeSheet = useCallback(() => setSheetOpen(false), [])

  // Agent rail intelligence — fires on every canvas view change
  useAgentContext()
  // Sync agent-dispatched CanvasActions to the primary canvas
  useAgentCanvasSync()

  // Desktop layout
  if (!isMobile) {
    return (
      <div
        className="alis-shell"
        style={{
          display: 'grid',
          gridTemplateColumns: '52px 1fr 320px',
          height: '100vh',
          overflow: 'hidden',
          background: 'var(--color-background-primary)',
        }}
      >
        <IconNav />
        <PrimaryCanvas />
        <AgentRail />
      </div>
    )
  }

  // Mobile layout
  return (
    <div
      className="alis-shell alis-shell--mobile"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        overflow: 'hidden',
        background: 'var(--color-background-primary)',
      }}
    >
      <MobileHeader onHamburger={() => setNavOpen(true)} />
      <MobileNavDrawer open={navOpen} onClose={closeNav} />

      {/* Full-width canvas */}
      <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
        <PrimaryCanvas />
        <AgentFAB onClick={() => setSheetOpen(true)} />
      </div>

      {/* Agent bottom sheet */}
      <AgentBottomSheet open={sheetOpen} onClose={closeSheet} />
    </div>
  )
}
