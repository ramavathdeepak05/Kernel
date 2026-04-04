/**
 * StatCard — 4-up statistics card with animated counters
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
      className="group relative overflow-hidden transition-all duration-200"
      style={{
        background: 'var(--color-background-secondary)',
        borderRadius: 'var(--radius-md)',
        padding: '12px 14px',
        border: 'var(--border)',
      }}
    >
      {/* Hover tint — green */}
      <div
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
        style={{
          background: 'linear-gradient(135deg, rgba(29,158,117,0.06) 0%, transparent 70%)',
        }}
      />

      <p className="relative" style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 6 }}>{label}</p>

      <div className="relative flex items-baseline gap-0.5">
        <p style={{ fontSize: 20, fontWeight: 500, color: 'var(--color-text-primary)', margin: 0 }}>{value}</p>
      </div>

      {delta && (
        <p className="relative" style={{ fontSize: 11, color: deltaColor, marginTop: 4 }}>{delta}</p>
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
