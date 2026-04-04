/**
 * RoleSwitch — renders different views based on the current user's role.
 *
 * Usage:
 *   <RoleSwitch
 *     student={<StudentAcademicsView />}
 *     faculty={<FacultyAcademicsView />}
 *     hod={<HODAcademicsView />}
 *     default={<AdminAcademicsView />}
 *   />
 *
 * If the current role has no matching prop, falls back to `default`.
 * If no `default`, renders null.
 */

import type { ReactElement } from 'react'
import { useALISRole } from '../hooks/useALISRole'
import type { ALISRole } from '../lib/role-config'

type RoleSwitchProps = Partial<Record<ALISRole, ReactElement>> & {
  default?: ReactElement
}

export function RoleSwitch(props: RoleSwitchProps) {
  const { role } = useALISRole()
  return props[role] ?? props.default ?? null
}
