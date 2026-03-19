/**
 * AgentBottomSheet — mobile agent panel (50vh bottom sheet)
 *
 * Appears when the floating action button is tapped on mobile.
 * Reuses the same store and child components as the desktop AgentRail
 * so conversation state is shared across desktop ↔ mobile.
 *
 * Reference: ALIS-skills/references/frontend.md §1 (mobile)
 */

import { useEffect, useRef } from 'react'
import { useALISStore } from '../store/alis.store'
import { ChatThread } from './AgentRail/ChatThread'
import { QuickActions } from './AgentRail/QuickActions'
import { ChatInput } from './AgentRail/ChatInput'

interface Props {
  open: boolean
  onClose: () => void
}

export function AgentBottomSheet({ open, onClose }: Props) {
  const { addMessage, setAgentTyping } = useALISStore()
  const sheetRef = useRef<HTMLDivElement>(null)

  // Lock body scroll while sheet is open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  const handleSend = async (text: string) => {
    addMessage({ role: 'user', text })
    setAgentTyping(true)
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

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.35)',
          zIndex: 300,
          backdropFilter: 'blur(2px)',
        }}
      />

      {/* Sheet */}
      <div
        ref={sheetRef}
        style={{
          position: 'fixed',
          left: 0,
          right: 0,
          bottom: 0,
          height: '50vh',
          minHeight: 300,
          background: 'var(--color-background-primary)',
          borderRadius: '16px 16px 0 0',
          boxShadow: '0 -4px 32px rgba(0,0,0,0.2)',
          zIndex: 301,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Drag handle + header */}
        <div
          style={{
            padding: '10px 16px 8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: 'var(--border)',
            flexShrink: 0,
          }}
        >
          {/* Drag affordance */}
          <div style={{ flex: 1 }} />
          <div
            style={{
              position: 'absolute',
              left: '50%',
              transform: 'translateX(-50%)',
              top: 8,
              width: 36,
              height: 4,
              borderRadius: 2,
              background: 'var(--color-border, #d0d5dd)',
            }}
          />

          {/* Title */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              flex: 1,
              justifyContent: 'center',
            }}
          >
            <div
              style={{
                width: 20,
                height: 20,
                borderRadius: 4,
                background: '#1D9E75',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <span style={{ color: '#fff', fontWeight: 700, fontSize: 10 }}>A</span>
            </div>
            <span style={{ fontWeight: 600, fontSize: 13 }}>ALIS Agent</span>
          </div>

          {/* Close */}
          <div style={{ flex: 1, display: 'flex', justifyContent: 'flex-end' }}>
            <button
              onClick={onClose}
              aria-label="Close agent"
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 4,
                borderRadius: 4,
                fontSize: 18,
                color: 'var(--color-text-secondary)',
                lineHeight: 1,
              }}
            >
              ×
            </button>
          </div>
        </div>

        {/* Chat content */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <ChatThread />
        </div>

        {/* Quick actions */}
        <QuickActions onAction={handleChipAction} />

        {/* Input */}
        <ChatInput onSend={handleSend} />
      </div>
    </>
  )
}
