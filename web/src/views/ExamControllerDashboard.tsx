/**
 * ExamControllerDashboard — CoE (Controller of Examinations) view
 * Reference: ALIS-skills/references/frontend.md §11
 *
 * 4-up stats: eligible students, hall tickets dispatched, papers in vault, days to exam
 * Paper dispatch status table (program, mode)
 * Pending AI score confirmations queue (EC-EXM-05)
 * Revaluation / supplementary overlap alerts
 */

import { useState, useEffect } from 'react'
import { useALISStore } from '../store/alis.store'
import { StatsRow } from '../components/StatCard'
import { DataTable, type Column } from '../components/DataTable'
import { Badge } from '../components/Badge'
import { ALISTabs, ALISTabsList, ALISTabsTrigger, ALISTabsContent } from '../components/ui/alis-tabs'

// ---------------------------------------------------------------------------
// Types + static fallback data
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

const STATS_DEFAULT = [
  { label: 'Eligible students', value: '—', delta: 'Loading…', deltaColor: '#7B82A8' },
  { label: 'Hall tickets dispatched', value: '—', delta: 'Loading…', deltaColor: '#7B82A8' },
  { label: 'Papers in vault', value: '—', delta: 'Loading…', deltaColor: '#5D5FEF' },
  { label: 'Days to exam', value: '—', delta: 'Loading…', deltaColor: '#EF9F27' },
]

const DISPATCH_FALLBACK: PaperDispatch[] = []
const AI_QUEUE_FALLBACK: AIScoreItem[] = []
const REVAL_FALLBACK: RevalAlert[] = []

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

const authHeader = () => ({ Authorization: `Bearer ${sessionStorage.getItem('token')}` })

export function ExamControllerDashboard() {
  const [stats, setStats] = useState(STATS_DEFAULT)
  const [schedules, setSchedules] = useState<PaperDispatch[]>(DISPATCH_FALLBACK)
  const [aiQueue, setAiQueue] = useState<AIScoreItem[]>(AI_QUEUE_FALLBACK)
  const [revalAlerts, setRevalAlerts] = useState<RevalAlert[]>(REVAL_FALLBACK)

  useEffect(() => {
    const h = authHeader()
    const currentYear = new Date().getFullYear().toString()

    // Paper dispatch schedule list
    fetch(`/api/v1/examinations/schedules?academic_year=${currentYear}`, { headers: h })
      .then(r => r.json())
      .then(d => {
        if (d.schedules?.length) {
          const rows: PaperDispatch[] = d.schedules.map((s: any) => ({
            id: s.id,
            program: s.program_name || s.course_code || 'Unknown',
            examDate: s.exam_date || '',
            mode: (s.dispatch_mode || 'ONLINE_VAULT') as DispatchMode,
            status: (s.status || 'PENDING') as PaperDispatch['status'],
            papers: s.registered_count || 0,
          }))
          setSchedules(rows)

          const inVault = d.schedules.filter((s: any) => s.status === 'IN_VAULT').length
          const upcoming = d.schedules
            .map((s: any) => new Date(s.exam_date))
            .filter((dt: Date) => dt > new Date())
            .sort((a: Date, b: Date) => a.getTime() - b.getTime())
          const days = upcoming.length
            ? Math.ceil((upcoming[0].getTime() - Date.now()) / 86400000)
            : null
          const dateLabel = upcoming.length
            ? upcoming[0].toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
            : '—'

          setStats(prev => prev.map(s => {
            if (s.label === 'Papers in vault')
              return { ...s, value: String(inVault), delta: `${d.total} programs`, deltaColor: '#5D5FEF' }
            if (s.label === 'Days to exam' && days !== null)
              return { ...s, value: String(days), delta: `${dateLabel} start`, deltaColor: '#EF9F27' }
            return s
          }))
        }
      })
      .catch(() => {})

    // AI eval faculty review queue
    fetch('/api/v1/examinations/ai-eval/faculty-review-queue', { headers: h })
      .then(r => r.json())
      .then(d => {
        if (d.items?.length) {
          const rows: AIScoreItem[] = d.items.map((item: any) => ({
            id: item.id,
            studentRoll: item.roll_number || item.student_id?.slice(0, 8) || '—',
            course: item.course_code || '—',
            question: item.question_id || '—',
            aiConfidence: Number(item.ai_confidence) || 0,
            status: (item.status || 'FACULTY_REVIEW') as AIScoreItem['status'],
            waitingHours: item.waiting_hours || 0,
          }))
          setAiQueue(rows)
        }
      })
      .catch(() => {})

    // Revaluation pending
    fetch('/api/v1/examinations/reeval/pending', { headers: h })
      .then(r => r.json())
      .then(d => {
        if (d.reeval_requests?.length) {
          const rows: RevalAlert[] = d.reeval_requests.map((r: any) => ({
            id: r.id,
            student: `${r.student_name || 'Student'} (${r.roll_number || r.student_id?.slice(0, 8) || '?'})`,
            course: r.course_code || r.exam_schedule_id || '—',
            issue: r.reason || r.notes || 'Revaluation pending',
            severity: (
              r.urgency === 'HIGH' || (r.days_pending && r.days_pending > 14)
                ? 'HIGH'
                : r.days_pending && r.days_pending > 7
                  ? 'MEDIUM'
                  : 'LOW'
            ) as RevalAlert['severity'],
          }))
          setRevalAlerts(rows)
        }
      })
      .catch(() => {})
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <StatsRow stats={stats} />

      {/* Tabs */}
      <ALISTabs defaultValue="dispatch">
        <ALISTabsList>
          <ALISTabsTrigger value="dispatch" badge={schedules.length}>Paper Dispatch</ALISTabsTrigger>
          <ALISTabsTrigger value="ai_queue" badge={aiQueue.length}>AI Score Review</ALISTabsTrigger>
          <ALISTabsTrigger value="reval" badge={revalAlerts.length}>Reval Alerts</ALISTabsTrigger>
        </ALISTabsList>

        <ALISTabsContent value="dispatch">
          <DataTable
            title="Paper Dispatch Status"
            columns={DISPATCH_COLS}
            rows={schedules}
            onRowClick={() => {}}
          />
        </ALISTabsContent>

        <ALISTabsContent value="ai_queue">
          <DataTable
            title="AI Score Confirmation Queue — Faculty Review Required"
            columns={AI_COLS}
            rows={aiQueue}
            onRowClick={() => {}}
          />
        </ALISTabsContent>

        <ALISTabsContent value="reval">
          <div style={{
            background: '#11131F', border: '1px solid #1E2235', borderRadius: 12, padding: 20,
          }}>
            <p style={{ color: '#7B82A8', fontSize: 12, margin: '0 0 16px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Revaluation / Supplementary Overlap Alerts
            </p>
            {revalAlerts.length === 0 ? (
              <p style={{ color: '#7B82A8', fontSize: 13, margin: 0 }}>No pending alerts.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {revalAlerts.map(alert => (
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
            )}
          </div>
        </ALISTabsContent>
      </ALISTabs>
    </div>
  )
}
