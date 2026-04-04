/** ProgressRow — §2.4 of ALIS_FRONTEND_SPEC.md */

interface ProgressRowProps {
  label: string
  value: number  // 0–100
  variant?: 'default' | 'warn' | 'danger' | 'success'
}

const BAR_COLORS: Record<string, string> = {
  default: 'var(--color-primary)',
  warn:    'var(--color-warning)',
  danger:  'var(--color-danger)',
  success: 'var(--color-success)',
}

export function ProgressRow({ label, value, variant = 'default' }: ProgressRowProps) {
  const color = BAR_COLORS[variant]

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
      <span style={{ width: 140, flexShrink: 0, fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {label}
      </span>
      <div style={{ flex: 1, height: 6, background: 'var(--color-border)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${Math.min(value, 100)}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.3s ease' }} />
      </div>
      <span style={{ width: 32, textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color }}>
        {value}%
      </span>
    </div>
  )
}
