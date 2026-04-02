/**
 * AgentRail — 320px fixed right panel
 * Always visible, always aware.
 *
 * EXECUTE two-step pattern:
 *   When the agent returns a canvasAction of type EXECUTE or EXECUTE_MODULE,
 *   it must not fire immediately. Instead the agent posts an action-card message
 *   with explicit confirm/skip chips. Only when the user taps the confirm chip
 *   does the action fire. This preserves Layer 2 compliance — the chip click
 *   is the human approval step.
 *
 *   EXECUTE_MODULE actions are dispatched to the module's REST endpoint.
 *   The payload always has status="DRAFT" enforced by the backend parser.
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
import { alisApi } from '../../lib/alis-api'
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
 * EXECUTE and EXECUTE_MODULE actions must become action-cards with confirm/skip chips.
 */
function requiresConfirmation(action: CanvasAction | null): boolean {
  return action?.type === 'EXECUTE' || action?.type === 'EXECUTE_MODULE'
}

/** Map copilot module names to REST API path prefixes */
const MODULE_API_MAP: Record<string, string> = {
  ACADEMICS:        '/academics',
  FINANCE:          '/finance',
  ADMISSIONS:       '/admissions',
  EXAMINATIONS:     '/examinations',
  HR:               '/hr',
  STUDENT_SERVICES: '/student-services',
  COMMUNICATIONS:   '/communications',
  REGULATORY:       '/regulatory',
  ALUMNI:           '/alumni',
  PHD:              '/phd',
  POLICY:           '/policy',
  SETTINGS:         '/admin',
  WORKFLOWS:        '/workflows',
  REPORTS:          '/reporting',
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

    // EXECUTE / EXECUTE_MODULE: post a confirmation action-card.
    if (requiresConfirmation(resp.canvasAction)) {
      const action = resp.canvasAction!

      // Build confirmation chips
      let confirmChips: string[]
      if (action.type === 'EXECUTE_MODULE') {
        confirmChips = action.is_batch
          ? ['Confirm Batch', 'Review Items First', 'Skip']
          : ['Confirm', 'Skip']
      } else if (action.type === 'EXECUTE') {
        confirmChips = [`Confirm ${action.action}`, 'Skip']
      } else {
        confirmChips = ['Confirm', 'Skip']
      }

      // Merge copilot-suggested chips (if any) with default confirm/skip
      if (resp.chips && resp.chips.length > 0) {
        confirmChips = resp.chips
      }

      addMessage({
        role: 'agent',
        text: resp.message ?? 'Please confirm this action.',
        chips: confirmChips,
        canvasAction: resp.canvasAction,
      })
      return
    }

    // Non-EXECUTE actions: dispatch immediately and surface the message
    if (resp.canvasAction) {
      dispatchAgentAction(resp.canvasAction)
    }

    // Use copilot-provided chips, falling back to quickActions
    const responseChips = resp.chips ?? resp.quickActions

    addMessage({
      role: 'agent',
      text: resp.message ?? 'Done.',
      chips: responseChips,
      canvasAction: resp.canvasAction ?? null,
    })
  }

  /**
   * Chip click handler.
   * Confirm chips (prefixed with "Confirm ") fire the pending EXECUTE action
   * from the most recent action-card message. All other chips send as text.
   */
  const handleChipAction = async (chip: string, sourceMsgCanvasAction?: CanvasAction | null) => {
    // --- EXECUTE confirm ---
    if (chip.startsWith('Confirm ') && sourceMsgCanvasAction?.type === 'EXECUTE') {
      dispatchAgentAction(sourceMsgCanvasAction)
      addMessage({ role: 'agent', text: 'Done.' })
      return
    }

    // --- EXECUTE_MODULE confirm ---
    if (
      (chip === 'Confirm' || chip === 'Confirm Batch') &&
      sourceMsgCanvasAction?.type === 'EXECUTE_MODULE'
    ) {
      const { module, actionEndpoint, payload, is_batch } = sourceMsgCanvasAction
      const apiPath = MODULE_API_MAP[module] ?? `/${module.toLowerCase()}`

      addMessage({ role: 'agent', text: is_batch ? 'Processing batch action...' : 'Processing...' })
      try {
        await alisApi.post(`${apiPath}/${actionEndpoint}`, payload)
        addMessage({ role: 'agent', text: is_batch ? 'Batch action submitted successfully.' : 'Action submitted successfully.' })
      } catch (err: unknown) {
        const errMsg = err instanceof Error ? err.message : 'Unknown error'
        addMessage({ role: 'agent', text: `Action failed: ${errMsg}` })
      }
      return
    }

    // --- Review Items First (batch) ---
    if (chip === 'Review Items First' && sourceMsgCanvasAction?.type === 'EXECUTE_MODULE') {
      addMessage({ role: 'agent', text: 'Opening items for review...' })
      // Navigate to the relevant module view so the user can inspect before confirming
      const { module } = sourceMsgCanvasAction
      const moduleKey = module.toLowerCase()
      dispatchAgentAction({ type: 'NAVIGATE', view: `${moduleKey}_dashboard` as never, module: moduleKey as never })
      return
    }

    // --- Skip ---
    if (chip === 'Skip') {
      addMessage({ role: 'agent', text: 'Skipped.' })
      return
    }

    // --- All other chips: send as text to the copilot ---
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
