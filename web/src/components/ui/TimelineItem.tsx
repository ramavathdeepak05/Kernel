/** TimelineItem — §2.4 of ALIS_FRONTEND_SPEC.md */

interface TimelineItemProps {
  title: string
  subtitle: string
  done: boolean
}

export function TimelineItem({ title, subtitle, done }: TimelineItemProps) {
  return (
    <div style={{ display: 'flex', gap: 12, position: 'relative', paddingBottom: 16 }}>
      {/* Connector line */}
      <div style={{
        position: 'absolute', left: 7, top: 18, bottom: 0, width: 2,
        background: 'var(--color-border)',
      }} />

      {/* Dot */}
      <div style={{
        width: 16, height: 16, borderRadius: '50%', flexShrink: 0, marginTop: 2,
        background: done ? 'var(--color-primary)' : 'transparent',
        border: done ? 'none' : '2px solid var(--color-border-strong)',
        position: 'relative', zIndex: 1,
      }} />

      {/* Content */}
      <div>
        <div style={{
          fontSize: 'var(--text-sm)', fontWeight: 500,
          color: done ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
        }}>
          {title}
        </div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: 2 }}>
          {subtitle}
        </div>
      </div>
    </div>
  )
}
