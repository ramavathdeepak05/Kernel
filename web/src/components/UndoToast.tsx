/**
 * UndoToast — 30s reversible action toast
 *
 * Every approval action shows this toast. It auto-dismisses at 30s.
 * Reference: ALIS-skills/references/frontend.md §14
 *
 * Uses Radix Toast — never position: fixed inline.
 */

import * as ToastPrimitive from '@radix-ui/react-toast'
import { useEffect, useRef, useState } from 'react'

interface UndoToastProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  message: string
  onUndo: () => void
  /** Countdown duration in ms. Default: 30000 */
  duration?: number
}

export function UndoToast({
  open,
  onOpenChange,
  message,
  onUndo,
  duration = 30000,
}: UndoToastProps) {
  const [remaining, setRemaining] = useState(100)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const startRef = useRef<number>(0)

  useEffect(() => {
    if (!open) {
      setRemaining(100)
      if (intervalRef.current) clearInterval(intervalRef.current)
      return
    }
    startRef.current = Date.now()
    intervalRef.current = setInterval(() => {
      const elapsed = Date.now() - startRef.current
      const pct = Math.max(0, 100 - (elapsed / duration) * 100)
      setRemaining(pct)
      if (pct === 0) {
        if (intervalRef.current) clearInterval(intervalRef.current)
      }
    }, 100)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [open, duration])

  return (
    <ToastPrimitive.Root
      open={open}
      onOpenChange={onOpenChange}
      duration={duration}
      style={{
        background: 'var(--color-background-elevated)',
        border: 'var(--border-emphasis)',
        borderRadius: 'var(--radius-md)',
        padding: '8px 12px',
        minWidth: 260,
        boxShadow: '0 4px 24px rgba(0,0,0,0.4)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'space-between' }}>
        <ToastPrimitive.Title
          style={{ fontSize: 12, fontWeight: 500, color: 'var(--color-text-primary)' }}
        >
          {message}
        </ToastPrimitive.Title>
        <ToastPrimitive.Action
          altText="Undo"
          onClick={onUndo}
          style={{
            padding: '2px 8px',
            borderRadius: 'var(--radius-sm)',
            fontSize: 11,
            fontWeight: 500,
            background: 'rgba(29,158,117,0.12)',
            color: '#1D9E75',
            border: '0.5px solid rgba(29,158,117,0.25)',
            cursor: 'pointer',
            flexShrink: 0,
          }}
        >
          Undo
        </ToastPrimitive.Action>
      </div>
      {/* Countdown bar */}
      <div
        style={{
          marginTop: 6,
          height: 2,
          borderRadius: 1,
          background: 'var(--color-border-tertiary)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${remaining}%`,
            height: '100%',
            background: '#1D9E75',
            transition: 'width 0.1s linear',
          }}
        />
      </div>
    </ToastPrimitive.Root>
  )
}
