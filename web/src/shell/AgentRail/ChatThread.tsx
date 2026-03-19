/**
 * ChatThread — scrollable message list
 * Reference: ALIS-skills/references/frontend.md §6
 *
 * Three message variants:
 *   agent   — left-aligned, background-secondary
 *   user    — right-aligned, teal-light background
 *   action  — full-width bordered card with chip buttons
 */

import { useEffect, useRef } from 'react'
import { useALISStore, type ChatMessage } from '../../store/alis.store'

function TypingIndicator() {
  return (
    <div
      style={{
        background: 'var(--color-background-secondary)',
        borderRadius: '0 6px 6px 6px',
        padding: '8px 12px',
        display: 'inline-block',
        marginBottom: 6,
      }}
    >
      <div style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
        {[0, 0.2, 0.4].map((delay, i) => (
          <span
            key={i}
            style={{
              width: 5,
              height: 5,
              borderRadius: '50%',
              background: 'var(--color-text-secondary)',
              animation: `alis-blink 1.2s ${delay}s infinite`,
              display: 'inline-block',
            }}
          />
        ))}
      </div>
    </div>
  )
}

function Message({ msg, onChipClick }: { msg: ChatMessage; onChipClick: (chip: string) => void }) {
  if (msg.chips && msg.chips.length > 0) {
    // Action card
    return (
      <div
        style={{
          border: 'var(--border)',
          borderRadius: 'var(--radius-md)',
          padding: '7px 10px',
          marginBottom: 6,
          width: '100%',
        }}
      >
        <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 4 }}>
          {msg.text}
        </p>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {msg.chips.map((chip) => (
            <button
              key={chip}
              onClick={() => onChipClick(chip)}
              style={{
                padding: '3px 8px',
                borderRadius: 'var(--radius-pill)',
                fontSize: 11,
                background: 'rgba(29,158,117,0.08)',
                color: '#1D9E75',
                border: '0.5px solid rgba(29,158,117,0.2)',
                cursor: 'pointer',
              }}
            >
              {chip}
            </button>
          ))}
        </div>
      </div>
    )
  }

  if (msg.role === 'agent') {
    return (
      <div
        style={{
          alignSelf: 'flex-start',
          background: 'var(--color-background-secondary)',
          borderRadius: '0 6px 6px 6px',
          padding: '8px 10px',
          fontSize: 12,
          color: 'var(--color-text-primary)',
          maxWidth: '85%',
          marginBottom: 6,
          lineHeight: 1.5,
        }}
      >
        {msg.text}
      </div>
    )
  }

  // User message
  return (
    <div
      style={{
        alignSelf: 'flex-end',
        background: '#E1F5EE',
        color: '#085041',
        borderRadius: '6px 0 6px 6px',
        padding: '8px 10px',
        fontSize: 12,
        maxWidth: '85%',
        marginBottom: 6,
        lineHeight: 1.5,
      }}
    >
      {msg.text}
    </div>
  )
}

export function ChatThread() {
  const { chat, agent, addMessage } = useALISStore()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chat.messages, agent.isTyping])

  const handleChipClick = (chip: string) => {
    addMessage({ role: 'user', text: chip })
  }

  return (
    <div
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: '10px 12px',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {chat.messages.map((msg) => (
        <Message key={msg.id} msg={msg} onChipClick={handleChipClick} />
      ))}
      {agent.isTyping && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  )
}
