/**
 * useAgentContext — fires a proactive context query whenever the canvas
 * view changes, and populates the agent rail chat thread with the result.
 *
 * Call pattern: __view_change__ → backend queries live counts → returns
 * brief only if the agent_rail_silence policy returns SURFACE.
 * Stays silent otherwise (message: null).
 *
 * Mount once inside ALISShell so the proactive call fires from one place.
 *
 * Reference: ALIS-skills/references/frontend.md §6
 */

import { useEffect, useRef } from 'react'
import { useALISStore } from '../store/alis.store'
import { useAuthStore } from '../store/authStore'
import { useALISRole } from './useALISRole'
import { invokeRailAgent } from '../lib/agent-gateway'

export function useAgentContext() {
  const {
    canvas,
    agent,
    addMessage,
    dispatchAgentAction,
    setAgentContext,
    setAgentContextHint,
  } = useALISStore()
  const { user } = useAuthStore()
  const { role } = useALISRole()

  const lastViewRef = useRef<string | null>(null)

  useEffect(() => {
    if (!user) return
    if (canvas.view === lastViewRef.current) return
    lastViewRef.current = canvas.view

    setAgentContext(canvas.view.replace(/_/g, ' '))

    invokeRailAgent({
      actorId: user.id,
      orgId: user.tenant_id,
      role,
      view: canvas.view,
      message: '__view_change__',
      agentContext: agent.agentContext,
      recentMessages: [],  // view-change doesn't need history
    }).then((resp) => {
      if (resp.agentContext !== undefined) {
        setAgentContextHint(resp.agentContext ?? null)
      }

      if (resp.message) {
        addMessage({
          role: 'agent',
          text: resp.message,
          canvasAction: resp.canvasAction ?? null,
          chips: resp.quickActions,
        })
      }

      if (resp.canvasAction && !resp.message) {
        dispatchAgentAction(resp.canvasAction)
      }
    })
    // invokeRailAgent never throws — returns SILENT on any failure
  }, [canvas.view, user?.id]) // eslint-disable-line react-hooks/exhaustive-deps
}
