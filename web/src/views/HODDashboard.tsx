/**
 * HODDashboard — Department Head overview
 * Reference: ALIS-skills/references/frontend.md §11
 *
 * 4-up stats: dept attendance %, faculty workload, at-risk students, pending approvals
 * Department attendance heat map (course × week)
 * Faculty workload table with overload indicators
 */

import { useState, useEffect } from 'react'
import { useALISStore } from '../store/alis.store'
import { StatsRow } from '../components/StatCard'
import { RiskBar } from '../components/RiskBar'
import { DataTable, type Column } from '../components/DataTable'
import { ALISTabs, ALISTabsList, ALISTabsTrigger, ALISTabsContent } from '../components/ui/alis-tabs'

// ---------------------------------------------------------------------------
// Types + static fallback data
// ---------------------------------------------------------------------------

interface FacultyWorkload {
  id: string
  name: string
  designation: string
  courses: number
  sessionsPerWeek: number
  pendingAssessments: number
  isOverloaded: boolean
}

interface CourseHeatCell {
  course: string
  week1: number
  week2: number
  week3: number
  week4: number
  avg: number
}

const DEPT_STATS_DEFAULT = [
  { label: 'Dept. attendance', value: '—', delta: 'Loading…', deltaColor: '#7B82A8' },
  { label: 'Faculty workload', value: '—', delta: 'avg sessions/week', deltaColor: '#7B82A8' },
  { label: 'At-risk students', value: '—', delta: 'Loading…', deltaColor: '#EF9F27' },
  { label: 'Pending approvals', value: '—', delta: 'Loading…', deltaColor: '#E24B4A' },
]

const HEAT_MAP_FALLBACK: CourseHeatCell[] = []

// ---------------------------------------------------------------------------
// Heat map cell
// ---------------------------------------------------------------------------

function HeatCell({ value }: { value: number }) {
  const color =
    value >= 85 ? '#1D9E75' :
    value >= 75 ? '#4CAF9F' :
    value >= 65 ? '#EF9F27' : '#E24B4A'
  return (
    <div style={{
      background: color + '22',
      color,
      borderRadius: 4,
      padding: '4px 8px',
      fontSize: 12,
      fontWeight: 600,
      textAlign: 'center',
    }}>
      {value}%
    </div>
  )
}

// ---------------------------------------------------------------------------
// Faculty workload table columns
// ---------------------------------------------------------------------------

const FACULTY_COLUMNS: Column<FacultyWorkload>[] = [
  { key: 'name', label: 'Faculty', width: '2fr' },
  { key: 'designation', label: 'Designation', width: '1.5fr' },
  { key: 'courses', label: 'Courses', width: '80px' },
  {
    key: 'sessionsPerWeek',
    label: 'Sessions/wk',
    width: '100px',
    render: (row) => (
      <span style={{
        color: row.isOverloaded ? '#E24B4A' : '#C9D1E9',
        fontWeight: row.isOverloaded ? 700 : 400,
      }}>
        {row.sessionsPerWeek}
        {row.isOverloaded && ' ⚠'}
      </span>
    ),
  },
  {
    key: 'pendingAssessments',
    label: 'Pending',
    width: '80px',
    render: (row) => (
      <span style={{ color: row.pendingAssessments > 10 ? '#EF9F27' : '#C9D1E9' }}>
        {row.pendingAssessments}
      </span>
    ),
  },
  {
    key: 'isOverloaded',
    label: 'Status',
    width: '100px',
    render: (row) => (
      <span style={{
        fontSize: 11,
        padding: '2px 8px',
        borderRadius: 4,
        background: row.isOverloaded ? '#E24B4A22' : '#1D9E7522',
        color: row.isOverloaded ? '#E24B4A' : '#1D9E75',
        fontWeight: 600,
      }}>
        {row.isOverloaded ? 'OVERLOADED' : 'NORMAL'}
      </span>
    ),
  },
]

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const authHeader = () => ({ Authorization: `Bearer ${sessionStorage.getItem('token')}` })

