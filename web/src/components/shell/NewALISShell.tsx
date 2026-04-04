/**
 * ALISShell — 3-column layout per §5.1 of ALIS_FRONTEND_SPEC.md
 *
 * Nav (56px→220px) | Canvas (flex:1) | AgentRail (320px)
 * Full viewport height, each column scrolls independently.
 */

import { Outlet } from 'react-router-dom'
import { NewIconNav } from './NewIconNav'
import { NewAgentRail } from './NewAgentRail'
import { BACKEND_ROLE_MAP, type FrontendRole } from '../../config/roleConfig'
import { useAuthStore } from '../../store/authStore'

export function NewALISShell() {
  const { user } = useAuthStore()
  const backendRole = (user?.role ?? '').toUpperCase().trim()
  const role: FrontendRole = BACKEND_ROLE_MAP[backendRole] ?? 'REGISTRAR'

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <NewIconNav role={role} />
      <main style={{
        flex: 1, overflowY: 'auto',
        background: 'var(--color-bg-page)',
      }}>
        <Outlet />
      </main>
      <NewAgentRail role={role} />
    </div>
  )
}
