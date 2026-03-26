/**
 * ChatThread — scrollable message list with sourceView dividers
 * Reference: ALIS-skills/references/frontend.md §6
 *
 * Three message variants:
 *   agent   — left-aligned, background-secondary
 *   user    — right-aligned, teal-light background
 *   action  — full-width bordered card with chip buttons
 *
 * sourceView dividers appear between consecutive messages from different
 * canvas views so the user can see which context each thread segment belongs to.
 *
 * EXECUTE chip pattern:
 *   Chips on action-card messages pass the source message's canvasAction to
 *   onChipAction. The rail dispatches EXECUTE only on explicit "Confirm" tap.
 */

import { useEffect, useRef } from 'react'
import { useALISStore, type ChatMessage } from '../../store/alis.store'
import type { CanvasAction, CanvasView } from '../../lib/canvas-actions'
import type { TaskGroup, TaskItem } from '../../lib/agent-gateway'

const VIEW_LABELS: Record<string, string> = {
  approval_queue:             'Approval Queue',
  student_risk:               'Student Risk',
  exam_management:            'Exam Management',
  fee_dashboard:              'Fee Dashboard',
  my_courses:                 'My Courses',
  my_academics:               'My Academics',
  admissions_pipeline:        'Admissions Pipeline',
  regulatory_dashboard:       'Regulatory',
  hr_dashboard:               'HR',
  reports_dashboard:          'Reports',
  student_services_dashboard: 'Student Services',
  communications_dashboard:   'Communications',
  alumni_dashboard:           'Alumni',
  phd_dashboard:              'PhD',
  workflows_dashboard:        'Workflows',
  consent_dashboard:          'Consent',
  home:                       'Home',
}

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

function ViewDivider({ view }: { view: string }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        margin: '8px 0',
        opacity: 0.45,
      }}
    >
      <div style={{ flex: 1, height: 1, background: 'var(--color-border, #e2e8f0)' }} />
      <span
        style={{
          fontSize: 9,
          letterSpacing: 0.8,
          textTransform: 'uppercase',
          whiteSpace: 'nowrap',
          color: 'var(--color-text-secondary)',
        }}
      >
        {VIEW_LABELS[view] ?? view.replace(/_/g, ' ')}
      </span>
      <div style={{ flex: 1, height: 1, background: 'var(--color-border, #e2e8f0)' }} />
    </div>
  )
}

// ─── Task Cockpit (Phase C) ───────────────────────────────────────────────────

const URGENCY_COLOR: Record<string, string> = {
  'SLA BREACH': '#E24B4A',
  'URGENT':     '#EF9F27',
  'APPROVALS':  '#3B82F6',
  'NORMAL':     '#6B7280',
}

const URGENCY_BG: Record<string, string> = {
  'SLA BREACH': 'rgba(226,75,74,0.08)',
  'URGENT':     'rgba(239,159,39,0.08)',
  'APPROVALS':  'rgba(59,130,246,0.08)',
  'NORMAL':     'rgba(107,114,128,0.06)',
}

function slaLabel(isoOrNull: string | null): string | null {
  if (!isoOrNull) return null
  const diff = new Date(isoOrNull).getTime() - Date.now()
  if (diff < 0) return 'Past SLA'
  const h = Math.floor(diff / 3_600_000)
  if (h < 1) return `${Math.floor(diff / 60_000)}m left`
  if (h < 24) return `${h}h left`
  return `${Math.floor(h / 24)}d left`
}

interface TaskCockpitProps {
  groups: TaskGroup[]
  onNavigate: (view: CanvasView) => void
}

