/**
 * AgentHeader — live dot + label + context line
 * Reference: ALIS-skills/references/frontend.md §6
 *
 * No avatar. No bot icon. No robot emoji.
 * The green dot is the only identity marker.
 */

import { useALISStore } from '../../store/alis.store'

export function AgentHeader() {
  const { agent } = useALISStore()
  return (
    <div
      style={{
        height: 44,
        borderBottom: 'var(--border)',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '0 12px',
        flexShrink: 0,
      }}
    >
      {/* Live dot — static, no pulse */}
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: '50%',
          background: '#1D9E75',
          flexShrink: 0,
        }}
      />
      <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--color-text-primary)' }}>
        ALIS Agent
      </span>
      <span
        style={{
          fontSize: 10,
          color: 'var(--color-text-secondary)',
          marginLeft: 'auto',
          textAlign: 'right',
          maxWidth: 160,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {agent.contextLabel}
      </span>
    </div>
  )
}
