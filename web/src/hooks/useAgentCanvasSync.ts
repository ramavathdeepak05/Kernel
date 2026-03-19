/**
 * useAgentCanvasSync — wires agent CanvasActions to the canvas
 *
 * Execute canvasAction BEFORE rendering the message in the thread —
 * so the dashboard moves first, then the text appears.
 * Reference: ALIS-skills/references/frontend.md §5, §18
 */

import { useEffect, useRef } from 'react'
import { useALISStore } from '../store/alis.store'

export function useAgentCanvasSync() {
  const {
    agent,
    canvas,
    setCanvasView,
    highlightItem,
    highlightMultiple,
    clearHighlight,
    clearPendingAction,
  } = useALISStore()

  const lastActionRef = useRef<string | null>(null)

  useEffect(() => {
    const action = agent.pendingAction
    if (!action) return

    // Deduplicate — same action object ref might re-trigger
    const actionKey = JSON.stringify(action)
    if (lastActionRef.current === actionKey) return
    lastActionRef.current = actionKey

    switch (action.type) {
      case 'NAVIGATE':
        setCanvasView(action.view, action.module, action.filters)
        break

      case 'HIGHLIGHT':
        highlightItem(action.itemId)
        if (action.scrollTo) {
          requestAnimationFrame(() => {
            document.getElementById(`qi-${action.itemId}`)?.scrollIntoView({
              behavior: 'smooth',
              block: 'center',
            })
          })
        }
        break

      case 'HIGHLIGHT_MULTIPLE':
        highlightMultiple(action.itemIds)
        // Scroll to first
        if (action.itemIds[0]) {
          requestAnimationFrame(() => {
            document.getElementById(`qi-${action.itemIds[0]}`)?.scrollIntoView({
              behavior: 'smooth',
              block: 'center',
            })
          })
        }
        break

      case 'FILTER':
        setCanvasView(canvas.view, canvas.module, action.filters)
        break

      case 'CLEAR_HIGHLIGHT':
        clearHighlight()
        break

      case 'OPEN_DETAIL':
        // Module pages handle this via their own local state
        // We highlight so the canvas knows which row is selected
        highlightItem(action.itemId)
        break

      case 'EXECUTE':
        // Dispatch a custom event; the hosting view handles it
        window.dispatchEvent(
          new CustomEvent('alis:execute', {
            detail: { action: action.action, itemId: action.itemId },
          }),
        )
        break
    }

    // Clear so the action isn't re-executed on re-render
    clearPendingAction()
  }, [agent.pendingAction]) // eslint-disable-line react-hooks/exhaustive-deps
}
