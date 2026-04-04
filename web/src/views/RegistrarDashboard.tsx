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
// API data fetching — real endpoints
// ---------------------------------------------------------------------------

const API_BASE = import.meta.env.VITE_API_URL || "/api/v1";

async function fetchApprovals(): Promise<ApprovalItem[]> {
  const token = sessionStorage.getItem("token");
  if (!token) return [];
  try {
    const res = await fetch(`${API_BASE}/approvals/pending?limit=20`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return [];
    const data = await res.json();
    return (data.items ?? data ?? []).map((item: Record<string, unknown>) => ({
      id: String(item.id ?? ""),
      title: String(item.title ?? item.description ?? ""),
      subtitle: String(item.subtitle ?? item.module ?? ""),
      priority: item.priority === "urgent" ? "urgent" : item.priority === "review" ? "review" : "routine",
      slaPercent: Number(item.sla_percent ?? item.slaPercent ?? 50),
      module: String(item.module ?? ""),
      canAutoApprove: Boolean(item.can_auto_approve ?? item.canAutoApprove ?? false),
    })) as ApprovalItem[];
  } catch {
    return [];
  }
}

async function fetchStats(): Promise<{ label: string; value: string; delta: string; deltaColor: string }[]> {
  const token = sessionStorage.getItem("token");
  if (!token) return [];
  try {
    const res = await fetch(`${API_BASE}/reports/dashboard/kpis`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return [];
    const kpis = await res.json();
    return [
      { label: "Pending approvals", value: String(kpis.pending_approvals ?? "0"), delta: `${kpis.urgent_count ?? 0} urgent`, deltaColor: "#E24B4A" },
      { label: "Enrolled this year", value: String(kpis.enrolled_count ?? "0"), delta: kpis.enrolled_delta ?? "", deltaColor: "#1D9E75" },
      { label: "Exams this week", value: String(kpis.exams_this_week ?? "0"), delta: kpis.exams_delta ?? "", deltaColor: "#EF9F27" },
      { label: "Docs issued today", value: String(kpis.docs_issued_today ?? "0"), delta: kpis.docs_delta ?? "", deltaColor: "#1D9E75" },
    ];
  } catch {
    return [];
  }
}

const EMPTY_STATS = [
  { label: "Pending approvals", value: "—", delta: "", deltaColor: "#94a3b8" },
  { label: "Enrolled this year", value: "—", delta: "", deltaColor: "#94a3b8" },
  { label: "Exams this week", value: "—", delta: "", deltaColor: "#94a3b8" },
  { label: "Docs issued today", value: "—", delta: "", deltaColor: "#94a3b8" },
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
  const [queue, setQueue] = useState<ApprovalItem[]>([])
  const [stats, setStats] = useState(EMPTY_STATS)
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState<ToastState>(CLOSED_TOAST)
  const prevHighlightRef = useRef<string | null>(null)

  // Fetch real data on mount
  useEffect(() => {
    setLoading(true)
    Promise.all([fetchApprovals(), fetchStats()])
      .then(([approvals, kpis]) => {
        setQueue(approvals)
        if (kpis.length > 0) setStats(kpis)
      })
      .finally(() => setLoading(false))
  }, [])

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
        <StatsRow stats={stats} />

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
