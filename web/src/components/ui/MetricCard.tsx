/** MetricCard — §2.4 of ALIS_FRONTEND_SPEC.md */

interface MetricCardProps {
  label: string
  value: string | number
  delta?: string
  deltaVariant?: 'positive' | 'negative' | 'neutral'
  urgent?: boolean
}

const DELTA_COLORS: Record<string, string> = {
  positive: 'var(--color-success)',
  negative: 'var(--color-danger)',
  neutral:  'var(--color-text-secondary)',
}

export function MetricCard({ label, value, delta, deltaVariant = 'neutral', urgent }: MetricCardProps) {
  return (
    <div style={{
      background: 'var(--color-bg-surface)',
      border: '1px solid var(--color-border)',
      borderLeft: urgent ? '3px solid var(--color-danger)' : '1px solid var(--color-border)',
      borderRadius: 'var(--radius-md)',
      padding: '14px 16px',
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
    }}>
      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {label}
      </span>
      <span style={{ fontSize: 'var(--text-2xl)', fontWeight: 600, color: 'var(--color-text-primary)', lineHeight: 1.1 }}>
        {value}
      </span>
      {delta && (
        <span style={{ fontSize: 'var(--text-xs)', color: DELTA_COLORS[deltaVariant], fontWeight: 500 }}>
          {delta}
        </span>
      )}
    </div>
  )
}
