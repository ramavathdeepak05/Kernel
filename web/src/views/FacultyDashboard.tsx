/**
 * FacultyDashboard — at-risk student list + course tiles
 * Reference: ALIS-skills/references/frontend.md §11
 *
 * Density: medium (Faculty/HOD role)
 * Default view: my_courses
 */

import { useState } from 'react'
import { useALISStore } from '../store/alis.store'
import { StatsRow } from '../components/StatCard'
import { RiskBar } from '../components/RiskBar'
import { DataTable, type Column } from '../components/DataTable'

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

interface AtRiskStudent {
  id: string
  name: string
  rollNo: string
  course: string
  attendance: number
  riskScore: number
  flag: string
}

const AT_RISK: AtRiskStudent[] = [
  { id: 's01', name: 'Arjun Mehta', rollNo: '22CS041', course: 'Data Structures', attendance: 52, riskScore: 84, flag: 'Below 60% attendance' },
  { id: 's02', name: 'Divya Nair', rollNo: '22CS017', course: 'OS & Networks', attendance: 61, riskScore: 72, flag: 'Missed 2 assessments' },
  { id: 's03', name: 'Rohit Bose', rollNo: '22EC008', course: 'Digital Electronics', attendance: 58, riskScore: 78, flag: 'Below 60% attendance' },
  { id: 's04', name: 'Sneha Pillai', rollNo: '22CS053', course: 'DBMS', attendance: 65, riskScore: 55, flag: 'Inconsistent submissions' },
  { id: 's05', name: 'Karan Sharma', rollNo: '22ME021', course: 'Thermodynamics', attendance: 70, riskScore: 48, flag: 'Low internal marks' },
  { id: 's06', name: 'Pooja Reddy', rollNo: '22CS031', course: 'Data Structures', attendance: 55, riskScore: 81, flag: 'Below 60% attendance' },
]

const COURSES = [
  { id: 'c1', code: 'CS301', name: 'Data Structures & Algorithms', students: 58, pending: 4, avgAttendance: 74 },
  { id: 'c2', code: 'CS302', name: 'Database Management Systems', students: 61, pending: 1, avgAttendance: 81 },
  { id: 'c3', code: 'CS303', name: 'Operating Systems', students: 55, pending: 2, avgAttendance: 69 },
  { id: 'c4', code: 'CS304', name: 'Computer Networks', students: 60, pending: 0, avgAttendance: 86 },
]

const STATS = [
  { label: 'My courses', value: '4', delta: 'Semester 5' },
  { label: 'At-risk students', value: '6', delta: '↑ 2 this week', deltaColor: '#EF9F27' },
  { label: 'Avg attendance', value: '77%', delta: 'Target: 75%', deltaColor: '#1D9E75' },
  { label: 'Pending marks', value: '7', delta: '2 overdue', deltaColor: '#E24B4A' },
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
  const [activeTab, setActiveTab] = useState<'risk' | 'courses'>('risk')

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
      <StatsRow stats={STATS} />

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 2, borderBottom: 'var(--border)', paddingBottom: 0 }}>
        {(['risk', 'courses'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '6px 14px',
              fontSize: 12,
              fontWeight: 500,
              background: 'none',
              border: 'none',
              borderBottom: activeTab === tab ? '2px solid var(--alis-teal)' : '2px solid transparent',
              color: activeTab === tab ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
              cursor: 'pointer',
              textTransform: 'capitalize',
              transition: 'color 0.12s',
            }}
          >
            {tab === 'risk' ? 'At-risk students' : 'My courses'}
          </button>
        ))}
      </div>

      {/* At-risk students table */}
      {activeTab === 'risk' && (
        <DataTable
          columns={AT_RISK_COLUMNS}
          rows={AT_RISK}
          highlightedId={canvas.highlightedItemId}
          onRowClick={(row) => highlightItem(row.id)}
          gridTemplateColumns="2fr 1fr 2fr 80px 100px 2fr"
        />
      )}

      {/* Course tiles */}
      {activeTab === 'courses' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
          {COURSES.map((course) => (
            <div
              key={course.id}
              style={{
                background: 'var(--color-background-secondary)',
                border: 'var(--border)',
                borderRadius: 'var(--radius-md)',
                padding: '12px 14px',
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
      )}
    </div>
  )
}
