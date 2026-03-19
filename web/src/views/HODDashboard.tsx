/**
 * HODDashboard — Department Head overview
 * Reference: ALIS-skills/references/frontend.md §11
 *
 * 4-up stats: dept attendance %, faculty workload, at-risk students, pending approvals
 * Department attendance heat map (course × week)
 * Faculty workload table with overload indicators
 */

import { useState } from 'react'
import { useALISStore } from '../store/alis.store'
import { StatsRow } from '../components/StatCard'
import { RiskBar } from '../components/RiskBar'
import { DataTable, type Column } from '../components/DataTable'

// ---------------------------------------------------------------------------
// Types + mock data
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

const DEPT_STATS = [
  { label: 'Dept. attendance', value: '74%', delta: 'Target: 75%', deltaColor: '#EF9F27' },
  { label: 'Faculty workload', value: '3.8', delta: 'avg sessions/week', deltaColor: '#1D9E75' },
  { label: 'At-risk students', value: '14', delta: '↑ 3 from last week', deltaColor: '#EF9F27' },
  { label: 'Pending approvals', value: '5', delta: '2 urgent', deltaColor: '#E24B4A' },
]

const FACULTY_WORKLOAD: FacultyWorkload[] = [
  { id: 'f1', name: 'Dr. Priya Menon', designation: 'Professor', courses: 3, sessionsPerWeek: 6, pendingAssessments: 8, isOverloaded: false },
  { id: 'f2', name: 'Prof. Ramesh Kumar', designation: 'Assoc. Professor', courses: 5, sessionsPerWeek: 12, pendingAssessments: 15, isOverloaded: true },
  { id: 'f3', name: 'Dr. Anjali Singh', designation: 'Asst. Professor', courses: 4, sessionsPerWeek: 10, pendingAssessments: 6, isOverloaded: false },
  { id: 'f4', name: 'Mr. Suresh Nair', designation: 'Lecturer', courses: 3, sessionsPerWeek: 7, pendingAssessments: 4, isOverloaded: false },
  { id: 'f5', name: 'Dr. Kavitha Rao', designation: 'Professor', courses: 6, sessionsPerWeek: 14, pendingAssessments: 20, isOverloaded: true },
]

const HEAT_MAP: CourseHeatCell[] = [
  { course: 'CS301 — Data Structures', week1: 78, week2: 72, week3: 65, week4: 71, avg: 72 },
  { course: 'CS302 — DBMS', week1: 85, week2: 83, week3: 80, week4: 84, avg: 83 },
  { course: 'CS303 — OS', week1: 68, week2: 65, week3: 61, week4: 67, avg: 65 },
  { course: 'CS304 — Networks', week1: 90, week2: 88, week3: 87, week4: 89, avg: 89 },
  { course: 'CS305 — Algorithms', week1: 74, week2: 70, week3: 68, week4: 73, avg: 71 },
]

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

export function HODDashboard() {
  const [activeTab, setActiveTab] = useState<'workload' | 'heatmap'>('workload')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Stats */}
      <StatsRow stats={DEPT_STATS} />

      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: 8 }}>
        {(['workload', 'heatmap'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '6px 16px',
              borderRadius: 6,
              border: 'none',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 600,
              background: activeTab === tab ? '#5D5FEF' : '#1A1D2E',
              color: activeTab === tab ? '#fff' : '#7B82A8',
            }}
          >
            {tab === 'workload' ? 'Faculty Workload' : 'Attendance Heat Map'}
          </button>
        ))}
      </div>

      {/* Faculty workload table */}
      {activeTab === 'workload' && (
        <DataTable
          title="Faculty Workload"
          columns={FACULTY_COLUMNS}
          rows={FACULTY_WORKLOAD}
          onRowClick={() => {}}
        />
      )}

      {/* Attendance heat map */}
      {activeTab === 'heatmap' && (
        <div style={{
          background: '#11131F',
          border: '1px solid #1E2235',
          borderRadius: 12,
          padding: 20,
        }}>
          <p style={{ color: '#7B82A8', fontSize: 12, margin: '0 0 16px', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
            Attendance Heat Map — Course × Week
          </p>
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
                {HEAT_MAP.map(row => (
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
        </div>
      )}
    </div>
  )
}
