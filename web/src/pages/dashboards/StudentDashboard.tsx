/** StudentDashboard — §8.6 — ZERO MOCK DATA */

import { useState, useEffect } from 'react'
import { useAuthStore } from '../../store/authStore'
import { MetricCard } from '../../components/ui/MetricCard'
import { SectionCard } from '../../components/ui/SectionCard'
import { ApprovalQueueItem } from '../../components/ui/ApprovalQueueItem'
import {
  fetchDashboardKPIs, fetchApprovals,
  EmptyState, type DashboardMetric, type QueueItem,
} from '../../lib/dashboard-api'

const EMPTY_METRICS: DashboardMetric[] = [
  { label: 'Attendance', value: '\u2014', delta: '', deltaVariant: 'neutral' },
  { label: 'CGPA', value: '\u2014', delta: '', deltaVariant: 'neutral' },
  { label: 'Fee Due', value: '\u2014', delta: '', deltaVariant: 'neutral' },
  { label: 'Library', value: '\u2014', delta: '', deltaVariant: 'neutral' },
]

export function StudentDashboard() {
  const { user } = useAuthStore()
  const [metrics, setMetrics] = useState<DashboardMetric[]>(EMPTY_METRICS)
  const [approvals, setApprovals] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetchDashboardKPIs('STUDENT'),
      fetchApprovals('role=STUDENT'),
    ]).then(([kpis, apprs]) => {
      if (kpis && Object.keys(kpis).length > 0) {
        setMetrics([
          { label: 'Attendance', value: kpis.attendance ? `${kpis.attendance}%` : '\u2014', delta: String(kpis.att_delta ?? ''), deltaVariant: 'negative', urgent: true },
          { label: 'CGPA', value: String(kpis.cgpa ?? '\u2014'), delta: String(kpis.cgpa_delta ?? ''), deltaVariant: 'neutral' },
          { label: 'Fee Due', value: String(kpis.fee_due ?? '\u2014'), delta: String(kpis.fee_delta ?? ''), deltaVariant: 'positive' },
          { label: 'Library', value: String(kpis.library_books ?? '\u2014'), delta: String(kpis.lib_delta ?? ''), deltaVariant: 'neutral' },
        ])
      }
      setApprovals(apprs)
    }).finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <header style={{ padding: '16px 20px', background: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 500, color: 'var(--color-text-primary)' }}>My Dashboard</h1>
          <p style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2 }}>{user?.display_name ?? 'Student'}</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-surface)', cursor: 'pointer', fontSize: 12, fontWeight: 500 }}>Pay Fees</button>
          <button style={{ padding: '6px 14px', borderRadius: 6, border: 'none', background: 'var(--color-primary)', color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 500 }}>Raise Grievance</button>
        </div>
      </header>

      <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {metrics.map((m, i) => <MetricCard key={i} label={m.label} value={m.value} delta={m.delta} deltaVariant={m.deltaVariant} urgent={m.urgent} />)}
        </div>

        <SectionCard title="Pending Actions" action={{ label: 'View all', onClick: () => {} }}>
          {loading ? <EmptyState message="Loading..." /> :
           approvals.length === 0 ? <EmptyState message="No pending actions." /> :
           approvals.map(item => <ApprovalQueueItem key={item.id} tag={item.tag} title={item.title} subtitle={item.subtitle} meta={item.meta} status={item.status} onView={() => {}} />)}
        </SectionCard>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <SectionCard title="Today's Classes">
            <div style={{ padding: '12px 16px' }}>
              <EmptyState message="No data available." />
            </div>
          </SectionCard>

          <SectionCard title="Course-wise Attendance">
            <div style={{ padding: '12px 16px' }}>
              <EmptyState message="No data available." />
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  )
}
