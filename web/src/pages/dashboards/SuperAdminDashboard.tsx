/** SuperAdminDashboard — §8.1 — ZERO MOCK DATA */

import { useState, useEffect } from 'react'
import { MetricCard } from '../../components/ui/MetricCard'
import { AlertBar } from '../../components/ui/AlertBar'
import { SectionCard } from '../../components/ui/SectionCard'
import { TimelineItem } from '../../components/ui/TimelineItem'
import { ApprovalQueueItem } from '../../components/ui/ApprovalQueueItem'
import {
  fetchDashboardKPIs, fetchApprovals, fetchRecentEvents, fetchAlerts,
  EmptyState, type DashboardMetric, type QueueItem, type TimelineEntry, type AlertEntry,
} from '../../lib/dashboard-api'

const EMPTY_METRICS: DashboardMetric[] = [
  { label: 'Total Students', value: '—', delta: '', deltaVariant: 'neutral' },
  { label: 'Active Faculty', value: '—', delta: '', deltaVariant: 'neutral' },
  { label: 'Open Approvals', value: '—', delta: '', deltaVariant: 'neutral', urgent: true },
  { label: 'System Health', value: '—', delta: '', deltaVariant: 'neutral' },
]

export function SuperAdminDashboard() {
  const [metrics, setMetrics] = useState<DashboardMetric[]>(EMPTY_METRICS)
  const [approvals, setApprovals] = useState<QueueItem[]>([])
  const [events, setEvents] = useState<TimelineEntry[]>([])
  const [alerts, setAlerts] = useState<AlertEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetchDashboardKPIs('SUPER_ADMIN'),
      fetchApprovals('limit=10'),
      fetchRecentEvents(5),
      fetchAlerts(),
    ]).then(([kpis, apprs, evts, alrts]) => {
      if (kpis && Object.keys(kpis).length > 0) {
        setMetrics([
          { label: 'Total Students', value: String(kpis.total_students ?? '—'), delta: String(kpis.students_delta ?? ''), deltaVariant: 'positive' },
          { label: 'Active Faculty', value: String(kpis.active_faculty ?? '—'), delta: String(kpis.faculty_delta ?? ''), deltaVariant: 'neutral' },
          { label: 'Open Approvals', value: String(kpis.pending_approvals ?? '—'), delta: String(kpis.approvals_delta ?? ''), deltaVariant: 'negative', urgent: true },
          { label: 'System Health', value: kpis.system_health ? `${kpis.system_health}%` : '—', delta: String(kpis.health_delta ?? ''), deltaVariant: 'positive' },
        ])
      }
      setApprovals(apprs)
      setEvents(evts)
      setAlerts(alrts)
    }).finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <header style={{ padding: '16px 20px', background: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 500, color: 'var(--color-text-primary)' }}>Institution Overview</h1>
          <p style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2 }}>Super Admin · All modules · Real-time</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-surface)', cursor: 'pointer', fontSize: 12, fontWeight: 500 }}>System Settings</button>
          <button style={{ padding: '6px 14px', borderRadius: 6, border: 'none', background: 'var(--color-primary)', color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 500 }}>Audit Log</button>
        </div>
      </header>

      <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {metrics.map((m, i) => <MetricCard key={i} label={m.label} value={m.value} delta={m.delta} deltaVariant={m.deltaVariant} urgent={m.urgent} />)}
        </div>

        <SectionCard title="Pending Approvals — All Modules" action={{ label: 'View all', onClick: () => {} }}>
          {loading ? <EmptyState message="Loading..." /> :
           approvals.length === 0 ? <EmptyState message="No pending approvals." /> :
           approvals.map(item => <ApprovalQueueItem key={item.id} tag={item.tag} title={item.title} subtitle={item.subtitle} meta={item.meta} status={item.status} showApproveReject onApprove={() => {}} onReject={() => {}} />)}
        </SectionCard>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <SectionCard title="Module Health">
            <div style={{ padding: '12px 16px' }}>
              <EmptyState message="No module health data available." />
            </div>
          </SectionCard>
          <SectionCard title="Recent Events">
            {events.length === 0 ? <EmptyState message="No recent events." /> :
             <div style={{ padding: '8px 0' }}>{events.map((e, i) => <TimelineItem key={i} title={e.title} subtitle={e.subtitle} done={e.done} />)}</div>}
          </SectionCard>
        </div>

        {alerts.length > 0 && (
          <SectionCard title="Compliance Alerts">
            <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
              {alerts.map((a, i) => <AlertBar key={i} variant={a.variant}>{a.message}</AlertBar>)}
            </div>
          </SectionCard>
        )}
      </div>
    </div>
  )
}
