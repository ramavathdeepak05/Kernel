/** SectionCard — §2.4 of ALIS_FRONTEND_SPEC.md */

import type { ReactNode } from 'react'

interface SectionCardProps {
  title: string
  action?: { label: string; onClick: () => void }
  children: ReactNode
}

export function SectionCard({ title, action, children }: SectionCardProps) {
  return (
    <div style={{
      background: 'var(--color-bg-surface)',
      border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius-lg)',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '12px 16px',
        borderBottom: '1px solid var(--color-border)',
      }}>
        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
          {title}
        </span>
        {action && (
          <button onClick={action.onClick} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            fontSize: 'var(--text-xs)', color: 'var(--color-primary)', fontWeight: 600,
          }}>
            {action.label}
          </button>
        )}
      </div>

      {/* Body */}
      <div>{children}</div>
    </div>
  )
}
