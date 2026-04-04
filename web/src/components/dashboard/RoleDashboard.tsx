/**
 * RoleDashboard — §6 of ALIS_FRONTEND_SPEC.md
 * Switches to the correct dashboard page based on user role.
 */

import { useAuthStore } from '../../store/authStore'
import { BACKEND_ROLE_MAP, type FrontendRole } from '../../config/roleConfig'

import { SuperAdminDashboard } from '../../pages/dashboards/SuperAdminDashboard'
import { RegistrarDashboard }  from '../../pages/dashboards/RegistrarDashboard'
import { DeanDashboard }       from '../../pages/dashboards/DeanDashboard'
import { HODDashboard }        from '../../pages/dashboards/HODDashboard'
import { FacultyDashboard }    from '../../pages/dashboards/FacultyDashboard'
import { StudentDashboard }    from '../../pages/dashboards/StudentDashboard'
import { FinanceDashboard }    from '../../pages/dashboards/FinanceDashboard'
import { CoEDashboard }        from '../../pages/dashboards/CoEDashboard'
import { HRDashboard }         from '../../pages/dashboards/HRDashboard'

const DASHBOARD_MAP: Record<FrontendRole, React.ComponentType> = {
  SUPER_ADMIN:     SuperAdminDashboard,
  REGISTRAR:       RegistrarDashboard,
  DEAN:            DeanDashboard,
  HOD:             HODDashboard,
  FACULTY:         FacultyDashboard,
  STUDENT:         StudentDashboard,
  FINANCE_OFFICER: FinanceDashboard,
  COE:             CoEDashboard,
  HR_MANAGER:      HRDashboard,
}

export function RoleDashboard() {
  const { user } = useAuthStore()
  const backendRole = (user?.role ?? '').toUpperCase().trim()
  const role: FrontendRole = BACKEND_ROLE_MAP[backendRole] ?? 'REGISTRAR'
  const Dashboard = DASHBOARD_MAP[role]

  if (!Dashboard) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-text-secondary)' }}>
        Unknown role: {backendRole}
      </div>
    )
  }

  return <Dashboard />
}
