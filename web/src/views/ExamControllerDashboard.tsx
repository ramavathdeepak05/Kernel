/**
 * ExamControllerDashboard — CoE (Controller of Examinations) view
 * Reference: ALIS-skills/references/frontend.md §11
 *
 * 4-up stats: eligible students, hall tickets dispatched, papers in vault, days to exam
 * Paper dispatch status table (program, mode)
 * Pending AI score confirmations queue (EC-EXM-05)
 * Revaluation / supplementary overlap alerts
 */

import { useState } from 'react'
import { useALISStore } from '../store/alis.store'
import { StatsRow } from '../components/StatCard'
import { DataTable, type Column } from '../components/DataTable'
import { Badge } from '../components/Badge'

// ---------------------------------------------------------------------------
// Types + mock data
// ---------------------------------------------------------------------------

type DispatchMode = 'ONLINE_VAULT' | 'OFFLINE_USB' | 'EMERGENCY_PRINT'

interface PaperDispatch {
  id: string
  program: string
  examDate: string
  mode: DispatchMode
  status: 'DISPATCHED' | 'PENDING' | 'IN_VAULT' | 'DELIVERED'
  papers: number
}

interface AIScoreItem {
  id: string
  studentRoll: string
  course: string
  question: string
  aiConfidence: number
  status: 'FACULTY_REVIEW' | 'AI_PENDING'
  waitingHours: number
}

interface RevalAlert {
  id: string
  student: string
  course: string
  issue: string
  severity: 'HIGH' | 'MEDIUM' | 'LOW'
}

const STATS = [
  { label: 'Eligible students', value: '1,842', delta: '96.4% of enrolled', deltaColor: '#1D9E75' },
  { label: 'Hall tickets dispatched', value: '1,786', delta: '97% issued', deltaColor: '#1D9E75' },
  { label: 'Papers in vault', value: '24', delta: '8 programs', deltaColor: '#5D5FEF' },
  { label: 'Days to exam', value: '7', delta: 'Nov 18 start', deltaColor: '#EF9F27' },
]

const DISPATCH_TABLE: PaperDispatch[] = [
  { id: 'p1', program: 'B.Tech CSE', examDate: '2025-11-18', mode: 'ONLINE_VAULT', status: 'IN_VAULT', papers: 62 },
  { id: 'p2', program: 'B.Tech ECE', examDate: '2025-11-18', mode: 'ONLINE_VAULT', status: 'IN_VAULT', papers: 48 },
  { id: 'p3', program: 'B.Tech ME', examDate: '2025-11-19', mode: 'OFFLINE_USB', status: 'PENDING', papers: 41 },
  { id: 'p4', program: 'MBA', examDate: '2025-11-20', mode: 'ONLINE_VAULT', status: 'DISPATCHED', papers: 93 },
  { id: 'p5', program: 'BCA', examDate: '2025-11-21', mode: 'OFFLINE_USB', status: 'DELIVERED', papers: 56 },
  { id: 'p6', program: 'B.Sc CS', examDate: '2025-11-22', mode: 'EMERGENCY_PRINT', status: 'PENDING', papers: 34 },
]

const AI_SCORE_QUEUE: AIScoreItem[] = [
  { id: 'ai1', studentRoll: '22CS041', course: 'DS Lab', question: 'Q7 — Linked List impl.', aiConfidence: 0.38, status: 'FACULTY_REVIEW', waitingHours: 14 },
  { id: 'ai2', studentRoll: '22EC017', course: 'Signals', question: 'Q3 — Fourier analysis', aiConfidence: 0.52, status: 'FACULTY_REVIEW', waitingHours: 6 },
  { id: 'ai3', studentRoll: '22CS008', course: 'DS Lab', question: 'Q12 — Graph BFS', aiConfidence: 0.71, status: 'AI_PENDING', waitingHours: 2 },
  { id: 'ai4', studentRoll: '22ME021', course: 'Thermodynamics', question: 'Q5 — Carnot cycle', aiConfidence: 0.45, status: 'FACULTY_REVIEW', waitingHours: 20 },
]

const REVAL_ALERTS: RevalAlert[] = [
  { id: 'r1', student: 'Arjun Mehta (22CS041)', course: 'CS301', issue: 'Revaluation result overlaps with supplementary exam date', severity: 'HIGH' },
  { id: 'r2', student: 'Priya Nair (22EC017)', course: 'EC201', issue: 'Grace mark application pending — hall ticket blocked', severity: 'HIGH' },
  { id: 'r3', student: 'Rohit Bose (22CS008)', course: 'CS302', issue: 'Supplementary result not yet declared — enrollment hold', severity: 'MEDIUM' },
]

// ---------------------------------------------------------------------------
// Mode badge
// ---------------------------------------------------------------------------

const MODE_COLORS: Record<DispatchMode, string> = {
  ONLINE_VAULT: '#5D5FEF',
  OFFLINE_USB: '#EF9F27',
  EMERGENCY_PRINT: '#E24B4A',
}

