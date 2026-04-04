/**
 * FinanceDashboard — fee defaulter table + collection overview
 * Reference: ALIS-skills/references/frontend.md §11
 *
 * Density: high (Finance role — 8-row tables)
 * Default view: fee_dashboard
 */

import { useState, useEffect } from 'react'
import { useALISStore } from '../store/alis.store'
import { StatsRow } from '../components/StatCard'
import { DataTable, type Column } from '../components/DataTable'
import { Badge } from '../components/Badge'
import { ALISTabs, ALISTabsList, ALISTabsTrigger, ALISTabsContent } from '../components/ui/alis-tabs'

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

interface Defaulter {
  id: string
  name: string
  rollNo: string
  programme: string
  dueAmount: number
  dueSince: string
  installment: string
  status: 'overdue' | 'partial' | 'notice_sent'
}

const API_BASE = import.meta.env.VITE_API_URL || "/api/v1";

const STATUS_BADGE: Record<Defaulter['status'], 'red' | 'amber' | 'blue'> = {
  overdue: 'red',
  partial: 'amber',
  notice_sent: 'blue',
}

const STATUS_LABEL: Record<Defaulter['status'], string> = {
  overdue: 'Overdue',
  partial: 'Partial',
  notice_sent: 'Notice sent',
}

const EMPTY_STATS = [
  { label: 'Total dues', value: '—', delta: '', deltaColor: '#94a3b8' },
  { label: 'Collected this month', value: '—', delta: '', deltaColor: '#94a3b8' },
  { label: 'Invoices overdue', value: '—', delta: '', deltaColor: '#94a3b8' },
  { label: 'Scholarships pending', value: '—', delta: '', deltaColor: '#94a3b8' },
]

const DEFAULTER_COLUMNS: Column<Defaulter>[] = [
  { key: 'name', label: 'Student', width: '2fr' },
  { key: 'rollNo', label: 'Roll No', width: '90px' },
  { key: 'programme', label: 'Programme', width: '1.5fr' },
  {
    key: 'dueAmount',
    label: 'Due amount',
    width: '100px',
    render: (row) => (
      <span style={{ fontSize: 12, fontWeight: 600, color: '#E24B4A' }}>
        ₹{row.dueAmount.toLocaleString('en-IN')}
      </span>
    ),
  },
  { key: 'dueSince', label: 'Due since', width: '1fr' },
  { key: 'installment', label: 'Installment', width: '2fr' },
  {
    key: 'status',
    label: 'Status',
    width: '100px',
    render: (row) => (
      <Badge variant={STATUS_BADGE[row.status]}>{STATUS_LABEL[row.status]}</Badge>
    ),
  },
]

// ---------------------------------------------------------------------------

