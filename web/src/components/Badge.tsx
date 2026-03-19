/**
 * Badge — semantic status badge
 * Reference: ALIS-skills/references/frontend.md §9
 *
 * Never use color decoratively — only for semantic status.
 */

export type BadgeVariant = 'red' | 'amber' | 'green' | 'blue' | 'gray' | 'teal'

const BADGE_STYLES: Record<BadgeVariant, { bg: string; color: string }> = {
  red:   { bg: '#FCEBEB', color: '#A32D2D' },
  amber: { bg: '#FAEEDA', color: '#854F0B' },
  green: { bg: '#EAF3DE', color: '#3B6D11' },
  blue:  { bg: '#E6F1FB', color: '#185FA5' },
  gray:  { bg: 'rgba(255,255,255,0.06)', color: '#94a3b8' },
  teal:  { bg: '#E1F5EE', color: '#0F6E56' },
}

interface BadgeProps {
  variant: BadgeVariant
  children: React.ReactNode
  className?: string
}

export function Badge({ variant, children, className }: BadgeProps) {
  const s = BADGE_STYLES[variant]
  return (
    <span
      className={className}
      style={{
        display: 'inline-block',
        padding: '2px 7px',
        borderRadius: 'var(--radius-pill)',
        fontSize: 10,
        fontWeight: 500,
        background: s.bg,
        color: s.color,
        whiteSpace: 'nowrap',
      }}
    >
      {children}
    </span>
  )
}

/** Priority → badge variant — used by approval queue */
export const PRIORITY_BADGE: Record<'urgent' | 'review' | 'routine', BadgeVariant> = {
  urgent:  'red',
  review:  'amber',
  routine: 'blue',
}
