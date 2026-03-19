/**
 * FinanceDashboard — fee defaulter table + collection overview
 * Reference: ALIS-skills/references/frontend.md §11
 *
 * Density: high (Finance role — 8-row tables)
 * Default view: fee_dashboard
 */

import { useState } from 'react'
import { useALISStore } from '../store/alis.store'
import { StatsRow } from '../components/StatCard'
import { DataTable, type Column } from '../components/DataTable'
import { Badge } from '../components/Badge'

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

const DEFAULTERS: Defaulter[] = [
  { id: 'd01', name: 'Rahul Gupta', rollNo: '22CS012', programme: 'B.Tech CSE', dueAmount: 45000, dueSince: '15 Jan 2026', installment: 'Sem 5 Fee', status: 'overdue' },
  { id: 'd02', name: 'Anjali Verma', rollNo: '22EC034', programme: 'B.Tech ECE', dueAmount: 32000, dueSince: '15 Jan 2026', installment: 'Sem 5 Fee', status: 'notice_sent' },
  { id: 'd03', name: 'Suresh Kumar', rollNo: '21ME009', programme: 'B.Tech ME', dueAmount: 60000, dueSince: '30 Nov 2025', installment: 'Sem 4 + Sem 5', status: 'overdue' },
  { id: 'd04', name: 'Meena Iyer', rollNo: '22CS067', programme: 'B.Tech CSE', dueAmount: 22500, dueSince: '15 Jan 2026', installment: 'Hostel fee', status: 'partial' },
  { id: 'd05', name: 'Akash Singh', rollNo: '23EC001', programme: 'B.Tech ECE', dueAmount: 90000, dueSince: '15 Sep 2025', installment: 'Sem 3 + Sem 4 + Sem 5', status: 'overdue' },
  { id: 'd06', name: 'Lakshmi Prasad', rollNo: '22CS041', programme: 'B.Tech CSE', dueAmount: 18000, dueSince: '01 Feb 2026', installment: 'Transport fee', status: 'partial' },
  { id: 'd07', name: 'Vikram Nair', rollNo: '21ME022', programme: 'B.Tech ME', dueAmount: 45000, dueSince: '30 Nov 2025', installment: 'Sem 4 Fee', status: 'notice_sent' },
  { id: 'd08', name: 'Priya Shankar', rollNo: '22EC018', programme: 'B.Tech ECE', dueAmount: 27000, dueSince: '15 Jan 2026', installment: 'Library + Lab fee', status: 'partial' },
]

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

const STATS = [
  { label: 'Total dues', value: '₹3,39,500', delta: '8 defaulters', deltaColor: '#E24B4A' },
  { label: 'Collected this month', value: '₹12.4L', delta: '↑ 8% vs last month', deltaColor: '#1D9E75' },
  { label: 'Invoices overdue', value: '23', delta: '4 > 90 days', deltaColor: '#EF9F27' },
  { label: 'Scholarships pending', value: '₹2.1L', delta: '14 students', deltaColor: '#94a3b8' },
]

// ---------------------------------------------------------------------------

const COLLECTION_MONTHS = [
  { month: 'Oct', amount: 8.4 },
  { month: 'Nov', amount: 9.1 },
  { month: 'Dec', amount: 7.2 },
  { month: 'Jan', amount: 11.5 },
  { month: 'Feb', amount: 12.4 },
]

const MAX_AMOUNT = Math.max(...COLLECTION_MONTHS.map((m) => m.amount))

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
  const [activeTab, setActiveTab] = useState<'defaulters' | 'collection'>('defaulters')

  const totalDue = DEFAULTERS.reduce((sum, d) => sum + d.dueAmount, 0)
  const overdueCount = DEFAULTERS.filter((d) => d.status === 'overdue').length

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
      <StatsRow stats={STATS} />

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 2, borderBottom: 'var(--border)' }}>
        {(['defaulters', 'collection'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '6px 14px',
              fontSize: 12,
              fontWeight: 500,
              background: 'none',
              border: 'none',
              borderBottom: activeTab === tab ? '2px solid var(--alis-teal)' : '2px solid transparent',
              color: activeTab === tab ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
              cursor: 'pointer',
              textTransform: 'capitalize',
              transition: 'color 0.12s',
            }}
          >
            {tab === 'defaulters'
              ? `Defaulters (${overdueCount} overdue)`
              : 'Collection trend'}
          </button>
        ))}
      </div>

      {/* Defaulter table */}
      {activeTab === 'defaulters' && (
        <>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: -4,
            }}
          >
            <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>
              Total outstanding: <strong style={{ color: '#E24B4A' }}>₹{totalDue.toLocaleString('en-IN')}</strong>
            </span>
            <button
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
            rows={DEFAULTERS}
            highlightedId={canvas.highlightedItemId}
            onRowClick={(row) => highlightItem(row.id)}
            gridTemplateColumns="2fr 90px 1.5fr 100px 1fr 2fr 100px"
          />
        </>
      )}

      {/* Collection trend mini chart */}
      {activeTab === 'collection' && (
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
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, height: 100 }}>
            {COLLECTION_MONTHS.map((m) => {
              const h = (m.amount / MAX_AMOUNT) * 100
              const isLatest = m.month === 'Feb'
              return (
                <div
                  key={m.month}
                  style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1 }}
                >
                  <span
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
                    style={{
                      width: '100%',
                      height: `${h}%`,
                      background: isLatest ? 'var(--alis-teal)' : 'rgba(29,158,117,0.3)',
                      borderRadius: '3px 3px 0 0',
                      minHeight: 4,
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
      )}
    </div>
  )
}
