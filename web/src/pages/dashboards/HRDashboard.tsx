/** HRDashboard — §8.9 — ZERO MOCK DATA */

import { useState, useEffect } from 'react'
import { MetricCard } from '../../components/ui/MetricCard'
import { SectionCard } from '../../components/ui/SectionCard'
import { ApprovalQueueItem } from '../../components/ui/ApprovalQueueItem'
import {
  fetchDashboardKPIs, fetchApprovals,
  EmptyState, type DashboardMetric, type QueueItem,
} from '../../lib/dashboard-api'

const EMPTY_METRICS: DashboardMetric[] = [
  { label: 'Payroll Exceptions', value: '\u2014', delta: '', deltaVariant: 'neutral' },
  { label: 'Leave Approvals', value: '\u2014', delta: '', deltaVariant: 'neutral' },
  { label: 'Open Requisitions', value: '\u2014', delta: '', deltaVariant: 'neutral' },
  { label: 'CAS Due', value: '\u2014', delta: '', deltaVariant: 'neutral' },
]

export function HRDashboard() {
  const [metrics, setMetrics] = useState<DashboardMetric[]>(EMPTY_METRICS)
  const [approvals, setApprovals] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetchDashboardKPIs('HR_MANAGER'),
      fetchApprovals('role=HR_MANAGER'),
    ]).then(([kpis, apprs]) => {
      if (kpis && Object.keys(kpis).length > 0) {
        setMetrics([
          { label: 'Payroll Exceptions', value: String(kpis.payroll_exceptions ?? '\u2014'), delta: String(kpis.payroll_delta ?? ''), deltaVariant: 'negative', urgent: true },
          { label: 'Leave Approvals', value: String(kpis.leave_approvals ?? '\u2014'), delta: String(kpis.leave_delta ?? ''), deltaVariant: 'negative', urgent: true },
          { label: 'Open Requisitions', value: String(kpis.open_requisitions ?? '\u2014'), delta: String(kpis.req_delta ?? ''), deltaVariant: 'neutral' },
          { label: 'CAS Due', value: String(kpis.cas_due ?? '\u2014'), delta: String(kpis.cas_delta ?? ''), deltaVariant: 'neutral' },
        ])
      }
      setApprovals(apprs)
    }).finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <header style={{ padding: '16px 20px', background: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 500, color: 'var(--color-text-primary)' }}>HR & Payroll Dashboard</h1>
          <p style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2 }}>Human Resources Overview</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-surface)', cursor: 'pointer', fontSize: 12, fontWeight: 500 }}>Payroll Report</button>
          <button style={{ padding: '6px 14px', borderRadius: 6, border: 'none', background: 'var(--color-primary)', color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 500 }}>Run Payroll</button>
        </div>
      </header>

      <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {metrics.map((m, i) => <MetricCard key={i} label={m.label} value={m.value} delta={m.delta} deltaVariant={m.deltaVariant} urgent={m.urgent} />)}
        </div>

        <SectionCard title="Payroll Exceptions Queue" action={{ label: 'View all', onClick: () => {} }}>
          {loading ? <EmptyState message="Loading..." /> :
           approvals.length === 0 ? <EmptyState message="No pending exceptions." /> :
           approvals.map(item => <ApprovalQueueItem key={item.id} tag={item.tag} title={item.title} subtitle={item.subtitle} meta={item.meta} status={item.status} showApproveReject onApprove={() => {}} onReject={() => {}} />)}
        </SectionCard>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <SectionCard title="Recruitment Pipeline">
            <div style={{ padding: '12px 16px' }}>
              <EmptyState message="No data available." />
            </div>
          </SectionCard>

          <SectionCard title="Statutory Compliance">
            <div style={{ padding: '12px 16px' }}>
              <EmptyState message="No data available." />
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  )
}