function ModeBadge({ mode }: { mode: DispatchMode }) {
  return (
    <span style={{
      fontSize: 11, padding: '2px 8px', borderRadius: 4, fontWeight: 600,
      background: MODE_COLORS[mode] + '22', color: MODE_COLORS[mode],
    }}>
      {mode.replace('_', ' ')}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Table columns
// ---------------------------------------------------------------------------

const DISPATCH_COLS: Column<PaperDispatch>[] = [
  { key: 'program', label: 'Program', width: '2fr' },
  { key: 'examDate', label: 'Exam Date', width: '120px' },
  { key: 'mode', label: 'Mode', width: '140px', render: (r) => <ModeBadge mode={r.mode} /> },
  { key: 'papers', label: 'Papers', width: '80px' },
  {
    key: 'status', label: 'Status', width: '120px',
    render: (r) => (
      <Badge
        label={r.status}
        color={r.status === 'DELIVERED' ? 'green' : r.status === 'IN_VAULT' ? 'blue' : r.status === 'DISPATCHED' ? 'purple' : 'yellow'}
      />
    ),
  },
]

const AI_COLS: Column<AIScoreItem>[] = [
  { key: 'studentRoll', label: 'Roll No', width: '100px' },
  { key: 'course', label: 'Course', width: '120px' },
  { key: 'question', label: 'Question', width: '3fr' },
  {
    key: 'aiConfidence', label: 'AI Conf.', width: '100px',
    render: (r) => (
      <span style={{ color: r.aiConfidence < 0.6 ? '#E24B4A' : '#1D9E75', fontWeight: 600 }}>
        {(r.aiConfidence * 100).toFixed(0)}%
      </span>
    ),
  },
  {
    key: 'status', label: 'Status', width: '140px',
    render: (r) => (
      <Badge
        label={r.status === 'FACULTY_REVIEW' ? 'Needs Review' : 'AI Pending'}
        color={r.status === 'FACULTY_REVIEW' ? 'red' : 'yellow'}
      />
    ),
  },
  {
    key: 'waitingHours', label: 'Waiting', width: '80px',
    render: (r) => (
      <span style={{ color: r.waitingHours > 12 ? '#E24B4A' : '#7B82A8' }}>
        {r.waitingHours}h
      </span>
    ),
  },
]

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ExamControllerDashboard() {
  const [tab, setTab] = useState<'dispatch' | 'ai_queue' | 'reval'>('dispatch')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <StatsRow stats={STATS} />

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8 }}>
        {[
          { key: 'dispatch', label: 'Paper Dispatch' },
          { key: 'ai_queue', label: `AI Score Review (${AI_SCORE_QUEUE.length})` },
          { key: 'reval', label: `Reval Alerts (${REVAL_ALERTS.length})` },
        ].map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key as typeof tab)}
            style={{
              padding: '6px 16px', borderRadius: 6, border: 'none', cursor: 'pointer',
              fontSize: 13, fontWeight: 600,
              background: tab === t.key ? '#5D5FEF' : '#1A1D2E',
              color: tab === t.key ? '#fff' : '#7B82A8',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'dispatch' && (
        <DataTable
          title="Paper Dispatch Status"
          columns={DISPATCH_COLS}
          rows={DISPATCH_TABLE}
          onRowClick={() => {}}
        />
      )}

      {tab === 'ai_queue' && (
        <DataTable
          title="AI Score Confirmation Queue — Faculty Review Required"
          columns={AI_COLS}
          rows={AI_SCORE_QUEUE}
          onRowClick={() => {}}
        />
      )}

      {tab === 'reval' && (
        <div style={{
          background: '#11131F', border: '1px solid #1E2235', borderRadius: 12, padding: 20,
        }}>
          <p style={{ color: '#7B82A8', fontSize: 12, margin: '0 0 16px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Revaluation / Supplementary Overlap Alerts
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {REVAL_ALERTS.map(alert => (
              <div key={alert.id} style={{
                display: 'flex', alignItems: 'flex-start', gap: 12,
                padding: '12px 16px', borderRadius: 8,
                background: alert.severity === 'HIGH' ? '#E24B4A11' : '#EF9F2711',
                border: `1px solid ${alert.severity === 'HIGH' ? '#E24B4A33' : '#EF9F2733'}`,
              }}>
                <span style={{
                  fontSize: 11, padding: '2px 8px', borderRadius: 4, fontWeight: 700, flexShrink: 0, marginTop: 2,
                  background: alert.severity === 'HIGH' ? '#E24B4A22' : '#EF9F2722',
                  color: alert.severity === 'HIGH' ? '#E24B4A' : '#EF9F27',
                }}>
                  {alert.severity}
                </span>
                <div>
                  <p style={{ margin: 0, color: '#C9D1E9', fontSize: 13, fontWeight: 600 }}>{alert.student}</p>
                  <p style={{ margin: '2px 0 0', color: '#7B82A8', fontSize: 12 }}>
                    {alert.course} — {alert.issue}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
