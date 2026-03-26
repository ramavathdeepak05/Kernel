/**
 * TimelinePanel — Entity activity debugger ("Why did this happen?")
 *
 * Fetches GET /api/v1/audit/timeline/{entity_type}/{entity_id} and renders
 * a vertical chronological timeline of every auditable event for the entity.
 *
 * Usage:
 *   <TimelinePanel entityType="application" entityId="APP-2026-000001" />
 *   <TimelinePanel entityType="policy" entityId="attendance_eligibility" />
 *
 * Visual pattern: vertical left-border line + colored dot + time + label + detail.
 * Matches the audit-tab pattern already used in ProcessEnginePage.tsx.
 */

import { useEffect, useState } from 'react'
import { alisApi } from '../lib/alis-api'

// ─── Types ──────────────────────────────────────────────────────────────────

interface TimelineEvent {
  id: number
  timestamp: string
  action: string
  label: string
  actor_id: string
  actor_role: string | null
  color: 'green' | 'blue' | 'amber' | 'red' | 'muted'
  icon: string
  metadata: Record<string, unknown>
  formatted_detail: string | null
}

interface TimelinePanelProps {
  entityType: string
  entityId: string
  title?: string
  /** Max height before scroll; defaults to 480px */
  maxHeight?: number
}

// ─── Color map ───────────────────────────────────────────────────────────────

const DOT_COLOR: Record<string, string> = {
  green: '#1D9E75',
  blue:  '#3B82F6',
  amber: '#EF9F27',
  red:   '#E24B4A',
  muted: '#6B7280',
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true })
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

function groupByDay(events: TimelineEvent[]): Array<{ date: string; events: TimelineEvent[] }> {
  const groups: Record<string, TimelineEvent[]> = {}
  for (const ev of events) {
    const key = ev.timestamp.slice(0, 10)  // YYYY-MM-DD
    if (!groups[key]) groups[key] = []
    groups[key].push(ev)
  }
  return Object.entries(groups).map(([date, evs]) => ({
    date: formatDate(evs[0].timestamp),
    events: evs,
  }))
}

// ─── Component ───────────────────────────────────────────────────────────────

export function TimelinePanel({ entityType, entityId, title, maxHeight = 480 }: TimelinePanelProps) {
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    alisApi
      .get<TimelineEvent[]>(`/audit/timeline/${entityType}/${entityId}`)
      .then(setEvents)
      .catch((err) => setError(err?.message ?? 'Failed to load timeline'))
      .finally(() => setLoading(false))
  }, [entityType, entityId])

  const groups = groupByDay(events)

  return (
    <div style={{ fontFamily: 'var(--font-mono, monospace)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)', margin: 0 }}>
          {title ?? 'Activity Timeline'}
        </p>
        {!loading && (
          <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>
            {events.length} event{events.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '20px 0' }}>
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              style={{
                width: 6, height: 6, borderRadius: '50%',
                background: 'var(--color-text-secondary)',
                opacity: 0.4,
                animation: `blink 1.2s ${i * 0.2}s infinite`,
              }}
            />
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <p style={{ fontSize: 12, color: '#E24B4A', margin: 0 }}>{error}</p>
      )}

      {/* Empty */}
      {!loading && !error && events.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--color-text-secondary)', margin: 0 }}>
          No activity recorded yet.
        </p>
      )}

      {/* Timeline */}
      {!loading && !error && events.length > 0 && (
        <div style={{ overflowY: 'auto', maxHeight }}>
          {groups.map((group) => (
            <div key={group.date}>
              {/* Day divider */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '12px 0 8px' }}>
                <div style={{ flex: 1, height: 1, background: 'var(--color-border-secondary)' }} />
                <span style={{ fontSize: 10, color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
                  {group.date}
                </span>
                <div style={{ flex: 1, height: 1, background: 'var(--color-border-secondary)' }} />
              </div>

              {/* Events in this day */}
              <div style={{ position: 'relative', paddingLeft: 20 }}>
                {/* Vertical rail */}
                <div
                  style={{
                    position: 'absolute',
                    left: 6,
                    top: 8,
                    bottom: 8,
                    width: 1,
                    background: 'var(--color-border-secondary)',
                  }}
                />

                {group.events.map((ev) => {
                  const dotColor = DOT_COLOR[ev.color] ?? DOT_COLOR.muted
                  return (
                    <div
                      key={ev.id}
                      style={{ display: 'flex', gap: 12, marginBottom: 14, position: 'relative' }}
                    >
                      {/* Dot */}
                      <div
                        style={{
                          position: 'absolute',
                          left: -14,
                          top: 4,
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          background: dotColor,
                          flexShrink: 0,
                          boxShadow: `0 0 0 2px var(--color-surface-primary)`,
                        }}
                      />

                      {/* Content */}
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                          <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--color-text-primary)' }}>
                            {ev.label}
                          </span>
                          <span style={{ fontSize: 10, color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
                            {formatTime(ev.timestamp)}
                          </span>
                        </div>

                        {/* Human-readable detail (from policy traces, state transitions, etc.) */}
                        {ev.formatted_detail && (
                          <p style={{
                            fontSize: 11,
                            color: 'var(--color-text-secondary)',
                            margin: '2px 0 0',
                            fontFamily: 'monospace',
                            whiteSpace: 'pre-line',
                          }}>
                            {ev.formatted_detail}
                          </p>
                        )}

                        {/* Actor */}
                        <p style={{ fontSize: 10, color: 'var(--color-text-tertiary)', margin: '2px 0 0' }}>
                          {ev.actor_role ? `${ev.actor_role} · ` : ''}{ev.actor_id}
                        </p>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