export function FinanceDashboard() {
  const { canvas, highlightItem } = useALISStore()
  const [defaulters, setDefaulters] = useState<Defaulter[]>([])
  const [stats, setStats] = useState(EMPTY_STATS)
  const [collectionMonths, setCollectionMonths] = useState<{ month: string; amount: number }[]>([])

  useEffect(() => {
    const token = sessionStorage.getItem("token");
    if (!token) return;
    const headers = { Authorization: `Bearer ${token}` };
    Promise.allSettled([
      fetch(`${API_BASE}/finance/fee-defaulters?limit=20`, { headers }),
      fetch(`${API_BASE}/reports/dashboard/kpis`, { headers }),
      fetch(`${API_BASE}/finance/collection-trend`, { headers }),
    ]).then(async ([defRes, kpiRes, trendRes]) => {
      if (defRes.status === "fulfilled" && defRes.value.ok) {
        const data = await defRes.value.json();
        setDefaulters((data.items ?? data ?? []).map((d: Record<string, unknown>) => ({
          id: String(d.id ?? ""), name: String(d.name ?? d.student_name ?? ""),
          rollNo: String(d.roll_no ?? d.rollNo ?? ""), programme: String(d.programme ?? d.program ?? ""),
          dueAmount: Number(d.due_amount ?? d.dueAmount ?? 0), dueSince: String(d.due_since ?? d.dueSince ?? ""),
          installment: String(d.installment ?? d.description ?? ""), status: String(d.status ?? "overdue") as Defaulter["status"],
        })));
      }
      if (kpiRes.status === "fulfilled" && kpiRes.value.ok) {
        const kpis = await kpiRes.value.json();
        setStats([
          { label: 'Total dues', value: kpis.total_dues ?? '—', delta: kpis.defaulter_count ? `${kpis.defaulter_count} defaulters` : '', deltaColor: '#E24B4A' },
          { label: 'Collected this month', value: kpis.collected_this_month ?? '—', delta: kpis.collection_delta ?? '', deltaColor: '#1D9E75' },
          { label: 'Invoices overdue', value: String(kpis.invoices_overdue ?? '—'), delta: kpis.overdue_delta ?? '', deltaColor: '#EF9F27' },
          { label: 'Scholarships pending', value: kpis.scholarships_pending ?? '—', delta: kpis.scholarship_delta ?? '', deltaColor: '#94a3b8' },
        ]);
      }
      if (trendRes.status === "fulfilled" && trendRes.value.ok) {
        const trend = await trendRes.value.json();
        setCollectionMonths((trend.items ?? trend ?? []).map((m: Record<string, unknown>) => ({
          month: String(m.month ?? ""), amount: Number(m.amount ?? 0),
        })));
      }
    });
  }, [])

  const totalDue = defaulters.reduce((sum, d) => sum + d.dueAmount, 0)
  const overdueCount = defaulters.filter((d) => d.status === 'overdue').length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 15, fontWeight: 600, color: 'var(--color-text-primary)', letterSpacing: '-0.01em' }}>
            Finance Dashboard
          </h1>
          <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
            AY 2025–26 · Semester 5
          </p>
        </div>
        <span style={{ fontSize: 10, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--color-text-secondary)' }}>
          Finance view
        </span>
      </div>

      {/* Stats */}
      <StatsRow stats={stats} />

      {/* Tabs */}
      <ALISTabs defaultValue="defaulters">
        <ALISTabsList>
          <ALISTabsTrigger value="defaulters" badge={overdueCount}>Defaulters</ALISTabsTrigger>
          <ALISTabsTrigger value="collection">Collection trend</ALISTabsTrigger>
        </ALISTabsList>

        <ALISTabsContent value="defaulters">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 8,
            }}
          >
            <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>
              Total outstanding: <strong style={{ color: '#E24B4A' }}>₹{totalDue.toLocaleString('en-IN')}</strong>
            </span>
            <button
              className="transition-colors duration-150"
              style={{
                padding: '4px 10px',
                fontSize: 11,
                fontWeight: 500,
                background: 'rgba(29,158,117,0.08)',
                border: '0.5px solid rgba(29,158,117,0.2)',
                borderRadius: 'var(--radius-sm)',
                color: '#1D9E75',
                cursor: 'pointer',
              }}
            >
              Send bulk notice
            </button>
          </div>
          <DataTable
            columns={DEFAULTER_COLUMNS}
            rows={defaulters}
            highlightedId={canvas.highlightedItemId}
            onRowClick={(row) => highlightItem(row.id)}
            gridTemplateColumns="2fr 90px 1.5fr 100px 1fr 2fr 100px"
          />
        </ALISTabsContent>

        <ALISTabsContent value="collection">
          <div
            style={{
              background: 'var(--color-background-secondary)',
              border: 'var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: '16px',
            }}
          >
            <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 16 }}>
              Fee collection (₹ Lakhs) — last 5 months
            </p>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, height: 120 }}>
              {collectionMonths.map((m, idx) => {
                const maxAmt = Math.max(...collectionMonths.map(x => x.amount), 1)
                const h = (m.amount / maxAmt) * 100
                const isLatest = m.month === 'Feb'
                return (
                  <div
                    key={m.month}
                    className="group/bar"
                    style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1 }}
                  >
                    <span
                      className="transition-all duration-200 group-hover/bar:text-[#e2e8f0]"
                      style={{
                        fontSize: 10,
                        color: isLatest ? 'var(--alis-teal)' : 'var(--color-text-secondary)',
                        fontWeight: isLatest ? 600 : 400,
                        marginBottom: 4,
                      }}
                    >
                      {m.amount}L
                    </span>
                    <div
                      className="transition-all duration-300 ease-out group-hover/bar:scale-x-110"
                      style={{
                        width: '100%',
                        height: `${h}%`,
                        background: isLatest ? 'var(--alis-teal)' : 'rgba(29,158,117,0.3)',
                        borderRadius: '4px 4px 0 0',
                        minHeight: 4,
                        animationDelay: `${idx * 100}ms`,
                      }}
                    />
                    <span style={{ fontSize: 10, color: 'var(--color-text-secondary)', marginTop: 4 }}>
                      {m.month}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </ALISTabsContent>
      </ALISTabs>
    </div>
  )
}
