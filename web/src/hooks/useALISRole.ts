/**
 * useALISRole — current user's role + canvas density
 * Reference: ALIS-skills/references/frontend.md §3
 */

import { useAuthStore } from '../store/authStore'
import { ROLE_DENSITY, ROLE_DEFAULT_MODULE, ROLE_DEFAULT_VIEW, ROLE_MODULES } from '../lib/role-config'
import type { ALISRole, Density } from '../lib/role-config'

export function useALISRole(): {
  role: ALISRole
  density: Density
  defaultView: ReturnType<typeof ROLE_DEFAULT_VIEW[ALISRole]>
  defaultModule: ReturnType<typeof ROLE_DEFAULT_MODULE[ALISRole]>
  visibleModules: ReturnType<typeof ROLE_MODULES[ALISRole]>
} {
  const { user } = useAuthStore()

  // Map backend role string to our ALISRole type
  const rawRole = (user?.role ?? 'registrar').toLowerCase().replace(/\s+/g, '_')
  const role: ALISRole = (Object.keys(ROLE_DENSITY).includes(rawRole)
    ? rawRole
    : 'registrar') as ALISRole

  return {
    role,
    density: ROLE_DENSITY[role],
    defaultView: ROLE_DEFAULT_VIEW[role],
    defaultModule: ROLE_DEFAULT_MODULE[role],
    visibleModules: ROLE_MODULES[role],
  }
}
