/** ApprovalQueueItem — §2.4 of ALIS_FRONTEND_SPEC.md */

interface ApprovalQueueItemProps {
  tag: string
  title: string
  subtitle: string
  meta: string
  status: 'pending' | 'review' | 'active' | 'urgent' | 'done'
  showApproveReject?: boolean
  onApprove?: () => void
  onReject?: () => void
  onView?: () => void
}

const TAG_COLORS: Record<string, { bg: string; text: string }> = {
  pending: { bg: 'var(--color-warning-bg)', text: 'var(--color-warning)' },
  review:  { bg: 'var(--color-info-bg)',    text: 'var(--color-info)' },
  active:  { bg: 'var(--color-success-bg)', text: 'var(--color-success)' },
  urgent:  { bg: 'var(--color-danger-bg)',  text: 'var(--color-danger)' },
  done:    { bg: '#f3f4f6',                 text: 'var(--color-text-muted)' },
}

export function ApprovalQueueItem({ tag, title, subtitle, meta, status, showApproveReject, onApprove, onReject, onView }: ApprovalQueueItemProps) {
  const colors = TAG_COLORS[status] || TAG_COLORS.pending

  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 12,
      padding: '12px 16px',
      borderBottom: '1px solid var(--color-border)',
    }}>
      {/* Tag */}
      <div style={{
        width: 36, height: 36, borderRadius: 'var(--radius-sm)',
        background: colors.bg, color: colors.text,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 'var(--text-xs)', fontWeight: 700, flexShrink: 0,
      }}>
        {tag}
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 'var(--text-base)', fontWeight: 500, color: 'var(--color-text-primary)', lineHeight: 1.3 }}>
          {title}
        </div>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)', marginTop: 2, lineHeight: 1.4 }}>
          {subtitle}
        </div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: 2 }}>
          {meta}
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 6, flexShrink: 0, alignItems: 'center' }}>
        {showApproveReject && onApprove && (
          <button onClick={onApprove} style={{
            padding: '5px 12px', borderRadius: 'var(--radius-sm)', border: 'none', cursor: 'pointer',
            background: 'var(--color-primary)', color: 'var(--color-text-on-primary)',
            fontSize: 'var(--text-xs)', fontWeight: 600,
          }}>
            Approve
          </button>
        )}
        {showApproveReject && onReject && (
          <button onClick={onReject} style={{
            padding: '5px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--color-danger-border)', cursor: 'pointer',
            background: 'var(--color-danger-bg)', color: 'var(--color-danger)',
            fontSize: 'var(--text-xs)', fontWeight: 600,
          }}>
            Reject
          </button>
        )}
        {onView && (
          <button onClick={onView} style={{
            padding: '5px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--color-border)', cursor: 'pointer',
            background: 'transparent', color: 'var(--color-text-secondary)',
            fontSize: 'var(--text-xs)', fontWeight: 500,
          }}>
            View
          </button>
        )}
      </div>
    </div>
  )
}
