/**
 * QuickActions — context-aware chip row (max 4)
 * Reference: ALIS-skills/references/frontend.md §6
 */

import { useALISStore } from '../../store/alis.store'

interface QuickActionsProps {
  onAction: (action: string) => void
}

export function QuickActions({ onAction }: QuickActionsProps) {
  const { agent } = useALISStore()
  const chips = agent.quickActions.slice(0, 4)

  if (chips.length === 0) return null

  return (
    <div
      style={{
        padding: '6px 12px',
        display: 'flex',
        gap: 4,
        flexWrap: 'wrap',
        borderTop: 'var(--border)',
        flexShrink: 0,
      }}
    >
      {chips.map((chip) => (
        <button
          key={chip}
          onClick={() => onAction(chip)}
          style={{
            padding: '4px 9px',
            borderRadius: 'var(--radius-pill)',
            fontSize: 11,
            background: 'rgba(29,158,117,0.08)',
            color: '#1D9E75',
            border: '0.5px solid rgba(29,158,117,0.2)',
            cursor: 'pointer',
            transition: 'background 0.1s',
            whiteSpace: 'nowrap',
          }}
        >
          {chip}
        </button>
      ))}
    </div>
  )
}
