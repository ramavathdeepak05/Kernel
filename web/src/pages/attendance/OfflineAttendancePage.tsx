/**
 * OfflineAttendancePage — Route wrapper for the offline-capable attendance view
 *
 * Route: /attendance/mark/:sessionId?courseCode=...&courseName=...&date=...
 * Standalone (no shell). Installable as PWA (feature flag: academics.offline_attendance_pwa).
 */
import { useParams, useSearchParams } from 'react-router-dom'
import { AttendanceMarking } from '../../views/AttendanceMarking'

export function OfflineAttendancePage() {
  const { sessionId = '' } = useParams<{ sessionId: string }>()
  const [params] = useSearchParams()

  return (
    <AttendanceMarking
      sessionId={sessionId}
      courseCode={params.get('courseCode') ?? ''}
      courseName={params.get('courseName') ?? 'Attendance'}
      date={params.get('date') ?? new Date().toISOString().slice(0, 10)}
      tenantId={localStorage.getItem('tenantId') ?? ''}
      authToken={localStorage.getItem('token') ?? ''}
    />
  )
}
