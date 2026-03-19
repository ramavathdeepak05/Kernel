/**
 * RegistrarDashboard — FE-1 approval queue (the sales demo)
 * Reference: ALIS-skills/references/frontend.md §8, §11
 *
 * - 4-up stats: pending approvals, enrolled, exams this week, docs issued
 * - Approval queue sorted urgent-first (lowest slaPercent first)
 * - Agent highlight-on-command: useEffect on canvas.highlightedItemId → DOM scroll
 * - Undo toast on every approve/reject (30s window)
 */

import { useEffect, useRef, useState } from 'react'
import * as ToastPrimitive from '@radix-ui/react-toast'

import { useALISStore } from '../store/alis.store'
import { StatsRow } from '../components/StatCard'
import { ApprovalRow, type ApprovalItem } from '../components/ApprovalRow'
import { UndoToast } from '../components/UndoToast'

// ---------------------------------------------------------------------------
// Mock data (replace with API hook when MSW layer is wired)
// ---------------------------------------------------------------------------

const INITIAL_QUEUE: ApprovalItem[] = [
  {
    id: 'apr-001',
    title: 'Hall ticket batch — B.Tech CSE 2025',
    subtitle: '142 students · Examination · Expires 3h 12m',
    priority: 'urgent',
    slaPercent: 8,
    module: 'examinations',
    canAutoApprove: false,
  },
  {
    id: 'apr-002',
    title: 'Fee waiver — Priya Sharma (ROLL-2024-0047)',
    subtitle: 'SC category · ₹18,400 waiver request · Finance',
    priority: 'urgent',
    slaPercent: 14,
    module: 'finance',
    canAutoApprove: false,
  },
  {
    id: 'apr-003',
    title: 'Transcript release — 6 alumni',
    subtitle: 'Post-graduation verification · Alumni module',
    priority: 'urgent',
    slaPercent: 22,
    module: 'alumni',
    canAutoApprove: true,
  },
  {
    id: 'apr-004',
    title: 'Leave application — Dr. Anand Rao',
    subtitle: 'HOD · Computer Science · 4 days medical',
    priority: 'review',
    slaPercent: 38,
    module: 'hr',
    canAutoApprove: false,
  },
  {
    id: 'apr-005',
    title: 'Bonafide certificate — 12 students',
    subtitle: 'Visa processing · Bulk request · Student Services',
    priority: 'review',
    slaPercent: 51,
    module: 'student_services',
    canAutoApprove: true,
  },
  {
    id: 'apr-006',
    title: 'New course proposal — Data Engineering',
    subtitle: 'Faculty: Dr. Kavitha · Academics board review',
    priority: 'review',
    slaPercent: 58,
    module: 'academics',
    canAutoApprove: false,
  },
  {
    id: 'apr-007',
    title: 'Hostel room reallocation — 3 students',
    subtitle: 'Block C, Room 204 → 312 · Maintenance conflict',
    priority: 'routine',
    slaPercent: 74,
    module: 'student_services',
    canAutoApprove: true,
  },
  {
    id: 'apr-008',
    title: 'Vendor invoice — Lab consumables',
    subtitle: '₹2,34,000 · PO-2025-0821 · Finance Controller',
    priority: 'routine',
    slaPercent: 91,
    module: 'finance',
    canAutoApprove: false,
  },
]

const STATS = [
  { label: 'Pending approvals', value: '8', delta: '3 urgent', deltaColor: '#E24B4A' },
  { label: 'Enrolled this year', value: '1,847', delta: '+12 this week', deltaColor: '#1D9E75' },
  { label: 'Exams this week', value: '14', delta: '2 halls unassigned', deltaColor: '#EF9F27' },
  { label: 'Docs issued today', value: '63', delta: '↑ 18% vs yesterday', deltaColor: '#1D9E75' },
]

// ---------------------------------------------------------------------------

interface ToastState {
  open: boolean
  message: string
  undoFn: () => void
}

const CLOSED_TOAST: ToastState = { open: false, message: '', undoFn: () => {} }

