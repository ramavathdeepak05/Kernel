/**
 * StudentDashboard — exam schedule + personal stats
 * Reference: ALIS-skills/references/frontend.md §11
 *
 * Density: low (Student role)
 * Default view: my_courses
 */

import { useALISStore } from '../store/alis.store'
import { StatsRow } from '../components/StatCard'
import { Badge } from '../components/Badge'

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

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

const EXAMS: ExamEntry[] = [
  { id: 'e1', subject: 'Data Structures & Algorithms', code: 'CS301', date: 'Mon, 17 Mar 2026', time: '09:00 AM', venue: 'Hall A – Room 101', daysAway: 2, status: 'upcoming' },
  { id: 'e2', subject: 'Database Management Systems', code: 'CS302', date: 'Wed, 19 Mar 2026', time: '02:00 PM', venue: 'Hall B – Room 205', daysAway: 4, status: 'upcoming' },
  { id: 'e3', subject: 'Operating Systems', code: 'CS303', date: 'Fri, 21 Mar 2026', time: '09:00 AM', venue: 'Hall A – Room 102', daysAway: 6, status: 'upcoming' },
  { id: 'e4', subject: 'Computer Networks', code: 'CS304', date: 'Mon, 24 Mar 2026', time: '02:00 PM', venue: 'Hall C – Room 301', daysAway: 9, status: 'upcoming' },
  { id: 'e5', subject: 'Engineering Mathematics IV', code: 'MA301', date: 'Wed, 26 Mar 2026', time: '09:00 AM', venue: 'Hall B – Room 202', daysAway: 11, status: 'upcoming' },
]

const STATS = [
  { label: 'Exams remaining', value: '5', delta: 'Next in 2 days', deltaColor: '#EF9F27' },
  { label: 'Attendance', value: '78%', delta: 'Min required: 75%', deltaColor: '#1D9E75' },
  { label: 'Internal marks', value: '71/100', delta: 'Avg across subjects' },
  { label: 'Dues', value: '₹0', delta: 'All clear', deltaColor: '#1D9E75' },
]

// ---------------------------------------------------------------------------

function urgencyColor(days: number): string {
  if (days <= 2) return '#E24B4A'
  if (days <= 5) return '#EF9F27'
  return 'var(--color-text-secondary)'
}

export function StudentDashboard() {
  useALISStore() // keep store wired for future agent actions

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
      <StatsRow stats={STATS} />

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
          {EXAMS.map((exam) => (
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
