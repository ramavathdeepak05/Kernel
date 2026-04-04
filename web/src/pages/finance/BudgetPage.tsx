/**
 * Budget Planning Page (FM-6)
 * Finance: manage budgets, track utilization, variance alerts
 */

import { useState, useEffect } from 'react'
import { Badge } from '../../components/Badge'
import { StatsRow } from '../../components/StatCard'

const API = import.meta.env.VITE_API_URL || "/api/v1";

interface Budget {
  id: string; department: string; financial_year: string;
  allocated_amount: number; committed_amount: number; spent_amount: number;
  status: string;
}

export function BudgetPage() {
  const [budgets, setBudgets] = useState<Budget[]>([])
  const [alerts, setAlerts] = useState<{ department: string; message: string; severity: string }[]>([])

  useEffect(() => {
    const token = sessionStorage.getItem("token")
    if (!token) return
    const headers = { Authorization: `Bearer ${token}` }
    Promise.allSettled([
      fetch(`${API}/finance/budgets?financial_year=2025-26`, { headers }),
      fetch(`${API}/finance/budgets/variance-alerts`, { headers }),
    ]).then(async ([budgetRes, alertRes]) => {
      if (budgetRes.status === 'fulfilled' && budgetRes.value.ok) {
        const d = await budgetRes.value.json()
        setBudgets((d.items ?? d ?? []).map((b: Record<string, unknown>) => ({
          id: String(b.id ?? ''), department: String(b.department ?? ''),
          financial_year: String(b.financial_year ?? ''),
          allocated_amount: Number(b.allocated_amount ?? 0),
          committed_amount: Number(b.committed_amount ?? 0),
          spent_amount: Number(b.spent_amount ?? 0),
          status: String(b.status ?? ''),
        })))
      }
      if (alertRes.status === 'fulfilled' && alertRes.value.ok) {
        const d = await alertRes.value.json()
        setAlerts((d.items ?? d ?? []).map((a: Record<string, unknown>) => ({
          department: String(a.department ?? ''),
          message: String(a.message ?? ''),
          severity: String(a.severity ?? 'WARNING'),
        })))
      }
    })
  }, [])

  const totalAllocated = budgets.reduce((s, b) => s + b.allocated_amount, 0)
  const totalSpent = budgets.reduce((s, b) => s + b.spent_amount, 0)
  const totalCommitted = budgets.reduce((s, b) => s + b.committed_amount, 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h1 style={{ fontSize: 15, fontWeight: 600 }}>Budget Planning</h1>

      <StatsRow stats={[
        { label: 'Total Allocated', value: `₹${(totalAllocated / 100000).toFixed(1)}L`, delta: '' },
        { label: 'Committed', value: `₹${(totalCommitted / 100000).toFixed(1)}L`, delta: '' },
        { label: 'Spent', value: `₹${(totalSpent / 100000).toFixed(1)}L`, delta: '' },
        { label: 'Variance Alerts', value: String(alerts.length), delta: alerts.length > 0 ? 'Action needed' : 'All clear', deltaColor: alerts.length > 0 ? '#E24B4A' : '#1D9E75' },
      ]} />

      {alerts.length > 0 && (
        <div style={{ background: 'rgba(226,75,74,0.06)', border: '1px solid rgba(226,75,74,0.2)', borderRadius: 8, padding: 12 }}>
          <p style={{ fontSize: 11, fontWeight: 600, color: '#E24B4A', marginBottom: 8 }}>VARIANCE ALERTS</p>
          {alerts.map((a, i) => (
            <p key={i} style={{ fontSize: 12, marginBottom: 4 }}>
              <strong>{a.department}:</strong> {a.message}
            </p>
          ))}
        </div>
      )}

      {budgets.length === 0 ? (
        <p style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: 40 }}>No budgets found.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {budgets.map(b => {
            const util = b.allocated_amount > 0 ? (b.spent_amount + b.committed_amount) / b.allocated_amount * 100 : 0
            return (
              <div key={b.id} style={{
                padding: '12px 16px', border: 'var(--border)', borderRadius: 8,
                display: 'grid', gridTemplateColumns: '1.5fr 100px 100px 100px 60px 80px',
                gap: 8, alignItems: 'center',
              }}>
                <span style={{ fontWeight: 500, fontSize: 13 }}>{b.department}</span>
                <span style={{ fontSize: 12 }}>₹{(b.allocated_amount / 1000).toFixed(0)}K</span>
                <span style={{ fontSize: 12 }}>₹{(b.spent_amount / 1000).toFixed(0)}K</span>
                <span style={{ fontSize: 12 }}>₹{(b.committed_amount / 1000).toFixed(0)}K</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: util > 100 ? '#E24B4A' : '#1D9E75' }}>
                  {util.toFixed(0)}%
                </span>
                <Badge variant={b.status === 'ACTIVE' ? 'green' : b.status === 'DRAFT' ? 'gray' : 'amber'}>
                  {b.status}
                </Badge>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
