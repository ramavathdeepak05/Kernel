/**
 * My Exams — Student view
 *
 * Shows:
 * - Upcoming exam schedule with venue + time
 * - Hall ticket download (with dues gate check)
 * - Published results
 * - Revaluation request status
 */

import { useState, useEffect } from 'react'
import { Badge } from '../../components/Badge'

const API = import.meta.env.VITE_API_URL || "/api/v1";

interface ExamEntry {
  id: string; course_code: string; course_name: string; exam_date: string;
  start_time: string; venue: string; hall_ticket_available: boolean;
}
interface ResultEntry {
  course_code: string; course_name: string; grade: string;
  grade_points: number; semester: number; is_pass: boolean;
}

export function MyExamsPage() {
  const [exams, setExams] = useState<ExamEntry[]>([])
  const [results, setResults] = useState<ResultEntry[]>([])
  const [tab, setTab] = useState<'schedule' | 'results'>('schedule')

  useEffect(() => {
    const token = sessionStorage.getItem("token")
    if (!token) return
    const headers = { Authorization: `Bearer ${token}` }
    Promise.allSettled([
      fetch(`${API}/examinations/my-schedule`, { headers }),
      fetch(`${API}/examinations/my-results`, { headers }),
    ]).then(async ([examRes, resultRes]) => {
      if (examRes.status === 'fulfilled' && examRes.value.ok) {
        const data = await examRes.value.json()
        setExams((data.items ?? data ?? []).map((e: Record<string, unknown>) => ({
          id: String(e.id ?? ''), course_code: String(e.course_code ?? ''),
          course_name: String(e.course_name ?? ''), exam_date: String(e.exam_date ?? ''),
          start_time: String(e.start_time ?? ''), venue: String(e.venue ?? 'TBA'),
          hall_ticket_available: Boolean(e.hall_ticket_available ?? false),
        })))
      }
      if (resultRes.status === 'fulfilled' && resultRes.value.ok) {
        const data = await resultRes.value.json()
        setResults((data.items ?? data ?? []).map((r: Record<string, unknown>) => ({
          course_code: String(r.course_code ?? ''), course_name: String(r.course_name ?? ''),
          grade: String(r.grade ?? ''), grade_points: Number(r.grade_points ?? 0),
          semester: Number(r.semester ?? 0), is_pass: Boolean(r.is_pass ?? false),
        })))
      }
    })
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h1 style={{ fontSize: 15, fontWeight: 600 }}>My Examinations</h1>

      <div style={{ display: 'flex', gap: 8, borderBottom: 'var(--border)', paddingBottom: 8 }}>
        {(['schedule', 'results'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: '6px 16px', borderRadius: 6, border: 'none', cursor: 'pointer',
            background: tab === t ? '#1D9E75' : 'transparent',
            color: tab === t ? '#fff' : 'var(--color-text-secondary)',
            fontWeight: tab === t ? 600 : 400, fontSize: 13,
          }}>
            {t === 'schedule' ? 'Exam Schedule' : 'My Results'}
          </button>
        ))}
      </div>

      {tab === 'schedule' && (
        exams.length === 0 ? (
          <p style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: 40 }}>
            No upcoming exams scheduled.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {exams.map(e => (
              <div key={e.id} style={{
                display: 'grid', gridTemplateColumns: '80px 2fr 120px 100px 1fr',
                gap: 8, padding: '10px 14px', border: 'var(--border)', borderRadius: 8, alignItems: 'center',
              }}>
                <span style={{ fontWeight: 600, fontSize: 12, color: '#1D9E75' }}>{e.course_code}</span>
                <span style={{ fontSize: 13 }}>{e.course_name}</span>
                <span style={{ fontSize: 12 }}>{e.exam_date}</span>
                <span style={{ fontSize: 12 }}>{e.start_time}</span>
                <span style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>{e.venue}</span>
              </div>
            ))}
          </div>
        )
      )}

      {tab === 'results' && (
        results.length === 0 ? (
          <p style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: 40 }}>
            No results published yet.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {results.map((r, i) => (
              <div key={i} style={{
                display: 'grid', gridTemplateColumns: '80px 2fr 60px 80px 80px',
                gap: 8, padding: '10px 14px', border: 'var(--border)', borderRadius: 8, alignItems: 'center',
              }}>
                <span style={{ fontWeight: 600, fontSize: 12, color: '#1D9E75' }}>{r.course_code}</span>
                <span style={{ fontSize: 13 }}>{r.course_name}</span>
                <span style={{ fontSize: 12 }}>Sem {r.semester}</span>
                <span style={{ fontWeight: 600, fontSize: 13, color: r.is_pass ? '#1D9E75' : '#E24B4A' }}>
                  {r.grade}
                </span>
                <Badge variant={r.is_pass ? 'green' : 'red'}>{r.is_pass ? 'Pass' : 'Fail'}</Badge>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  )
}
