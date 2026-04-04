/**
 * HRDashboard — HR Manager view
 * Shows: staff overview, pending approvals, recruitment, training reminders
 */

import { useState, useEffect } from 'react'
import { StatsRow } from '../components/StatCard'

const API = import.meta.env.VITE_API_URL || "/api/v1";

const EMPTY_STATS = [
  { label: 'Active Staff', value: '—', delta: '' },
  { label: 'Open Vacancies', value: '—', delta: '' },
  { label: 'Pending Leaves', value: '—', delta: '' },
  { label: 'Training Due', value: '—', delta: '' },
]

export function HRDashboard() {
  const [stats, setStats] = useState(EMPTY_STATS)

  useEffect(() => {
    const token = sessionStorage.getItem("token")
    if (!token) return
    fetch(`${API}/reports/dashboard/kpis`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : {})
      .then(kpis => {
        setStats([
          { label: 'Active Staff', value: String(kpis.active_staff ?? '—'), delta: kpis.staff_delta ?? '' },
          { label: 'Open Vacancies', value: String(kpis.open_vacancies ?? '—'), delta: kpis.vacancy_delta ?? '', deltaColor: '#EF9F27' },
          { label: 'Pending Leaves', value: String(kpis.pending_leaves ?? '—'), delta: kpis.leave_delta ?? '' },
          { label: 'Training Due', value: String(kpis.training_due ?? '—'), delta: kpis.training_delta ?? '', deltaColor: '#E24B4A' },
        ])
      })
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <h1 style={{ fontSize: 15, fontWeight: 600 }}>HR Dashboard</h1>
        <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
          Staff management overview
        </p>
      </div>
      <StatsRow stats={stats} />
      <p style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: 20, fontSize: 13 }}>
        Navigate to HR, Recruitment, or Training from the sidebar for detailed views.
      </p>
    </div>
  )
}
