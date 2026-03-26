/**
 * AgentRail — 320px fixed right panel
 * Always visible, always aware.
 *
 * EXECUTE two-step pattern:
 *   When the agent returns a canvasAction of type EXECUTE, it must not fire
 *   immediately. Instead the agent posts an action-card message with explicit
 *   confirm/skip chips. Only when the user taps the confirm chip does EXECUTE
 *   fire through the canvas. This preserves Layer 2 compliance — the chip
 *   click is the human approval step for low-stakes single-step operations.
 *
 * Reference: ALIS-skills/references/frontend.md §6
 */

import * as ToastPrimitive from '@radix-ui/react-toast'
import { useALISStore } from '../../store/alis.store'
import { useAuthStore } from '../../store/authStore'
import { useALISRole } from '../../hooks/useALISRole'
import { useQuickActions } from '../../hooks/useQuickActions'
import { AgentHeader } from './AgentHeader'
import { ChatThread } from './ChatThread'
import { QuickActions } from './QuickActions'
import { ChatInput } from './ChatInput'
import { invokeRailAgent } from '../../lib/agent-gateway'
import type { CanvasAction } from '../../lib/canvas-actions'

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

/**
 * Determine whether a canvasAction requires an explicit second confirmation.
 * EXECUTE actions proposing a write operation must never fire automatically —
 * they become an action-card with confirm/skip chips.
 */
function requiresConfirmation(action: CanvasAction | null): boolean {
  return action?.type === 'EXECUTE'
}

export function AgentRail() {
  const {
    canvas,
    chat,
    agent,
    addMessage,
    setAgentTyping,
    dispatchAgentAction,
    setAgentContextHint,
  } = useALISStore()
  const { user } = useAuthStore()
  const { role } = useALISRole()

  // Wire context-aware quick action chips
  useQuickActions()

  const handleSend = async (text: string) => {
    if (!user) return

    addMessage({ role: 'user', text })
    setAgentTyping(true)

    // Pass last 5 messages (already in store) for reference resolution
    const recentMessages = chat.messages
      .slice(-6, -1) // exclude the message we just added
      .map((m) => ({ role: m.role, text: m.text }))

    const resp = await invokeRailAgent({
      actorId: user.id,
      orgId: user.tenant_id,
      role,
      view: canvas.view,
      message: text,
      agentContext: agent.agentContext,
      recentMessages,
    })

    setAgentTyping(false)

    // Persist the new agentContext hint for the next call
    if (resp.agentContext !== undefined) {
      setAgentContextHint(resp.agentContext ?? null)
    }

    // EXECUTE actions: post a confirmation action-card instead of firing immediately.
    // The user must explicitly tap "Confirm" for the action to dispatch.
    if (requiresConfirmation(resp.canvasAction)) {
      const execAction = resp.canvasAction as Extract<CanvasAction, { type: 'EXECUTE' }>
      addMessage({
        role: 'agent',
        text: resp.message ?? `Confirm: ${execAction.action} this item?`,
        chips: [
          `Confirm ${execAction.action}`,
          'Skip',
        ],
        // Store the pending action in the message so the chip handler can access it
        canvasAction: resp.canvasAction,
      })
      return
    }

    // Non-EXECUTE actions: dispatch immediately and surface the message
    if (resp.canvasAction) {
      dispatchAgentAction(resp.canvasAction)
    }

    addMessage({
      role: 'agent',
      text: resp.message ?? 'Done.',
      chips: resp.quickActions,
      canvasAction: resp.canvasAction ?? null,
    })
  }

  /**
   * Chip click handler.
   * Confirm chips (prefixed with "Confirm ") fire the pending EXECUTE action
   * from the most recent action-card message. All other chips send as text.
   */
  const handleChipAction = (chip: string, sourceMsgCanvasAction?: CanvasAction | null) => {
    if (chip.startsWith('Confirm ') && sourceMsgCanvasAction?.type === 'EXECUTE') {
      dispatchAgentAction(sourceMsgCanvasAction)
      addMessage({ role: 'agent', text: 'Done.' })
      return
    }
    if (chip === 'Skip') {
      addMessage({ role: 'agent', text: 'Skipped.' })
      return
    }
    handleSend(chip)
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
        <ChatThread onChipAction={handleChipAction} />
        <QuickActions onAction={(a) => handleChipAction(a)} />
        <ChatInput onSend={handleSend} />
      </aside>

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
