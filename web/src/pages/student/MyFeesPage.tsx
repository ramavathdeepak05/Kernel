/**
 * My Fees — Student view
 *
 * Shows:
 * - Current dues summary
 * - Payment history
 * - Fee structure (locked version)
 * - Scholarship status
 * - Pay now button (Razorpay / PayU integration)
 */

import { useState, useEffect } from 'react'
import { StatsRow } from '../../components/StatCard'
import { Badge } from '../../components/Badge'

const API = import.meta.env.VITE_API_URL || "/api/v1";

interface FeeItem {
  id: string; description: string; amount: number; due_date: string;
  status: 'PAID' | 'UNPAID' | 'OVERDUE' | 'PARTIAL';
}

const EMPTY_STATS = [
  { label: 'Total Dues', value: '—', delta: '' },
  { label: 'Total Paid', value: '—', delta: '' },
  { label: 'Scholarships', value: '—', delta: '' },
  { label: 'Next Due', value: '—', delta: '' },
]

const STATUS_VARIANT: Record<string, 'green' | 'red' | 'amber' | 'gray'> = {
  PAID: 'green', UNPAID: 'amber', OVERDUE: 'red', PARTIAL: 'amber',
}

export function MyFeesPage() {
  const [fees, setFees] = useState<FeeItem[]>([])
  const [stats, setStats] = useState(EMPTY_STATS)

  useEffect(() => {
    const token = sessionStorage.getItem("token")
    if (!token) return
    const headers = { Authorization: `Bearer ${token}` }
    Promise.allSettled([
      fetch(`${API}/finance/my-fees`, { headers }),
      fetch(`${API}/finance/my-dues-summary`, { headers }),
    ]).then(async ([feeRes, summaryRes]) => {
      if (feeRes.status === 'fulfilled' && feeRes.value.ok) {
        const data = await feeRes.value.json()
        setFees((data.items ?? data ?? []).map((f: Record<string, unknown>) => ({
          id: String(f.id ?? ''), description: String(f.description ?? f.invoice_type ?? ''),
          amount: Number(f.amount ?? f.total_amount ?? 0),
          due_date: String(f.due_date ?? ''), status: String(f.status ?? 'UNPAID'),
        })))
      }
      if (summaryRes.status === 'fulfilled' && summaryRes.value.ok) {
        const s = await summaryRes.value.json()
        setStats([
          { label: 'Total Dues', value: s.total_due ? `₹${Number(s.total_due).toLocaleString()}` : '₹0', delta: s.total_due > 0 ? 'Outstanding' : 'All clear', deltaColor: s.total_due > 0 ? '#E24B4A' : '#1D9E75' },
          { label: 'Total Paid', value: s.total_paid ? `₹${Number(s.total_paid).toLocaleString()}` : '₹0', delta: '' },
          { label: 'Scholarships', value: s.scholarship_amount ? `₹${Number(s.scholarship_amount).toLocaleString()}` : '₹0', delta: s.scholarship_name ?? '' },
          { label: 'Next Due', value: s.next_due_date ?? '—', delta: s.next_due_amount ? `₹${Number(s.next_due_amount).toLocaleString()}` : '' },
        ])
      }
    })
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <h1 style={{ fontSize: 15, fontWeight: 600 }}>My Fees & Payments</h1>
      <StatsRow stats={stats} />

      {fees.length === 0 ? (
        <p style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: 40 }}>
          No fee records found.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {fees.map(f => (
            <div key={f.id} style={{
              display: 'grid', gridTemplateColumns: '2fr 100px 120px 100px',
              gap: 8, padding: '10px 14px', border: 'var(--border)', borderRadius: 8, alignItems: 'center',
            }}>
              <span style={{ fontSize: 13 }}>{f.description}</span>
              <span style={{ fontWeight: 600, fontSize: 13 }}>₹{f.amount.toLocaleString()}</span>
              <span style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>{f.due_date}</span>
              <Badge variant={STATUS_VARIANT[f.status] ?? 'gray'}>{f.status}</Badge>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
