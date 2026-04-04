/** DeanDashboard — §8.3 — ZERO MOCK DATA */

import { useState, useEffect } from 'react'
import { MetricCard } from '../../components/ui/MetricCard'
import { SectionCard } from '../../components/ui/SectionCard'
import { ApprovalQueueItem } from '../../components/ui/ApprovalQueueItem'
import {
  fetchDashboardKPIs, fetchApprovals,
  EmptyState, type DashboardMetric, type QueueItem,
} from '../../lib/dashboard-api'

const EMPTY_METRICS: DashboardMetric[] = [
  { label: 'Departments', value: '\u2014', delta: '', deltaVariant: 'neutral' },
  { label: 'Escalated to Me', value: '\u2014', delta: '', deltaVariant: 'neutral' },
  { label: 'Scholarship Pending', value: '\u2014', delta: '', deltaVariant: 'neutral' },
  { label: 'Faculty Vacancies', value: '\u2014', delta: '', deltaVariant: 'neutral' },
]

export function DeanDashboard() {
  const [metrics, setMetrics] = useState<DashboardMetric[]>(EMPTY_METRICS)
  const [approvals, setApprovals] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetchDashboardKPIs('DEAN'),
      fetchApprovals('role=DEAN'),
    ]).then(([kpis, apprs]) => {
      if (kpis && Object.keys(kpis).length > 0) {
        setMetrics([
          { label: 'Departments', value: String(kpis.departments ?? '\u2014'), delta: String(kpis.dept_delta ?? ''), deltaVariant: 'neutral' },
          { label: 'Escalated to Me', value: String(kpis.escalated ?? '\u2014'), delta: String(kpis.escalated_delta ?? ''), deltaVariant: 'negative', urgent: true },
          { label: 'Scholarship Pending', value: String(kpis.scholarship_pending ?? '\u2014'), delta: String(kpis.scholarship_delta ?? ''), deltaVariant: 'negative', urgent: true },
          { label: 'Faculty Vacancies', value: String(kpis.vacancies ?? '\u2014'), delta: String(kpis.vacancy_delta ?? ''), deltaVariant: 'neutral' },
        ])
      }
      setApprovals(apprs)
    }).finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <header style={{ padding: '16px 20px', background: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 500, color: 'var(--color-text-primary)' }}>Dean — Academic & Student Affairs</h1>
          <p style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2 }}>Academic Overview</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-surface)', cursor: 'pointer', fontSize: 12, fontWeight: 500 }}>Academic Calendar</button>
          <button style={{ padding: '6px 14px', borderRadius: 6, border: 'none', background: 'var(--color-primary)', color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 500 }}>Schedule Committee</button>
        </div>
      </header>

      <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {metrics.map((m, i) => <MetricCard key={i} label={m.label} value={m.value} delta={m.delta} deltaVariant={m.deltaVariant} urgent={m.urgent} />)}
        </div>

        <SectionCard title="Escalated Approvals" action={{ label: 'View all', onClick: () => {} }}>
          {loading ? <EmptyState message="Loading..." /> :
           approvals.length === 0 ? <EmptyState message="No escalated approvals." /> :
           approvals.map(item => <ApprovalQueueItem key={item.id} tag={item.tag} title={item.title} subtitle={item.subtitle} meta={item.meta} status={item.status} showApproveReject onApprove={() => {}} onReject={() => {}} />)}
        </SectionCard>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <SectionCard title="Department Performance">
            <div style={{ padding: '12px 16px' }}>
              <EmptyState message="No data available." />
            </div>
          </SectionCard>

          <SectionCard title="Academic Committee Actions">
            <div style={{ padding: '12px 16px' }}>
              <EmptyState message="No data available." />
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  )
}
