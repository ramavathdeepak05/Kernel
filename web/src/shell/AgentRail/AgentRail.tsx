/**
 * AgentRail — 320px fixed right panel
 * Always visible, always aware.
 * Reference: ALIS-skills/references/frontend.md §6
 */

import * as ToastPrimitive from '@radix-ui/react-toast'
import { useALISStore } from '../../store/alis.store'
import { useQuickActions } from '../../hooks/useQuickActions'
import { AgentHeader } from './AgentHeader'
import { ChatThread } from './ChatThread'
import { QuickActions } from './QuickActions'
import { ChatInput } from './ChatInput'

// Blink animation injected once
const blinkStyle =
  typeof document !== 'undefined' &&
  !document.getElementById('alis-blink-style') &&
  (() => {
    const s = document.createElement('style')
    s.id = 'alis-blink-style'
    s.textContent = `@keyframes alis-blink { 0%,80%,100%{opacity:0.2} 40%{opacity:1} }`
    document.head.appendChild(s)
    return true
  })()
void blinkStyle

export function AgentRail() {
  const { addMessage, setAgentTyping } = useALISStore()

  // Wire quick actions context
  useQuickActions()

  const handleSend = async (text: string) => {
    addMessage({ role: 'user', text })
    setAgentTyping(true)

    // TODO: replace with real AI gateway call via llm_router
    await new Promise((r) => setTimeout(r, 800))
    setAgentTyping(false)
    addMessage({
      role: 'agent',
      text: `Processing: "${text}" — connecting to ALIS backend…`,
    })
  }

  const handleChipAction = (action: string) => {
    handleSend(action)
  }

  return (
    <ToastPrimitive.Provider>
      <aside
        style={{
          width: 320,
          flexShrink: 0,
          borderLeft: 'var(--border)',
          background: 'var(--color-background-primary)',
          display: 'flex',
          flexDirection: 'column',
          height: '100vh',
          position: 'sticky',
          top: 0,
        }}
      >
        <AgentHeader />
        <ChatThread />
        <QuickActions onAction={handleChipAction} />
        <ChatInput onSend={handleSend} />
      </aside>

      {/* Toast viewport — bottom of the canvas, not of this rail */}
      <ToastPrimitive.Viewport
        style={{
          position: 'fixed',
          bottom: 16,
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 9999,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          outline: 'none',
          pointerEvents: 'none',
        }}
      />
    </ToastPrimitive.Provider>
  )
}
