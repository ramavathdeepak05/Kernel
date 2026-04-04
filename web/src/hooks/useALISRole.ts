/**
 * useALISRole — current user's role + canvas density
 *
 * Maps the backend role string (e.g., "SUPER_ADMIN", "FINANCE_OFFICER", "COE")
 * to the frontend ALISRole type used for sidebar filtering + dashboard selection.
 */

import { useAuthStore } from '../store/authStore'
import { ROLE_DENSITY, ROLE_DEFAULT_MODULE, ROLE_DEFAULT_VIEW, ROLE_MODULES } from '../lib/role-config'
import type { ALISRole, Density } from '../lib/role-config'

/**
 * Explicit mapping from backend role strings to frontend ALISRole.
 * Backend roles that don't appear here fall through to the
 * lowercase + underscore normalization below.
 */
const BACKEND_ROLE_MAP: Record<string, ALISRole> = {
  // Exact backend values → frontend role
  SUPER_ADMIN:      'super_admin',
  ADMIN:            'admin',
  REGISTRAR:        'registrar',
  DEAN:             'dean',
  HOD:              'hod',
  FACULTY:          'faculty',
  STUDENT:          'student',
  FINANCE_OFFICER:  'finance',
  COE:              'exam_controller',
  HR_MANAGER:       'hr_manager',
  // Aliases for flexibility
  EXAM_CONTROLLER:  'exam_controller',
  FINANCE:          'finance',
}

export function useALISRole(): {
  role: ALISRole
  density: Density
  defaultView: ReturnType<typeof ROLE_DEFAULT_VIEW[ALISRole]>
  defaultModule: ReturnType<typeof ROLE_DEFAULT_MODULE[ALISRole]>
  visibleModules: ReturnType<typeof ROLE_MODULES[ALISRole]>
} {
  const { user } = useAuthStore()

  const backendRole = (user?.role ?? '').toUpperCase().trim()

  // 1. Try explicit map first
  let role: ALISRole = BACKEND_ROLE_MAP[backendRole] ?? (null as unknown as ALISRole)

  // 2. Fallback: normalize to lowercase and check if it's a valid ALISRole
  if (!role) {
    const normalized = backendRole.toLowerCase().replace(/\s+/g, '_')
    if (Object.keys(ROLE_DENSITY).includes(normalized)) {
      role = normalized as ALISRole
    } else {
      role = 'registrar' // safe default — RBAC still enforces on backend
    }
  }

  return {
    role,
    density: ROLE_DENSITY[role],
    defaultView: ROLE_DEFAULT_VIEW[role],
    defaultModule: ROLE_DEFAULT_MODULE[role],
    visibleModules: ROLE_MODULES[role],
  }
}
