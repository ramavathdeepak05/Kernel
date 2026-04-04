/** FinanceDashboard — §8.7 — ZERO MOCK DATA */

import { useState, useEffect } from 'react'
import { MetricCard } from '../../components/ui/MetricCard'
import { SectionCard } from '../../components/ui/SectionCard'
import { ApprovalQueueItem } from '../../components/ui/ApprovalQueueItem'
import {
  fetchDashboardKPIs, fetchApprovals,
  EmptyState, type DashboardMetric, type QueueItem,
} from '../../lib/dashboard-api'

const EMPTY_METRICS: DashboardMetric[] = [
  { label: 'Collected', value: '\u2014', delta: '', deltaVariant: 'neutral' },
  { label: 'Overdue Accounts', value: '\u2014', delta: '', deltaVariant: 'neutral' },
  { label: 'Recon Exceptions', value: '\u2014', delta: '', deltaVariant: 'neutral' },
  { label: 'Payroll', value: '\u2014', delta: '', deltaVariant: 'neutral' },
]

export function FinanceDashboard() {
  const [metrics, setMetrics] = useState<DashboardMetric[]>(EMPTY_METRICS)
  const [approvals, setApprovals] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetchDashboardKPIs('FINANCE_OFFICER'),
      fetchApprovals('role=FINANCE_OFFICER'),
    ]).then(([kpis, apprs]) => {
      if (kpis && Object.keys(kpis).length > 0) {
        setMetrics([
          { label: 'Collected', value: String(kpis.collected ?? '\u2014'), delta: String(kpis.collected_delta ?? ''), deltaVariant: 'positive' },
          { label: 'Overdue Accounts', value: String(kpis.overdue_count ?? '\u2014'), delta: String(kpis.overdue_delta ?? ''), deltaVariant: 'negative', urgent: true },
          { label: 'Recon Exceptions', value: String(kpis.recon_exceptions ?? '\u2014'), delta: String(kpis.recon_delta ?? ''), deltaVariant: 'negative', urgent: true },
          { label: 'Payroll', value: String(kpis.payroll_total ?? '\u2014'), delta: String(kpis.payroll_delta ?? ''), deltaVariant: 'neutral' },
        ])
      }
      setApprovals(apprs)
    }).finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <header style={{ padding: '16px 20px', background: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 500, color: 'var(--color-text-primary)' }}>Finance Dashboard</h1>
          <p style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2 }}>Finance Overview</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-surface)', cursor: 'pointer', fontSize: 12, fontWeight: 500 }}>Export Ledger</button>
          <button style={{ padding: '6px 14px', borderRadius: 6, border: 'none', background: 'var(--color-primary)', color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 500 }}>Run Reconciliation</button>
        </div>
      </header>

      <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {metrics.map((m, i) => <MetricCard key={i} label={m.label} value={m.value} delta={m.delta} deltaVariant={m.deltaVariant} urgent={m.urgent} />)}
        </div>

        <SectionCard title="Finance Approval Queue" action={{ label: 'View all', onClick: () => {} }}>
          {loading ? <EmptyState message="Loading..." /> :
           approvals.length === 0 ? <EmptyState message="No pending approvals." /> :
           approvals.map(item => <ApprovalQueueItem key={item.id} tag={item.tag} title={item.title} subtitle={item.subtitle} meta={item.meta} status={item.status} showApproveReject onApprove={() => {}} onReject={() => {}} />)}
        </SectionCard>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <SectionCard title="Bank Reconciliation">
            <div style={{ padding: '12px 16px' }}>
              <EmptyState message="No data available." />
            </div>
          </SectionCard>

          <SectionCard title="Fee Collection Progress">
            <div style={{ padding: '12px 16px' }}>
              <EmptyState message="No data available." />
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  )
}
