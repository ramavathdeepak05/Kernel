/**
 * StatCard — 4-up statistics card
 * Reference: ALIS-skills/references/frontend.md §7
 */

interface StatCardProps {
  label: string
  value: string | number
  delta?: string
  deltaColor?: string
}

export function StatCard({ label, value, delta, deltaColor = '#94a3b8' }: StatCardProps) {
  return (
    <div
      style={{
        background: 'var(--color-background-secondary)',
        borderRadius: 'var(--radius-md)',
        padding: '10px 12px',
        border: 'var(--border)',
      }}
    >
      <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 4 }}>{label}</p>
      <p style={{ fontSize: 20, fontWeight: 500, color: 'var(--color-text-primary)' }}>{value}</p>
      {delta && (
        <p style={{ fontSize: 11, color: deltaColor, marginTop: 2 }}>{delta}</p>
      )}
    </div>
  )
}

interface StatsRowProps {
  stats: StatCardProps[]
}

/** 4-up stats grid — always 4 columns on desktop, 2×2 on mobile */
export function StatsRow({ stats }: StatsRowProps) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
        gap: 8,
      }}
      className="stats-row"
    >
      {stats.map((stat) => (
        <StatCard key={stat.label} {...stat} />
      ))}
    </div>
  )
}
