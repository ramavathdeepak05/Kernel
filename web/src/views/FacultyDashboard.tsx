/**
 * FacultyDashboard — at-risk student list + course tiles
 * Reference: ALIS-skills/references/frontend.md §11
 *
 * Density: medium (Faculty/HOD role)
 * Default view: my_courses
 */

import { useState, useEffect } from 'react'
import { useALISStore } from '../store/alis.store'
import { StatsRow } from '../components/StatCard'
import { RiskBar } from '../components/RiskBar'
import { DataTable, type Column } from '../components/DataTable'
import { ALISTabs, ALISTabsList, ALISTabsTrigger, ALISTabsContent } from '../components/ui/alis-tabs'

// ---------------------------------------------------------------------------
// Data types + API fetching
// ---------------------------------------------------------------------------

const API_BASE = import.meta.env.VITE_API_URL || "/api/v1";

interface AtRiskStudent {
  id: string
  name: string
  rollNo: string
  course: string
  attendance: number
  riskScore: number
  flag: string
}

async function fetchFacultyData(token: string) {
  const headers = { Authorization: `Bearer ${token}` };
  const [riskRes, courseRes, kpiRes] = await Promise.allSettled([
    fetch(`${API_BASE}/academics/at-risk-students`, { headers }),
    fetch(`${API_BASE}/academics/my-courses`, { headers }),
    fetch(`${API_BASE}/reports/dashboard/kpis`, { headers }),
  ]);
  const risk = riskRes.status === "fulfilled" && riskRes.value.ok ? await riskRes.value.json() : [];
  const courses = courseRes.status === "fulfilled" && courseRes.value.ok ? await courseRes.value.json() : [];
  const kpis = kpiRes.status === "fulfilled" && kpiRes.value.ok ? await kpiRes.value.json() : {};
  return {
    atRisk: (risk.items ?? risk ?? []).map((s: Record<string, unknown>) => ({
      id: String(s.id ?? ""), name: String(s.name ?? s.student_name ?? ""),
      rollNo: String(s.roll_no ?? s.rollNo ?? ""), course: String(s.course ?? ""),
      attendance: Number(s.attendance ?? 0), riskScore: Number(s.risk_score ?? s.riskScore ?? 0),
      flag: String(s.flag ?? s.reason ?? ""),
    })) as AtRiskStudent[],
    courses: (courses.items ?? courses ?? []).map((c: Record<string, unknown>) => ({
      id: String(c.id ?? ""), code: String(c.code ?? c.course_code ?? ""),
      name: String(c.name ?? c.course_name ?? ""), students: Number(c.students ?? c.student_count ?? 0),
      pending: Number(c.pending ?? c.pending_marks ?? 0), avgAttendance: Number(c.avg_attendance ?? c.avgAttendance ?? 0),
    })),
    stats: [
      { label: 'My courses', value: String(kpis.my_courses ?? courses.length ?? '0'), delta: kpis.semester ?? '' },
      { label: 'At-risk students', value: String(kpis.at_risk_count ?? risk.length ?? '0'), delta: kpis.risk_delta ?? '', deltaColor: '#EF9F27' },
      { label: 'Avg attendance', value: kpis.avg_attendance ? `${kpis.avg_attendance}%` : '—', delta: kpis.attendance_delta ?? '', deltaColor: '#1D9E75' },
      { label: 'Pending marks', value: String(kpis.pending_marks ?? '0'), delta: kpis.marks_delta ?? '', deltaColor: '#E24B4A' },
    ],
  };
}

const EMPTY_STATS = [
  { label: 'My courses', value: '—', delta: '' },
  { label: 'At-risk students', value: '—', delta: '' },
  { label: 'Avg attendance', value: '—', delta: '' },
  { label: 'Pending marks', value: '—', delta: '' },
]

