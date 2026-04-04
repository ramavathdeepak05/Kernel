/**
 * Recruitment Page (HR-1)
 * HR Manager: manage vacancies, screen applications, UGC eligibility
 */

import { useState, useEffect } from 'react'
import { Badge } from '../../components/Badge'

const API = import.meta.env.VITE_API_URL || "/api/v1";

interface Vacancy {
  id: string; department: string; designation: string; positions_count: number;
  status: string; ugc_designation: string;
}

export function RecruitmentPage() {
  const [vacancies, setVacancies] = useState<Vacancy[]>([])

  useEffect(() => {
    const token = sessionStorage.getItem("token")
    if (!token) return
    fetch(`${API}/hr/recruitment/vacancies`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : { items: [] })
      .then(d => setVacancies((d.items ?? d ?? []).map((v: Record<string, unknown>) => ({
        id: String(v.id ?? ''), department: String(v.department ?? ''),
        designation: String(v.designation ?? ''),
        positions_count: Number(v.positions_count ?? 0),
        status: String(v.status ?? ''), ugc_designation: String(v.ugc_designation ?? ''),
      }))))
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h1 style={{ fontSize: 15, fontWeight: 600 }}>Recruitment</h1>
      {vacancies.length === 0 ? (
        <p style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: 40 }}>
          No active vacancies.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {vacancies.map(v => (
            <div key={v.id} style={{
              padding: '12px 16px', border: 'var(--border)', borderRadius: 8,
              display: 'grid', gridTemplateColumns: '1.5fr 1.5fr 60px 100px',
              gap: 8, alignItems: 'center',
            }}>
              <div>
                <span style={{ fontWeight: 600, fontSize: 14 }}>{v.designation}</span>
                {v.ugc_designation && (
                  <span style={{ fontSize: 10, color: '#1D9E75', marginLeft: 6 }}>UGC</span>
                )}
              </div>
              <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>{v.department}</span>
              <span style={{ fontSize: 12 }}>{v.positions_count} pos</span>
              <Badge variant={v.status === 'ADVERTISED' ? 'green' : v.status === 'FILLED' ? 'gray' : 'amber'}>
                {v.status}
              </Badge>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
