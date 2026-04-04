/** FacultyDashboard — §8.5 — ZERO MOCK DATA */

import { useState, useEffect } from 'react'
import { MetricCard } from '../../components/ui/MetricCard'
import { SectionCard } from '../../components/ui/SectionCard'
import { ApprovalQueueItem } from '../../components/ui/ApprovalQueueItem'
import {
  fetchDashboardKPIs, fetchApprovals,
  EmptyState, type DashboardMetric, type QueueItem,
} from '../../lib/dashboard-api'

const EMPTY_METRICS: DashboardMetric[] = [
  { label: "Today's Classes", value: '\u2014', delta: '', deltaVariant: 'neutral' },
  { label: 'Pending Approvals', value: '\u2014', delta: '', deltaVariant: 'neutral' },
  { label: 'Students Below 75%', value: '\u2014', delta: '', deltaVariant: 'neutral' },
  { label: 'IA Submission', value: '\u2014', delta: '', deltaVariant: 'neutral' },
]

export function FacultyDashboard() {
  const [metrics, setMetrics] = useState<DashboardMetric[]>(EMPTY_METRICS)
  const [approvals, setApprovals] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetchDashboardKPIs('FACULTY'),
      fetchApprovals('role=FACULTY'),
    ]).then(([kpis, apprs]) => {
      if (kpis && Object.keys(kpis).length > 0) {
        setMetrics([
          { label: "Today's Classes", value: String(kpis.today_classes ?? '\u2014'), delta: String(kpis.classes_delta ?? ''), deltaVariant: 'neutral' },
          { label: 'Pending Approvals', value: String(kpis.pending_approvals ?? '\u2014'), delta: String(kpis.approvals_delta ?? ''), deltaVariant: 'negative', urgent: true },
          { label: 'Students Below 75%', value: String(kpis.at_risk_count ?? '\u2014'), delta: String(kpis.risk_delta ?? ''), deltaVariant: 'negative', urgent: true },
          { label: 'IA Submission', value: String(kpis.ia_submission ?? '\u2014'), delta: String(kpis.ia_delta ?? ''), deltaVariant: 'negative', urgent: true },
        ])
      }
      setApprovals(apprs)
    }).finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <header style={{ padding: '16px 20px', background: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 500 }}>Faculty Workspace</h1>
          <p style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2 }}>Faculty Dashboard</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-surface)', cursor: 'pointer', fontSize: 12, fontWeight: 500 }}>Download Marksheet</button>
          <button style={{ padding: '6px 14px', borderRadius: 6, border: 'none', background: 'var(--color-primary)', color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 500 }}>Mark Attendance</button>
        </div>
      </header>

      <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {metrics.map((m, i) => <MetricCard key={i} label={m.label} value={m.value} delta={m.delta} deltaVariant={m.deltaVariant} urgent={m.urgent} />)}
        </div>

        <SectionCard title="Approval Queue" action={{ label: 'View all', onClick: () => {} }}>
          {loading ? <EmptyState message="Loading..." /> :
           approvals.length === 0 ? <EmptyState message="No pending approvals." /> :
           approvals.map(item => <ApprovalQueueItem key={item.id} tag={item.tag} title={item.title} subtitle={item.subtitle} meta={item.meta} status={item.status} showApproveReject onApprove={() => {}} onReject={() => {}} />)}
        </SectionCard>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <SectionCard title="Today's Schedule">
            <div style={{ padding: '12px 16px' }}>
              <EmptyState message="No data available." />
            </div>
          </SectionCard>

          <SectionCard title="IA Marks Entry">
            <div style={{ padding: '12px 16px' }}>
              <EmptyState message="No data available." />
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  )
}
