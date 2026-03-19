/**
 * useQuickActions — returns context-aware action chips for the current
 * canvas view + user role.
 *
 * Chips change every time the canvas view changes.
 * Reference: ALIS-skills/references/frontend.md §6
 */

import { useEffect } from 'react'
import { useALISStore } from '../store/alis.store'
import { useALISRole } from './useALISRole'
import { getQuickActions } from '../lib/quick-actions'

export function useQuickActions() {
  const { canvas, setQuickActions } = useALISStore()
  const { role } = useALISRole()

  useEffect(() => {
    const actions = getQuickActions(canvas.view, role)
    setQuickActions(actions)
  }, [canvas.view, role]) // eslint-disable-line react-hooks/exhaustive-deps
}
