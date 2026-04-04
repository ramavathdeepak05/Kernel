/**
 * Training & Development Page (HR-5)
 *
 * Faculty: see available programs, enroll, track completion
 * HR Manager: manage programs, enrollments, assessments, refresher reminders
 */

import { useState, useEffect } from 'react'
import { Badge } from '../../components/Badge'

const API = import.meta.env.VITE_API_URL || "/api/v1";

interface Program {
  id: string; title: string; training_type: string; start_date: string;
  end_date: string; status: string; venue: string;
}

export function TrainingPage() {
  const [programs, setPrograms] = useState<Program[]>([])

  useEffect(() => {
    const token = sessionStorage.getItem("token")
    if (!token) return
    fetch(`${API}/hr/training/programs`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : { items: [] })
      .then(d => setPrograms((d.items ?? d ?? []).map((p: Record<string, unknown>) => ({
        id: String(p.id ?? ''), title: String(p.title ?? ''),
        training_type: String(p.training_type ?? ''), start_date: String(p.start_date ?? ''),
        end_date: String(p.end_date ?? ''), status: String(p.status ?? ''),
        venue: String(p.venue ?? ''),
      }))))
  }, [])

  const STATUS_COLORS: Record<string, 'green' | 'amber' | 'blue' | 'gray'> = {
    PLANNED: 'blue', OPEN: 'green', IN_PROGRESS: 'amber', COMPLETED: 'gray',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h1 style={{ fontSize: 15, fontWeight: 600 }}>Training & Development</h1>

      {programs.length === 0 ? (
        <p style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: 40 }}>
          No training programs found.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {programs.map(p => (
            <div key={p.id} style={{
              padding: '12px 16px', border: 'var(--border)', borderRadius: 8,
              display: 'grid', gridTemplateColumns: '2fr 100px 120px 100px',
              gap: 8, alignItems: 'center',
            }}>
              <div>
                <span style={{ fontWeight: 600, fontSize: 14 }}>{p.title}</span>
                <span style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginLeft: 8 }}>
                  {p.training_type}
                </span>
              </div>
              <span style={{ fontSize: 12 }}>{p.start_date}</span>
              <span style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>{p.venue}</span>
              <Badge variant={STATUS_COLORS[p.status] ?? 'gray'}>{p.status}</Badge>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
