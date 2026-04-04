/**
 * My Courses — Student view
 *
 * Shows:
 * - Currently enrolled courses with faculty name, schedule, attendance %
 * - Course materials (LMS integration)
 * - Assignment deadlines
 * - Internal marks (published only)
 */

import { useState, useEffect } from 'react'
import { StatsRow } from '../../components/StatCard'

const API = import.meta.env.VITE_API_URL || "/api/v1";

interface Course {
  id: string
  code: string
  name: string
  faculty_name: string
  credits: number
  attendance_pct: number
  internal_marks: number | null
}

const EMPTY_STATS = [
  { label: 'Enrolled Courses', value: '—', delta: '' },
  { label: 'Avg Attendance', value: '—', delta: '' },
  { label: 'Avg Internal Marks', value: '—', delta: '' },
  { label: 'Pending Assignments', value: '—', delta: '' },
]

export function MyCoursesPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [stats, setStats] = useState(EMPTY_STATS)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = sessionStorage.getItem("token")
    if (!token) return
    setLoading(true)
    fetch(`${API}/academics/my-courses`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : { items: [] })
      .then(data => {
        const items = data.items ?? data ?? []
        setCourses(items.map((c: Record<string, unknown>) => ({
          id: String(c.id ?? ''),
          code: String(c.course_code ?? c.code ?? ''),
          name: String(c.course_name ?? c.name ?? ''),
          faculty_name: String(c.faculty_name ?? ''),
          credits: Number(c.credits ?? 0),
          attendance_pct: Number(c.attendance_pct ?? c.attendance ?? 0),
          internal_marks: c.internal_marks != null ? Number(c.internal_marks) : null,
        })))
        if (items.length > 0) {
          const avgAtt = items.reduce((s: number, c: Record<string, unknown>) => s + Number(c.attendance_pct ?? 0), 0) / items.length
          setStats([
            { label: 'Enrolled Courses', value: String(items.length), delta: 'Current semester' },
            { label: 'Avg Attendance', value: `${avgAtt.toFixed(0)}%`, delta: avgAtt >= 75 ? 'On track' : 'Below 75%', deltaColor: avgAtt >= 75 ? '#1D9E75' : '#E24B4A' },
            { label: 'Avg Internal Marks', value: '—', delta: '' },
            { label: 'Pending Assignments', value: '—', delta: '' },
          ])
        }
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 15, fontWeight: 600 }}>My Courses</h1>
        <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
          Current semester enrollment
        </p>
      </div>

      <StatsRow stats={stats} />

      {loading ? (
        <p style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: 40 }}>Loading...</p>
      ) : courses.length === 0 ? (
        <p style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: 40 }}>
          No courses enrolled for this semester.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {courses.map(c => (
            <div
              key={c.id}
              style={{
                display: 'grid',
                gridTemplateColumns: '80px 2fr 1.5fr 80px 80px',
                gap: 12,
                padding: '12px 16px',
                border: 'var(--border)',
                borderRadius: 'var(--radius-md)',
                alignItems: 'center',
              }}
            >
              <span style={{ fontWeight: 600, fontSize: 12, color: '#1D9E75' }}>{c.code}</span>
              <span style={{ fontSize: 13 }}>{c.name}</span>
              <span style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>{c.faculty_name}</span>
              <span style={{
                fontSize: 12, fontWeight: 500,
                color: c.attendance_pct >= 75 ? '#1D9E75' : c.attendance_pct >= 60 ? '#EF9F27' : '#E24B4A',
              }}>
                {c.attendance_pct}%
              </span>
              <span style={{ fontSize: 12 }}>{c.credits} cr</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
