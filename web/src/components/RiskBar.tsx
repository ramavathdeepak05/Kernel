/**
 * RiskBar — student risk score visualization
 * score: 0–100, higher = more at risk
 * Reference: ALIS-skills/references/frontend.md §12
 */

interface RiskBarProps {
  score: number
}

export function RiskBar({ score }: RiskBarProps) {
  const s = Math.max(0, Math.min(100, score))
  const color = s > 70 ? '#E24B4A' : s > 40 ? '#EF9F27' : '#1D9E75'
  const label = s > 70 ? 'High' : s > 40 ? 'Medium' : 'Low'

  return (
    <div>
      <div style={{ width: `${s}%`, height: 5, borderRadius: 3, background: color }} />
      <p style={{ fontSize: 10, color: 'var(--color-text-secondary)', marginTop: 1 }}>
        {label}
      </p>
    </div>
  )
}
