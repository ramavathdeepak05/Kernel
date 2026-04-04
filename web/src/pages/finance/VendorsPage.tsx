/**
 * Vendors & Purchase Page (FM-4)
 * Finance: vendor management, POs, 3-way match, TDS
 */

import { useState, useEffect } from 'react'
import { Badge } from '../../components/Badge'

const API = import.meta.env.VITE_API_URL || "/api/v1";

interface Vendor { id: string; name: string; gstin: string; pan: string; status: string }
interface PO { id: string; po_number: string; vendor_name?: string; total_amount: number; status: string }

export function VendorsPage() {
  const [tab, setTab] = useState<'vendors' | 'orders'>('vendors')
  const [vendors, setVendors] = useState<Vendor[]>([])
  const [orders, setOrders] = useState<PO[]>([])

  useEffect(() => {
    const token = sessionStorage.getItem("token")
    if (!token) return
    const headers = { Authorization: `Bearer ${token}` }
    fetch(`${API}/finance/vendors`, { headers })
      .then(r => r.ok ? r.json() : { items: [] })
      .then(d => setVendors((d.items ?? d ?? []).map((v: Record<string, unknown>) => ({
        id: String(v.id ?? ''), name: String(v.name ?? ''),
        gstin: String(v.gstin ?? ''), pan: String(v.pan ?? ''),
        status: String(v.status ?? ''),
      }))))
    fetch(`${API}/finance/purchase-orders`, { headers })
      .then(r => r.ok ? r.json() : { items: [] })
      .then(d => setOrders((d.items ?? d ?? []).map((o: Record<string, unknown>) => ({
        id: String(o.id ?? ''), po_number: String(o.po_number ?? ''),
        total_amount: Number(o.total_amount ?? 0), status: String(o.status ?? ''),
      }))))
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h1 style={{ fontSize: 15, fontWeight: 600 }}>Vendors & Purchase Orders</h1>

      <div style={{ display: 'flex', gap: 8 }}>
        {(['vendors', 'orders'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: '6px 16px', borderRadius: 6, border: 'none', cursor: 'pointer',
            background: tab === t ? '#1D9E75' : 'transparent',
            color: tab === t ? '#fff' : 'var(--color-text-secondary)',
            fontWeight: tab === t ? 600 : 400, fontSize: 13,
          }}>
            {t === 'vendors' ? `Vendors (${vendors.length})` : `Purchase Orders (${orders.length})`}
          </button>
        ))}
      </div>

      {tab === 'vendors' && (
        vendors.length === 0 ? (
          <p style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: 40 }}>No vendors registered.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {vendors.map(v => (
              <div key={v.id} style={{
                padding: '10px 14px', border: 'var(--border)', borderRadius: 8,
                display: 'grid', gridTemplateColumns: '2fr 120px 100px 80px', gap: 8, alignItems: 'center',
              }}>
                <span style={{ fontWeight: 500, fontSize: 13 }}>{v.name}</span>
                <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>{v.gstin || 'No GSTIN'}</span>
                <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>{v.pan || 'No PAN'}</span>
                <Badge variant={v.status === 'ACTIVE' ? 'green' : v.status === 'PENDING' ? 'amber' : 'red'}>
                  {v.status}
                </Badge>
              </div>
            ))}
          </div>
        )
      )}

      {tab === 'orders' && (
        orders.length === 0 ? (
          <p style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: 40 }}>No purchase orders.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {orders.map(o => (
              <div key={o.id} style={{
                padding: '10px 14px', border: 'var(--border)', borderRadius: 8,
                display: 'grid', gridTemplateColumns: '120px 2fr 100px 100px', gap: 8, alignItems: 'center',
              }}>
                <span style={{ fontWeight: 600, fontSize: 12, color: '#1D9E75' }}>{o.po_number}</span>
                <span style={{ fontSize: 13 }}>{o.vendor_name ?? '—'}</span>
                <span style={{ fontWeight: 500, fontSize: 13 }}>₹{o.total_amount.toLocaleString()}</span>
                <Badge variant={o.status === 'PAID' ? 'green' : o.status === 'APPROVED' ? 'blue' : 'amber'}>
                  {o.status}
                </Badge>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  )
}