export function RegistrarDashboard() {
  const { canvas, highlightItem } = useALISStore()
  const [queue, setQueue] = useState<ApprovalItem[]>(INITIAL_QUEUE)
  const [toast, setToast] = useState<ToastState>(CLOSED_TOAST)
  const prevHighlightRef = useRef<string | null>(null)

  // Agent highlight-on-command: scroll to highlighted row
  useEffect(() => {
    const id = canvas.highlightedItemId
    if (!id || id === prevHighlightRef.current) return
    prevHighlightRef.current = id
    requestAnimationFrame(() => {
      document.getElementById(`qi-${id}`)?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      })
    })
  }, [canvas.highlightedItemId])

  function handleApprove(id: string) {
    const item = queue.find((q) => q.id === id)
    if (!item) return
    setQueue((q) => q.filter((r) => r.id !== id))
    setToast({
      open: true,
      message: `Approved: ${item.title.slice(0, 48)}`,
      undoFn: () => setQueue((q) => [item, ...q].sort(sortQueue)),
    })
  }

  function handleReject(id: string) {
    const item = queue.find((q) => q.id === id)
    if (!item) return
    setQueue((q) => q.filter((r) => r.id !== id))
    setToast({
      open: true,
      message: `Rejected: ${item.title.slice(0, 48)}`,
      undoFn: () => setQueue((q) => [item, ...q].sort(sortQueue)),
    })
  }

  function handleSelect(id: string) {
    highlightItem(id)
  }

  const sorted = [...queue].sort(sortQueue)

  return (
    <ToastPrimitive.Provider swipeDirection="right">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* Page header */}
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
          <div>
            <h1
              style={{
                fontSize: 15,
                fontWeight: 600,
                color: 'var(--color-text-primary)',
                letterSpacing: '-0.01em',
              }}
            >
              Approval Queue
            </h1>
            <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
              {sorted.length} pending · sorted by urgency
            </p>
          </div>
          <span
            style={{
              fontSize: 10,
              fontWeight: 500,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'var(--color-text-secondary)',
            }}
          >
            Registrar view
          </span>
        </div>

        {/* 4-up stats */}
        <StatsRow stats={STATS} />

        {/* Section label */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            paddingBottom: 4,
            borderBottom: 'var(--border)',
          }}
        >
          <span
            style={{
              fontSize: 10,
              fontWeight: 500,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'var(--color-text-secondary)',
            }}
          >
            Pending actions
          </span>
          {sorted.filter((i) => i.slaPercent < 30).length > 0 && (
            <span
              style={{
                fontSize: 10,
                fontWeight: 500,
                padding: '1px 6px',
                borderRadius: 'var(--radius-pill)',
                background: 'rgba(226,75,74,0.12)',
                color: '#E24B4A',
                border: '0.5px solid rgba(226,75,74,0.25)',
              }}
            >
              {sorted.filter((i) => i.slaPercent < 30).length} urgent
            </span>
          )}
        </div>

        {/* Approval queue */}
        <div
          style={{
            border: 'var(--border)',
            borderRadius: 'var(--radius-md)',
            overflow: 'hidden',
          }}
        >
          {/* Column headers */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '3fr 1.2fr 1fr auto',
              gap: 8,
              padding: '6px 12px',
              background: 'var(--color-background-secondary)',
              borderBottom: 'var(--border)',
            }}
          >
            {['Item', 'Priority', 'SLA remaining', ''].map((h) => (
              <span
                key={h}
                style={{
                  fontSize: 10,
                  fontWeight: 500,
                  color: 'var(--color-text-secondary)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}
              >
                {h}
              </span>
            ))}
          </div>

          {sorted.length === 0 ? (
            <div
              style={{
                padding: '32px 12px',
                textAlign: 'center',
                fontSize: 13,
                color: 'var(--color-text-secondary)',
              }}
            >
              All clear — no pending approvals
            </div>
          ) : (
            sorted.map((item, i) => (
              <ApprovalRow
                key={item.id}
                item={item}
                isHighlighted={canvas.highlightedItemId === item.id}
                isLast={i === sorted.length - 1}
                onApprove={handleApprove}
                onReject={handleReject}
                onSelect={handleSelect}
              />
            ))
          )}
        </div>
      </div>

      {/* Undo toast */}
      <UndoToast
        open={toast.open}
        onOpenChange={(open) => setToast((t) => ({ ...t, open }))}
        message={toast.message}
        onUndo={() => {
          toast.undoFn()
          setToast(CLOSED_TOAST)
        }}
      />

      <ToastPrimitive.Viewport
        style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          zIndex: 9999,
          listStyle: 'none',
          margin: 0,
          padding: 0,
        }}
      />
    </ToastPrimitive.Provider>
  )
}

function sortQueue(a: ApprovalItem, b: ApprovalItem): number {
  return a.slaPercent - b.slaPercent
}
