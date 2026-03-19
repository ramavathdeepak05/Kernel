/**
 * ApprovalRow — single row in the approval queue
 * Reference: ALIS-skills/references/frontend.md §8
 */

import { Badge, PRIORITY_BADGE } from './Badge'
import { SLABar } from './SLABar'

export interface ApprovalItem {
  id: string
  title: string
  subtitle: string
  priority: 'urgent' | 'review' | 'routine'
  slaPercent: number
  module: string
  canAutoApprove: boolean
}

interface ApprovalRowProps {
  item: ApprovalItem
  isHighlighted: boolean
  isLast: boolean
  onApprove?: (id: string) => void
  onReject?: (id: string) => void
  onSelect?: (id: string) => void
}

export function ApprovalRow({
  item,
  isHighlighted,
  isLast,
  onApprove,
  onReject,
  onSelect,
}: ApprovalRowProps) {
  const overdue = item.slaPercent === 0

  return (
    <div
      id={`qi-${item.id}`}
      onClick={() => onSelect?.(item.id)}
      style={{
        display: 'grid',
        gridTemplateColumns: '3fr 1.2fr 1fr auto',
        alignItems: 'center',
        gap: 8,
        padding: '9px 12px',
        background: isHighlighted
          ? 'var(--color-background-secondary)'
          : 'var(--color-background-primary)',
        borderLeft: isHighlighted
          ? '2.5px solid var(--alis-teal)'
          : overdue
          ? '2.5px solid #E24B4A'
          : '2.5px solid transparent',
        borderBottom: isLast ? 'none' : 'var(--border)',
        cursor: 'pointer',
        transition: 'background 0.12s',
        outline: overdue ? '1px solid rgba(226,75,74,0.3)' : 'none',
      }}
    >
      {/* Title + subtitle */}
      <div>
        <p style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-text-primary)' }}>
          {item.title}
        </p>
        <p
          style={{
            fontSize: 11,
            color: 'var(--color-text-secondary)',
            marginTop: 1,
          }}
        >
          {item.subtitle}
        </p>
      </div>

      {/* Priority badge */}
      <Badge variant={PRIORITY_BADGE[item.priority]}>
        {item.priority.charAt(0).toUpperCase() + item.priority.slice(1)}
      </Badge>

      {/* SLA bar */}
      <SLABar percent={item.slaPercent} />

      {/* Actions */}
      <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
        <button
          onClick={(e) => { e.stopPropagation(); onApprove?.(item.id) }}
          style={{
            padding: '3px 8px',
            borderRadius: 'var(--radius-sm)',
            fontSize: 11,
            fontWeight: 500,
            background: 'rgba(29,158,117,0.12)',
            color: '#1D9E75',
            border: '0.5px solid rgba(29,158,117,0.25)',
            cursor: 'pointer',
          }}
        >
          ✓
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); onReject?.(item.id) }}
          style={{
            padding: '3px 8px',
            borderRadius: 'var(--radius-sm)',
            fontSize: 11,
            fontWeight: 500,
            background: 'rgba(226,75,74,0.08)',
            color: '#E24B4A',
            border: '0.5px solid rgba(226,75,74,0.2)',
            cursor: 'pointer',
          }}
        >
          ✕
        </button>
      </div>
    </div>
  )
}
