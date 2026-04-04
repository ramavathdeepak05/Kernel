/**
 * Clubs & Events Page (SS-6)
 *
 * Students: see clubs, join, propose events
 * Faculty/Dean: review + approve clubs and events
 */

import { useState, useEffect } from 'react'
import { Badge } from '../../components/Badge'
import { RoleSwitch } from '../../components/RoleSwitch'

const API = import.meta.env.VITE_API_URL || "/api/v1";

interface Club { id: string; name: string; category: string; status: string; member_count?: number }
interface Event { id: string; title: string; event_date: string; status: string; club_name?: string }

function ClubsList() {
  const [clubs, setClubs] = useState<Club[]>([])
  useEffect(() => {
    const token = sessionStorage.getItem("token")
    if (!token) return
    fetch(`${API}/student-services/clubs`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : { items: [] })
      .then(d => setClubs((d.items ?? d ?? []).map((c: Record<string, unknown>) => ({
        id: String(c.id ?? ''), name: String(c.name ?? ''),
        category: String(c.category ?? ''), status: String(c.status ?? ''),
      }))))
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {clubs.length === 0 ? (
        <p style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: 40 }}>No clubs found.</p>
      ) : clubs.map(c => (
        <div key={c.id} style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '10px 14px', border: 'var(--border)', borderRadius: 8,
        }}>
          <div>
            <span style={{ fontWeight: 600, fontSize: 14 }}>{c.name}</span>
            <span style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginLeft: 8 }}>{c.category}</span>
          </div>
          <Badge variant={c.status === 'ACTIVE' ? 'green' : c.status === 'PROPOSED' ? 'amber' : 'gray'}>
            {c.status}
          </Badge>
        </div>
      ))}
    </div>
  )
}

export function ClubsEventsPage() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h1 style={{ fontSize: 15, fontWeight: 600 }}>Clubs & Events</h1>
      <ClubsList />
    </div>
  )
}