export function HODDashboard() {
  const [stats, setStats] = useState(DEPT_STATS_DEFAULT)
  const [faculty, setFaculty] = useState<FacultyWorkload[]>([])
  const [heatMap, setHeatMap] = useState<CourseHeatCell[]>(HEAT_MAP_FALLBACK)

  useEffect(() => {
    const h = authHeader()
    const currentYear = new Date().getFullYear().toString()

    // Faculty workload
    fetch(`/api/v1/reporting/academics/faculty-workload?academic_year=${currentYear}`, { headers: h })
      .then(r => r.json())
      .then(d => {
        if (d.faculty?.length) {
          const rows: FacultyWorkload[] = d.faculty.map((f: any, i: number) => ({
            id: f.faculty_id || f.id || String(i),
            name: f.name || f.faculty_name || 'Unknown',
            designation: f.designation || f.employment_type || 'Faculty',
            courses: Number(f.course_count ?? f.courses ?? 0),
            sessionsPerWeek: Number(f.sessions_per_week ?? f.weekly_sessions ?? 0),
            pendingAssessments: Number(f.pending_assessments ?? 0),
            isOverloaded: Number(f.sessions_per_week ?? f.weekly_sessions ?? 0) > 10,
          }))
          setFaculty(rows)

          const total = rows.reduce((s, r) => s + r.sessionsPerWeek, 0)
          const avg = rows.length ? (total / rows.length).toFixed(1) : '—'
          setStats(prev => prev.map(s =>
            s.label === 'Faculty workload' ? { ...s, value: avg, deltaColor: '#1D9E75' } : s
          ))
        }
      })
      .catch(() => {})

    // At-risk students
    fetch(`/api/v1/academics/analytics/at-risk?academic_year=${currentYear}`, { headers: h })
      .then(r => r.json())
      .then(d => {
        const total = d.total ?? d.at_risk?.length ?? null
        if (total !== null) {
          setStats(prev => prev.map(s =>
            s.label === 'At-risk students'
              ? { ...s, value: String(total), deltaColor: total > 10 ? '#E24B4A' : '#EF9F27' }
              : s
          ))
        }
      })
      .catch(() => {})

    // Pending approvals
    fetch('/api/v1/approvals?status=PENDING&limit=1', {
      headers: { ...h, 'Content-Type': 'application/json' },
    })
      .then(r => r.json())
      .then(d => {
        const count = d.total ?? d.approval_requests?.length ?? null
        if (count !== null) {
          setStats(prev => prev.map(s =>
            s.label === 'Pending approvals'
              ? { ...s, value: String(count), deltaColor: count > 0 ? '#E24B4A' : '#1D9E75' }
              : s
          ))
        }
      })
      .catch(() => {})
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Stats */}
      <StatsRow stats={stats} />

      {/* Tabs */}
      <ALISTabs defaultValue="workload">
        <ALISTabsList>
          <ALISTabsTrigger value="workload" badge={faculty.length}>Faculty Workload</ALISTabsTrigger>
          <ALISTabsTrigger value="heatmap">Attendance Heat Map</ALISTabsTrigger>
        </ALISTabsList>

        <ALISTabsContent value="workload">
          <DataTable
            title="Faculty Workload"
            columns={FACULTY_COLUMNS}
            rows={faculty}
            onRowClick={() => {}}
          />
        </ALISTabsContent>

        <ALISTabsContent value="heatmap">
          <div style={{
            background: '#11131F',
            border: '1px solid #1E2235',
            borderRadius: 12,
            padding: 20,
          }}>
            <p style={{ color: '#7B82A8', fontSize: 12, margin: '0 0 16px', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
              Attendance Heat Map — Course × Week
            </p>
            {heatMap.length === 0 ? (
              <p style={{ color: '#7B82A8', fontSize: 13, margin: 0 }}>No attendance data available.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr>
                      {['Course', 'Week 1', 'Week 2', 'Week 3', 'Week 4', 'Avg'].map(h => (
                        <th key={h} style={{
                          padding: '8px 12px', textAlign: h === 'Course' ? 'left' : 'center',
                          color: '#7B82A8', fontWeight: 600, fontSize: 11, letterSpacing: '0.04em',
                          borderBottom: '1px solid #1E2235',
                        }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {heatMap.map(row => (
                      <tr key={row.course} style={{ borderBottom: '1px solid #1E2235' }}>
                        <td style={{ padding: '8px 12px', color: '#C9D1E9', fontSize: 13 }}>{row.course}</td>
                        <td style={{ padding: '8px 12px' }}><HeatCell value={row.week1} /></td>
                        <td style={{ padding: '8px 12px' }}><HeatCell value={row.week2} /></td>
                        <td style={{ padding: '8px 12px' }}><HeatCell value={row.week3} /></td>
                        <td style={{ padding: '8px 12px' }}><HeatCell value={row.week4} /></td>
                        <td style={{ padding: '8px 12px' }}><HeatCell value={row.avg} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </ALISTabsContent>
      </ALISTabs>
    </div>
  )
}
