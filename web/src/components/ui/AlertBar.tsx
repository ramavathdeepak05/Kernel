/** AlertBar — §2.4 of ALIS_FRONTEND_SPEC.md */

import type { ReactNode } from 'react'

interface AlertBarProps {
  variant: 'info' | 'warning' | 'danger' | 'success'
  children: ReactNode
}

const ALERT_STYLES: Record<string, { bg: string; border: string; color: string }> = {
  info:    { bg: 'var(--color-info-bg)',    border: 'var(--color-info-border)',    color: 'var(--color-info)' },
  warning: { bg: 'var(--color-warning-bg)', border: 'var(--color-warning-border)', color: 'var(--color-warning)' },
  danger:  { bg: 'var(--color-danger-bg)',  border: 'var(--color-danger-border)',  color: 'var(--color-danger)' },
  success: { bg: 'var(--color-success-bg)', border: 'var(--color-success-border)', color: 'var(--color-success)' },
}

export function AlertBar({ variant, children }: AlertBarProps) {
  const s = ALERT_STYLES[variant]
  return (
    <div style={{
      background: s.bg, border: `1px solid ${s.border}`, borderRadius: 'var(--radius-md)',
      padding: '10px 14px', fontSize: 'var(--text-sm)', color: s.color, fontWeight: 500,
      lineHeight: 1.5,
    }}>
      {children}
    </div>
  )
}
