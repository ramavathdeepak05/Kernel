/**
 * SLABar — SLA time remaining indicator
 * percent = time REMAINING (0–100), not elapsed
 * Reference: ALIS-skills/references/frontend.md §8
 *
 * Color rules (strict):
 *   < 30%  → red   (urgent)
 *   30–59% → amber (approaching)
 *   ≥ 60%  → teal  (on track)
 */

interface SLABarProps {
  percent: number
}

export function SLABar({ percent }: SLABarProps) {
  const p = Math.max(0, Math.min(100, percent))
  const color = p < 30 ? '#E24B4A' : p < 60 ? '#EF9F27' : '#1D9E75'

  return (
    <div>
      <div
        style={{
          width: 50,
          height: 4,
          borderRadius: 2,
          background: 'var(--color-border-tertiary)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${p}%`,
            height: '100%',
            borderRadius: 2,
            background: color,
            transition: 'width 0.3s',
          }}
        />
      </div>
      <p style={{ fontSize: 10, color: 'var(--color-text-secondary)', marginTop: 2 }}>
        SLA {p}%
      </p>
    </div>
  )
}
