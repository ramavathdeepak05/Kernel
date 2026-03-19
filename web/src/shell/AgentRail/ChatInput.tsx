/**
 * ChatInput — text input + send button
 * Reference: ALIS-skills/references/frontend.md §6
 */

import { useState, type KeyboardEvent } from 'react'

interface ChatInputProps {
  onSend: (text: string) => void
  disabled?: boolean
}

export function ChatInput({ onSend, disabled = false }: ChatInputProps) {
  const [value, setValue] = useState('')

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div
      style={{
        padding: '8px 10px',
        borderTop: 'var(--border)',
        display: 'flex',
        gap: 6,
        alignItems: 'flex-end',
        flexShrink: 0,
      }}
    >
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask ALIS…"
        rows={1}
        disabled={disabled}
        style={{
          flex: 1,
          resize: 'none',
          background: 'var(--color-background-secondary)',
          border: 'var(--border)',
          borderRadius: 'var(--radius-sm)',
          padding: '6px 8px',
          fontSize: 12,
          color: 'var(--color-text-primary)',
          outline: 'none',
          lineHeight: 1.4,
          maxHeight: 80,
          overflow: 'auto',
          fontFamily: 'inherit',
        }}
      />
      <button
        onClick={handleSend}
        disabled={!value.trim() || disabled}
        style={{
          width: 28,
          height: 28,
          borderRadius: 'var(--radius-sm)',
          background: value.trim() ? '#1D9E75' : 'rgba(255,255,255,0.06)',
          color: value.trim() ? '#fff' : '#94a3b8',
          border: 'none',
          cursor: value.trim() ? 'pointer' : 'default',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 14,
          flexShrink: 0,
          transition: 'background 0.12s',
        }}
      >
        ↑
      </button>
    </div>
  )
}