function TaskCockpit({ groups, onNavigate }: TaskCockpitProps) {
  if (groups.length === 0) {
    return (
      <p style={{ fontSize: 12, color: 'var(--color-text-secondary)', margin: 0 }}>
        Queue is clear.
      </p>
    )
  }
  return (
    <div style={{ width: '100%' }}>
      {groups.map((group) => (
        <div key={group.label} style={{ marginBottom: 10 }}>
          {/* Group header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <span
              style={{
                fontSize: 9,
                fontWeight: 700,
                letterSpacing: 0.8,
                textTransform: 'uppercase',
                color: URGENCY_COLOR[group.label] ?? '#6B7280',
                background: URGENCY_BG[group.label] ?? 'transparent',
                padding: '1px 5px',
                borderRadius: 3,
              }}
            >
              {group.label}
            </span>
            <span style={{ fontSize: 10, color: 'var(--color-text-secondary)' }}>
              {group.count}
            </span>
          </div>

          {/* Task items */}
          {group.tasks.map((task: TaskItem) => {
            const sla = slaLabel(task.sla_deadline)
            const isPastSla = task.sla_deadline && new Date(task.sla_deadline) < new Date()
            return (
              <button
                key={task.id}
                onClick={() => onNavigate(task.canvas_view as CanvasView)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  width: '100%',
                  padding: '5px 8px',
                  marginBottom: 3,
                  borderRadius: 5,
                  border: '0.5px solid var(--color-border-secondary)',
                  background: 'var(--color-surface-primary)',
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
              >
                <span style={{ fontSize: 11, color: 'var(--color-text-primary)', lineHeight: 1.4 }}>
                  {task.label}
                </span>
                {sla && (
                  <span
                    style={{
                      fontSize: 10,
                      color: isPastSla ? '#E24B4A' : 'var(--color-text-secondary)',
                      whiteSpace: 'nowrap',
                      marginLeft: 8,
                      flexShrink: 0,
                    }}
                  >
                    {sla}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────

interface MessageProps {
  msg: ChatMessage
  onChipClick: (chip: string, canvasAction?: CanvasAction | null) => void
}

function Message({ msg, onChipClick }: MessageProps) {
  const { setCanvasView } = useALISStore()

  // Task cockpit — structured task groups present
  if (msg.tasks && msg.tasks.length >= 0) {
    return (
      <div
        style={{
          border: 'var(--border)',
          borderRadius: 'var(--radius-md)',
          padding: '8px 10px',
          marginBottom: 6,
          width: '100%',
        }}
      >
        {msg.text && (
          <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 8 }}>
            {msg.text}
          </p>
        )}
        <TaskCockpit
          groups={msg.tasks}
          onNavigate={(view) => setCanvasView(view, 'admissions')}
        />
      </div>
    )
  }

  // Action card — chips present
  if (msg.chips && msg.chips.length > 0) {
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
              onClick={() => onChipClick(chip, msg.canvasAction)}
              style={{
                padding: '3px 8px',
                borderRadius: 'var(--radius-pill)',
                fontSize: 11,
                background: chip === 'Skip'
                  ? 'rgba(0,0,0,0.04)'
                  : 'rgba(29,158,117,0.08)',
                color: chip === 'Skip'
                  ? 'var(--color-text-secondary)'
                  : '#1D9E75',
                border: chip === 'Skip'
                  ? '0.5px solid rgba(0,0,0,0.1)'
                  : '0.5px solid rgba(29,158,117,0.2)',
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

interface ChatThreadProps {
  onChipAction: (chip: string, canvasAction?: CanvasAction | null) => void
}

export function ChatThread({ onChipAction }: ChatThreadProps) {
  const { chat, agent } = useALISStore()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chat.messages, agent.isTyping])

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
      {chat.messages.map((msg, idx) => {
        const prevMsg = idx > 0 ? chat.messages[idx - 1] : null
        const showDivider =
          prevMsg !== null &&
          prevMsg.sourceView !== null &&
          msg.sourceView !== null &&
          prevMsg.sourceView !== msg.sourceView

        return (
          <div key={msg.id}>
            {showDivider && <ViewDivider view={msg.sourceView!} />}
            <Message msg={msg} onChipClick={onChipAction} />
          </div>
        )
      })}
      {agent.isTyping && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  )
}