const AT_RISK_COLUMNS: Column<AtRiskStudent>[] = [
  { key: 'name', label: 'Student', width: '2fr' },
  { key: 'rollNo', label: 'Roll No', width: '1fr' },
  { key: 'course', label: 'Course', width: '2fr' },
  {
    key: 'attendance',
    label: 'Attendance',
    width: '80px',
    render: (row) => (
      <span
        style={{
          fontSize: 12,
          color: row.attendance < 60 ? '#E24B4A' : row.attendance < 75 ? '#EF9F27' : '#1D9E75',
          fontWeight: 500,
        }}
      >
        {row.attendance}%
      </span>
    ),
  },
  {
    key: 'riskScore',
    label: 'Risk',
    width: '100px',
    render: (row) => <RiskBar score={row.riskScore} />,
  },
  {
    key: 'flag',
    label: 'Flag',
    width: '2fr',
    render: (row) => (
      <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>{row.flag}</span>
    ),
  },
]

// ---------------------------------------------------------------------------

export function FacultyDashboard() {
  const { canvas, highlightItem } = useALISStore()
  const [atRisk, setAtRisk] = useState<AtRiskStudent[]>([])
  const [courses, setCourses] = useState<{ id: string; code: string; name: string; students: number; pending: number; avgAttendance: number }[]>([])
  const [stats, setStats] = useState(EMPTY_STATS)

  useEffect(() => {
    const token = sessionStorage.getItem("token");
    if (!token) return;
    fetchFacultyData(token).then((data) => {
      setAtRisk(data.atRisk);
      setCourses(data.courses);
      if (data.stats.length > 0) setStats(data.stats);
    });
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 15, fontWeight: 600, color: 'var(--color-text-primary)', letterSpacing: '-0.01em' }}>
            My Dashboard
          </h1>
          <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
            Semester 5 · B.Tech CSE / ECE / ME
          </p>
        </div>
        <span style={{ fontSize: 10, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--color-text-secondary)' }}>
          Faculty view
        </span>
      </div>

      {/* Stats */}
      <StatsRow stats={stats} />

      {/* Tabs */}
      <ALISTabs defaultValue="risk">
        <ALISTabsList>
          <ALISTabsTrigger value="risk" badge={atRisk.length}>At-risk students</ALISTabsTrigger>
          <ALISTabsTrigger value="courses">My courses</ALISTabsTrigger>
        </ALISTabsList>

        <ALISTabsContent value="risk">
          <DataTable
            columns={AT_RISK_COLUMNS}
            rows={atRisk}
            highlightedId={canvas.highlightedItemId}
            onRowClick={(row) => highlightItem(row.id)}
            gridTemplateColumns="2fr 1fr 2fr 80px 100px 2fr"
          />
        </ALISTabsContent>

        <ALISTabsContent value="courses">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
            {courses.map((course) => (
              <div
                key={course.id}
                className="group"
                style={{
                  background: 'var(--color-background-secondary)',
                  border: 'var(--border)',
                  borderRadius: 'var(--radius-md)',
                  padding: '12px 14px',
                  transition: 'border-color 0.15s',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
                  <div>
                    <p style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em', color: 'var(--alis-teal)', textTransform: 'uppercase' }}>
                      {course.code}
                    </p>
                    <p style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-text-primary)', marginTop: 2 }}>
                      {course.name}
                    </p>
                  </div>
                  {course.pending > 0 && (
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 600,
                        padding: '2px 7px',
                        borderRadius: 'var(--radius-pill)',
                        background: 'rgba(239,159,39,0.12)',
                        color: '#EF9F27',
                        border: '0.5px solid rgba(239,159,39,0.25)',
                        flexShrink: 0,
                      }}
                    >
                      {course.pending} pending
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 16 }}>
                  <div>
                    <p style={{ fontSize: 10, color: 'var(--color-text-secondary)' }}>Students</p>
                    <p style={{ fontSize: 15, fontWeight: 500, color: 'var(--color-text-primary)' }}>{course.students}</p>
                  </div>
                  <div>
                    <p style={{ fontSize: 10, color: 'var(--color-text-secondary)' }}>Avg attendance</p>
                    <p
                      style={{
                        fontSize: 15,
                        fontWeight: 500,
                        color: course.avgAttendance >= 75 ? '#1D9E75' : '#EF9F27',
                      }}
                    >
                      {course.avgAttendance}%
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </ALISTabsContent>
      </ALISTabs>
    </div>
  )
}
