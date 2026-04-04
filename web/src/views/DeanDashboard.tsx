/**
 * DeanDashboard — Dean view
 * Shows: academic oversight, pending approvals (clubs, events), OBE status
 */

import { useState, useEffect } from 'react'
import { StatsRow } from '../components/StatCard'

const API = import.meta.env.VITE_API_URL || "/api/v1";

const EMPTY_STATS = [
  { label: 'Programs', value: '—', delta: '' },
  { label: 'Faculty', value: '—', delta: '' },
  { label: 'Pending Approvals', value: '—', delta: '' },
  { label: 'OBE Attainment', value: '—', delta: '' },
]

export function DeanDashboard() {
  const [stats, setStats] = useState(EMPTY_STATS)

  useEffect(() => {
    const token = sessionStorage.getItem("token")
    if (!token) return
    fetch(`${API}/reports/dashboard/kpis`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : {})
      .then(kpis => {
        setStats([
          { label: 'Programs', value: String(kpis.programs ?? '—'), delta: '' },
          { label: 'Faculty', value: String(kpis.faculty_count ?? '—'), delta: kpis.faculty_delta ?? '' },
          { label: 'Pending Approvals', value: String(kpis.pending_approvals ?? '—'), delta: '', deltaColor: '#EF9F27' },
          { label: 'OBE Attainment', value: kpis.obe_attainment ? `${kpis.obe_attainment}%` : '—', delta: kpis.obe_delta ?? '', deltaColor: '#1D9E75' },
        ])
      })
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <h1 style={{ fontSize: 15, fontWeight: 600 }}>Dean Dashboard</h1>
        <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
          Academic oversight
        </p>
      </div>
      <StatsRow stats={stats} />
      <p style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: 20, fontSize: 13 }}>
        Navigate to Academics, Clubs & Events, or Regulatory from the sidebar.
      </p>
    </div>
  )
}
