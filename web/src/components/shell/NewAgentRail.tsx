/**
 * AgentRail — Role-aware AI panel per §5.3 of ALIS_FRONTEND_SPEC.md
 *
 * Skeleton with quick-action chips. AI chat placeholder.
 * Chips come from ROLE_AGENT_CHIPS[role].
 */

import { useState } from 'react'
import { ROLE_AGENT_CHIPS, ROLE_DISPLAY, type FrontendRole } from '../../config/roleConfig'

interface AgentRailProps {
  role: FrontendRole
}

export function NewAgentRail({ role }: AgentRailProps) {
  const chips = ROLE_AGENT_CHIPS[role] || []
  const display = ROLE_DISPLAY[role]
  const [inputValue, setInputValue] = useState('')

  return (
    <div style={{
      width: 320, flexShrink: 0,
      borderLeft: '1px solid var(--color-border)',
      background: 'var(--color-bg-surface)',
      display: 'flex', flexDirection: 'column',
      height: '100vh',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px', borderBottom: '1px solid var(--color-border)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
        height: 56,
      }}>
        <div>
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>
            ALIS Assistant
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: 1 }}>
            {display?.name} — {display?.description}
          </div>
        </div>
      </div>

      {/* Empty state */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 20px' }}>
        <div style={{
          textAlign: 'center', padding: '24px 0',
        }}>
          <div style={{
            width: 48, height: 48, borderRadius: '50%',
            background: 'var(--color-primary-light)', margin: '0 auto 12px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <span style={{ fontSize: 20 }}>✦</span>
          </div>
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-text-primary)' }}>
            AI is ready
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: 4 }}>
            Ask anything about your {display?.description.toLowerCase() || 'workspace'}
          </div>
        </div>

        {/* Quick action chips */}
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
            Quick actions
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {chips.map((chip, i) => (
              <button
                key={i}
                onClick={() => setInputValue(chip.prompt)}
                style={{
                  padding: '6px 12px', borderRadius: 'var(--radius-pill)',
                  border: '1px solid var(--color-border)',
                  background: 'var(--color-bg-surface)', cursor: 'pointer',
                  fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)',
                  fontWeight: 500, transition: 'all 100ms',
                }}
                onMouseEnter={e => {
                  (e.target as HTMLElement).style.borderColor = 'var(--color-primary-border)';
                  (e.target as HTMLElement).style.color = 'var(--color-primary)';
                }}
                onMouseLeave={e => {
                  (e.target as HTMLElement).style.borderColor = 'var(--color-border)';
                  (e.target as HTMLElement).style.color = 'var(--color-text-secondary)';
                }}
              >
                {chip.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Input — disabled placeholder */}
      <div style={{
        padding: '12px 16px', borderTop: '1px solid var(--color-border)',
        display: 'flex', gap: 8,
      }}>
        <input
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          placeholder="Type a message..."
          disabled
          title="AI chat coming soon"
          style={{
            flex: 1, padding: '8px 12px', borderRadius: 'var(--radius-md)',
            border: '1px solid var(--color-border)', background: '#f9fafb',
            fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)',
            outline: 'none',
          }}
        />
        <button
          disabled
          style={{
            width: 36, height: 36, borderRadius: 'var(--radius-md)',
            border: '1px solid var(--color-border)', background: '#f9fafb',
            cursor: 'not-allowed', display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--color-text-muted)', fontSize: 16,
          }}
        >
          ↑
        </button>
      </div>
    </div>
  )
}
