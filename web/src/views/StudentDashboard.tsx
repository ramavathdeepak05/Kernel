/**
 * StudentDashboard — exam schedule + personal stats
 * Reference: ALIS-skills/references/frontend.md §11
 *
 * Density: low (Student role)
 * Default view: my_courses
 */

import { useState, useEffect } from 'react'
import { useALISStore } from '../store/alis.store'
import { StatsRow } from '../components/StatCard'
import { Badge } from '../components/Badge'

// ---------------------------------------------------------------------------
// Data types + API fetching
// ---------------------------------------------------------------------------

const API_BASE = import.meta.env.VITE_API_URL || "/api/v1";

interface ExamEntry {
  id: string
  subject: string
  code: string
  date: string
  time: string
  venue: string
  daysAway: number
  status: 'upcoming' | 'today' | 'done'
}

const EMPTY_STATS = [
  { label: 'Exams remaining', value: '—', delta: '' },
  { label: 'Attendance', value: '—', delta: '' },
  { label: 'Internal marks', value: '—', delta: '' },
  { label: 'Dues', value: '—', delta: '' },
]

// ---------------------------------------------------------------------------

function urgencyColor(days: number): string {
  if (days <= 2) return '#E24B4A'
  if (days <= 5) return '#EF9F27'
  return 'var(--color-text-secondary)'
}

export function StudentDashboard() {
  useALISStore() // keep store wired for future agent actions
  const [exams, setExams] = useState<ExamEntry[]>([])
  const [stats, setStats] = useState(EMPTY_STATS)

  useEffect(() => {
    const token = sessionStorage.getItem("token");
    if (!token) return;
    const headers = { Authorization: `Bearer ${token}` };
    Promise.allSettled([
      fetch(`${API_BASE}/examinations/my-schedule`, { headers }),
      fetch(`${API_BASE}/reports/dashboard/kpis`, { headers }),
    ]).then(async ([examRes, kpiRes]) => {
      if (examRes.status === "fulfilled" && examRes.value.ok) {
        const data = await examRes.value.json();
        setExams((data.items ?? data ?? []).map((e: Record<string, unknown>) => ({
          id: String(e.id ?? ""), subject: String(e.subject ?? e.course_name ?? ""),
          code: String(e.code ?? e.course_code ?? ""), date: String(e.date ?? e.exam_date ?? ""),
          time: String(e.time ?? e.start_time ?? ""), venue: String(e.venue ?? "TBA"),
          daysAway: Number(e.days_away ?? e.daysAway ?? 0),
          status: (e.status as ExamEntry["status"]) ?? "upcoming",
        })));
      }
      if (kpiRes.status === "fulfilled" && kpiRes.value.ok) {
        const kpis = await kpiRes.value.json();
        setStats([
          { label: 'Exams remaining', value: String(kpis.exams_remaining ?? '0'), delta: kpis.next_exam_delta ?? '', deltaColor: '#EF9F27' },
          { label: 'Attendance', value: kpis.attendance ? `${kpis.attendance}%` : '—', delta: kpis.attendance_delta ?? '', deltaColor: '#1D9E75' },
          { label: 'Internal marks', value: String(kpis.internal_marks ?? '—'), delta: kpis.marks_delta ?? '' },
          { label: 'Dues', value: kpis.dues ?? '₹0', delta: kpis.dues_delta ?? '', deltaColor: '#1D9E75' },
        ]);
      }
    });
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Header */}
      <div>
        <h1 style={{ fontSize: 15, fontWeight: 600, color: 'var(--color-text-primary)', letterSpacing: '-0.01em' }}>
          My Dashboard
        </h1>
        <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
          B.Tech CSE · Semester 5 · Roll: 22CS041
        </p>
      </div>

      {/* Stats */}
      <StatsRow stats={stats} />

      {/* Exam schedule */}
      <div>
        <p
          style={{
            fontSize: 10,
            fontWeight: 500,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'var(--color-text-secondary)',
            marginBottom: 10,
            paddingBottom: 4,
            borderBottom: 'var(--border)',
          }}
        >
          Exam schedule
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {exams.map((exam) => (
            <div
              key={exam.id}
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr auto',
                alignItems: 'center',
                gap: 12,
                background: 'var(--color-background-secondary)',
                border: 'var(--border)',
                borderLeft: `2.5px solid ${urgencyColor(exam.daysAway)}`,
                borderRadius: 'var(--radius-md)',
                padding: '10px 14px',
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 600,
                      color: 'var(--alis-teal)',
                      letterSpacing: '0.05em',
                    }}
                  >
                    {exam.code}
                  </span>
                  {exam.daysAway <= 2 && (
                    <Badge variant="red">Soon</Badge>
                  )}
                </div>
                <p style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-text-primary)' }}>
                  {exam.subject}
                </p>
                <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 3 }}>
                  {exam.venue}
                </p>
              </div>

              <div style={{ textAlign: 'right', flexShrink: 0 }}>
                <p style={{ fontSize: 12, fontWeight: 500, color: 'var(--color-text-primary)' }}>
                  {exam.date}
                </p>
                <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 1 }}>
                  {exam.time}
                </p>
                <p
                  style={{
                    fontSize: 10,
                    marginTop: 4,
                    fontWeight: 500,
                    color: urgencyColor(exam.daysAway),
                  }}
                >
                  {exam.daysAway === 0 ? 'Today' : `In ${exam.daysAway} day${exam.daysAway !== 1 ? 's' : ''}`}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Quick links */}
      <div>
        <p
          style={{
            fontSize: 10,
            fontWeight: 500,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'var(--color-text-secondary)',
            marginBottom: 8,
          }}
        >
          Quick links
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {['Hall ticket', 'Fee receipt', 'Bonafide certificate', 'Timetable', 'Attendance report'].map((link) => (
            <button
              key={link}
              style={{
                padding: '5px 12px',
                fontSize: 12,
                fontWeight: 500,
                background: 'var(--color-background-secondary)',
                border: 'var(--border)',
                borderRadius: 'var(--radius-pill)',
                color: 'var(--color-text-primary)',
                cursor: 'pointer',
              }}
            >
              {link}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
