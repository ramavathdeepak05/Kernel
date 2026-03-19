/**
 * PrimaryCanvas — canvas host, view router, context broadcaster
 * Reference: ALIS-skills/references/frontend.md §7
 *
 * Routes based on URL path. Renders existing page components
 * while the new views/ layer is being built.
 * On every view change, updates agent context label within 100ms.
 */

import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { useALISStore } from '../store/alis.store'
import { useAgentCanvasSync } from '../hooks/useAgentCanvasSync'
import { useALISRole } from '../hooks/useALISRole'
import type { CanvasView, ALISModule } from '../lib/canvas-actions'
import { MODULE_LABELS } from '../lib/role-config'
import { ROLE_DEFAULT_VIEW } from '../lib/role-config'

function getContextLabel(pathname: string, role: string): string {
  const seg = pathname.replace('/', '') || 'dashboard'
  const modLabel = MODULE_LABELS[seg as ALISModule] ?? seg
  return `Watching: ${modLabel}`
}

function getCanvasView(pathname: string): CanvasView {
  if (pathname.startsWith('/finance')) return 'fee_dashboard'
  if (pathname.startsWith('/examinations')) return 'exam_management'
  if (pathname.startsWith('/admissions')) return 'admissions_pipeline'
  if (pathname.startsWith('/academics')) return 'my_courses'
  if (pathname.startsWith('/students')) return 'student_risk'
  if (pathname.startsWith('/regulatory')) return 'regulatory_dashboard'
  if (pathname.startsWith('/hr')) return 'hr_dashboard'
  return 'approval_queue'
}

function getModule(pathname: string): ALISModule {
  const seg = pathname.replace('/', '').split('/')[0] || 'dashboard'
  const modMap: Record<string, ALISModule> = {
    admissions: 'admissions',
    academics: 'academics',
    examinations: 'examinations',
    finance: 'finance',
    hr: 'hr',
    students: 'student_services',
    regulatory: 'regulatory',
    reports: 'reports',
    dashboard: 'dashboard',
    settings: 'settings',
  }
  return modMap[seg] ?? 'dashboard'
}

export function PrimaryCanvas() {
  const { setCanvasView, setAgentContext } = useALISStore()
  const { role } = useALISRole()
  const location = useLocation()

  // Wire agent ↔ canvas sync
  useAgentCanvasSync()

  // Broadcast context on every route change (within 100ms)
  useEffect(() => {
    const view = getCanvasView(location.pathname)
    const module = getModule(location.pathname)
    setCanvasView(view, module)
    setAgentContext(getContextLabel(location.pathname, role))
  }, [location.pathname]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main
      style={{
        flex: 1,
        minWidth: 0,
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--color-background-primary)',
      }}
    >
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '20px 24px',
        }}
      >
        <Outlet />
      </div>
    </main>
  )
}
