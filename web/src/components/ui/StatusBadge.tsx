/** StatusBadge — §2.4 of ALIS_FRONTEND_SPEC.md */

interface StatusBadgeProps {
  status: 'pending' | 'review' | 'active' | 'urgent' | 'done'
}

const STYLES: Record<string, { bg: string; color: string; label: string }> = {
  pending: { bg: 'var(--color-warning-bg)', color: 'var(--color-warning)', label: 'Pending' },
  review:  { bg: 'var(--color-info-bg)',    color: 'var(--color-info)',    label: 'Review' },
  active:  { bg: 'var(--color-success-bg)', color: 'var(--color-success)', label: 'Active' },
  urgent:  { bg: 'var(--color-danger-bg)',  color: 'var(--color-danger)',  label: 'Urgent' },
  done:    { bg: '#f3f4f6',                 color: 'var(--color-text-muted)', label: 'Done' },
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const s = STYLES[status] || STYLES.pending
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 'var(--radius-pill)',
      fontSize: 'var(--text-xs)', fontWeight: 600,
      background: s.bg, color: s.color,
    }}>
      {s.label}
    </span>
  )
}
