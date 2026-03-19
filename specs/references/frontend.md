---
name: alis-frontend
description: Build production-grade UI for ALIS OS — the Autonomous Institutional Operating System by QUAICU. Use this skill whenever building, modifying, or extending any part of the ALIS frontend: the chat-first dual-panel shell, role-adaptive dashboards, approval queues, agent rail, canvas views, module screens (admissions, academics, examinations, finance, HR, student services, regulatory), or any ALIS-specific component. Also use when the user asks about ALIS UI architecture, component design, agent-canvas sync, or mobile responsiveness for the institutional OS. This skill contains the full design system, layout rules, interaction model, and component library — always read it before writing a single line of ALIS frontend code.
---

# ALIS Frontend — Build Reference

ALIS is an Autonomous Institutional Operating System for universities. The frontend is a **chat-first, dual-panel application** where a persistent AI agent co-pilots every user action. The design must feel like a trusted institutional tool — dense, calm, reliable — not a consumer app.

Read this entire file before writing any ALIS frontend code.

---

## 1. Layout — the fundamental shell

The shell is a three-column layout. All three columns are always visible on desktop.

```
┌──────┬─────────────────────────────────────┬──────────────────┐
│  52px│          PRIMARY CANVAS             │   AGENT RAIL     │
│ Icon │          (flex: 1)                  │   (320px fixed)  │
│ nav  │                                     │                  │
│      │  Morphs based on:                   │  Chat thread     │
│      │  · User navigation (manual)         │  Always visible  │
│      │  · Agent command (auto)             │  Always aware    │
│      │  · Module context                   │                  │
└──────┴─────────────────────────────────────┴──────────────────┘
```

```tsx
// Shell structure — never deviate from this
<div className="alis-shell"> {/* grid: 52px 1fr 320px, height: 100vh */}
  <IconNav />          {/* 52px — role-based module icons */}
  <PrimaryCanvas />    {/* flex: 1 — morphs per view */}
  <AgentRail />        {/* 320px fixed — always mounted */}
</div>
```

**Breakpoints:**
- Desktop (≥1280px): full three-column shell as above
- Tablet (768–1279px): sidebar stays icon-only (52px), agent rail shrinks to 280px
- Mobile (<768px): canvas goes full width, sidebar becomes hamburger, agent rail becomes a bottom sheet (collapsed to 48px input bar, expands on tap to 60% viewport height)

**Never** hide the agent rail entirely on any breakpoint. It is the core product differentiator.

---

## 2. Design tokens — use exclusively

```css
/* Spacing */
--space-1: 4px;   --space-2: 8px;   --space-3: 12px;
--space-4: 16px;  --space-5: 20px;  --space-6: 24px;

/* Typography */
--text-xs: 10px;   --text-sm: 11px;  --text-base: 12px;
--text-md: 13px;   --text-lg: 14px;  --text-xl: 16px;

/* Font weight — two only */
--weight-normal: 400;
--weight-medium: 500;

/* Borders — always 0.5px */
--border: 0.5px solid var(--color-border-tertiary);
--border-emphasis: 0.5px solid var(--color-border-secondary);

/* Radius */
--radius-sm: 6px;
--radius-md: 8px;   /* most components */
--radius-lg: 12px;  /* cards, panels */
--radius-pill: 20px; /* badges, chips */

/* Brand */
--alis-teal: #1D9E75;
--alis-teal-light: #E1F5EE;
--alis-teal-mid: #9FE1CB;
--alis-teal-dark: #0F6E56;
```

**Color semantics — apply these consistently, never decoratively:**

| Color | Semantic meaning | Never use for |
|---|---|---|
| Red | Urgent, overdue, ineligible, at-risk | Decoration |
| Amber | Needs review, approaching threshold, condonation | General warning |
| Green | Approved, eligible, on track, cleared | Generic success |
| Blue | Informational, routine, scheduled | Branding |
| Teal `#1D9E75` | Primary action, agent, approve accent, focus rings | Any semantic status |
| Gray | Archived, historical, inactive | Active states |

---

## 3. Role-adaptive density

ALIS serves four primary roles. Each role gets a different default density. This is not a preference setting — it is determined by the authenticated user's role at login.

| Role | Canvas density | Stats grid | Table rows (default) | Agent voice |
|---|---|---|---|---|
| Registrar / Admin | High — data tables, dense queues | 4-up | 8 rows | Briefing-led, action-oriented |
| Faculty / HOD | Medium — student cards + course tiles | 4-up | 5 rows | Risk-aware, empathetic |
| Student | Low — personal timeline, clean cards | 4-up | 6 rows, no bulk actions | Helpful, plain language |
| Finance Officer | High — financial tables, trend charts | 4-up | 8 rows | Precise, compliance-aware |

```tsx
// Role context — always available via useALISRole()
type ALISRole = 'registrar' | 'faculty' | 'student' | 'finance' | 'hod' | 'exam_controller'

const { role, density } = useALISRole()
// density: 'high' | 'medium' | 'low'
```

---

## 4. Shared state — Zustand store shape

The agent rail and primary canvas share a single Zustand store. Never put canvas state in local component state — the agent must be able to drive the canvas from the rail.

```tsx
interface ALISStore {
  // What's currently rendered on the canvas
  canvas: {
    view: CanvasView           // current view key
    module: ALISModule         // current module
    filters: Record<string, unknown>
    highlightedItemId: string | null   // agent points at this
    selectedItemIds: string[]          // multi-select
    scrollToItemId: string | null      // triggers scroll
  }

  // Agent awareness — always knows what's on screen
  agent: {
    contextLabel: string       // "Watching: Approval Queue · 3 urgent"
    pendingAction: CanvasAction | null
    isTyping: boolean
    quickActions: string[]     // chips shown below thread
  }

  // Chat thread
  chat: {
    messages: ChatMessage[]
  }

  // Actions
  setCanvasView: (view: CanvasView, module: ALISModule, filters?: Record<string, unknown>) => void
  highlightItem: (id: string) => void
  highlightMultiple: (ids: string[]) => void
  clearHighlight: () => void
  dispatchAgentAction: (action: CanvasAction) => void
  addMessage: (msg: ChatMessage) => void
  setAgentTyping: (typing: boolean) => void
  setQuickActions: (actions: string[]) => void
}
```

---

## 5. Bidirectional sync — agent ↔ canvas

This is the defining interaction model of ALIS. Every agent response carries two payloads: a message for the chat thread, and a `CanvasAction` that the dashboard executes.

```tsx
// Canvas action types — the complete set
type CanvasAction =
  | { type: 'NAVIGATE'; view: CanvasView; module: ALISModule; filters?: Record<string, unknown> }
  | { type: 'HIGHLIGHT'; itemId: string; scrollTo: boolean }
  | { type: 'HIGHLIGHT_MULTIPLE'; itemIds: string[] }
  | { type: 'FILTER'; filters: Record<string, unknown> }
  | { type: 'OPEN_DETAIL'; itemId: string }
  | { type: 'EXECUTE'; action: 'approve' | 'reject' | 'escalate'; itemId: string }
  | { type: 'CLEAR_HIGHLIGHT' }

// The canvas listens and executes
function useAgentCanvasSync() {
  const { agent, canvas, setCanvasView, highlightItem } = useALISStore()

  useEffect(() => {
    const action = agent.pendingAction
    if (!action) return

    switch (action.type) {
      case 'NAVIGATE':
        setCanvasView(action.view, action.module, action.filters)
        break
      case 'HIGHLIGHT':
        highlightItem(action.itemId)
        if (action.scrollTo) scrollToItem(action.itemId)
        break
      case 'HIGHLIGHT_MULTIPLE':
        action.itemIds.forEach(id => highlightItem(id))
        break
      case 'EXECUTE':
        executeItemAction(action.action, action.itemId)
        break
    }
  }, [agent.pendingAction])
}
```

The canvas also sends context back to the agent on every view change:

```tsx
// In PrimaryCanvas, on every view change:
useEffect(() => {
  setAgentContext(getContextLabel(canvas.view, canvas.module))
  setQuickActions(getQuickActions(canvas.view, role))
}, [canvas.view])
```

---

## 6. Agent rail — component spec

The agent must never feel like a chatbot. It is a briefing officer. Apply these rules precisely.

```tsx
function AgentRail() {
  return (
    <aside className="agent-rail"> {/* 320px, border-left, flex column */}
      <AgentHeader />      {/* live dot + label + context line */}
      <ChatThread />       {/* scrollable, flex: 1 */}
      <QuickActions />     {/* context-aware chips, max 4 */}
      <ChatInputRow />     {/* input + send */}
    </aside>
  )
}
```

### AgentHeader

```tsx
function AgentHeader() {
  const { agent } = useALISStore()
  return (
    <div className="agent-header"> {/* 44px height, border-bottom, flex, gap-8 */}
      <span className="agent-dot" /> {/* 7px circle, bg: --alis-teal, no pulse animation */}
      <span style={{ fontSize: 12, fontWeight: 500 }}>ALIS Agent</span>
      <span className="agent-ctx"> {/* 10px, secondary color, margin-left: auto, text-align: right */}
        {agent.contextLabel}
      </span>
    </div>
  )
}
```

**No avatar. No bot icon. No robot emoji.** The green dot is the only identity marker.

### Message types — three variants only

```tsx
// 1. Agent message — left-aligned
<div className="msg-agent">
  {/* bg: background-secondary, radius: 0 md md md, padding: 8px 10px, font-size: 12px */}
  {message.text}
</div>

// 2. User message — right-aligned
<div className="msg-user">
  {/* bg: #E1F5EE, color: #085041, radius: md 0 md md */}
  {message.text}
</div>

// 3. Action card — full width, bordered
<div className="msg-action">
  {/* border: 0.5px, radius: md, padding: 7px 10px */}
  <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 4 }}>
    {message.prompt}
  </p>
  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
    {message.chips.map(chip => (
      <button key={chip} className="action-chip" onClick={() => handleChipClick(chip)}>
        {chip}
      </button>
    ))}
  </div>
</div>
```

Never use bubble tails. No rounded-on-one-side corners. Clean flat rectangles only.

### Typing indicator

```tsx
function TypingIndicator() {
  return (
    <div className="msg-agent" style={{ padding: '8px 12px' }}>
      <div style={{ display: 'flex', gap: 3 }}>
        {[0, 0.2, 0.4].map((delay, i) => (
          <span key={i} style={{
            width: 5, height: 5, borderRadius: '50%',
            background: 'var(--color-text-secondary)',
            animation: `blink 1.2s ${delay}s infinite`
          }} />
        ))}
      </div>
    </div>
  )
}
// @keyframes blink: 0%,80%,100% opacity 0.2 | 40% opacity 1
```

### Quick-action chips — context-aware rotation

Change chips every time the canvas view changes. Maximum 4. These are the product's teaching mechanism — they show users what the agent can do.

```tsx
const QUICK_ACTIONS: Record<CanvasView, Record<ALISRole, string[]>> = {
  approval_queue: {
    registrar: ['Show urgent items', 'Brief me on exceptions', 'Auto-approve routine', 'Export queue'],
    finance: ['Show overdue items', 'Escalate pending', 'Export queue', 'Run reconciliation'],
  },
  student_risk: {
    faculty: ['Show red-risk students', 'Draft parent alerts', 'Schedule mentorship', 'Export report'],
    registrar: ['Show detention risk', 'Academic probation list', 'Contact mentors', 'Export report'],
  },
  exam_management: {
    registrar: ['Eligibility status', 'Hall ticket dispatch', 'Flag conflicts', 'Seating chart'],
    exam_controller: ['Check paper vault', 'Invigilation duty chart', 'Flag malpractice', 'Results status'],
  },
  fee_dashboard: {
    finance: ['Show defaulters', 'Send batch reminders', 'Reconciliation report', 'Pending refunds'],
    registrar: ['Students with holds', 'Clear for hall ticket', 'Waiver requests', 'Export dues'],
  },
  my_courses: {
    faculty: ['Show at-risk students', 'Draft parent alerts', 'View IA submissions', 'Check attendance'],
    hod: ['Department attendance', 'Faculty workload', 'Pending IA papers', 'Course coverage'],
  },
  my_academics: {
    student: ['Download hall ticket', 'Check my schedule', 'View my grades', 'Request transcript'],
  },
}
```

---

## 7. Primary canvas — view system

The canvas renders different views depending on navigation state. Every view has: a header (breadcrumb + controls), a stats row (4 cards), and a content area.

### Canvas header

```tsx
function CanvasHeader() {
  const { canvas } = useALISStore()
  const role = useALISRole()
  return (
    <header className="canvas-header"> {/* 52px, border-bottom, flex, gap-12 */}
      <div>
        <h1 style={{ fontSize: 13, fontWeight: 500 }}>{getViewTitle(canvas.view, role)}</h1>
        <p style={{ fontSize: 10, color: 'var(--color-text-secondary)' }}>
          {getViewSubtitle(canvas.view, role)}
        </p>
      </div>
      <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
        <ViewControls />   {/* filter, sort, export — context-sensitive */}
      </div>
    </header>
  )
}
```

### Stats row — 4-up grid, always

```tsx
function StatsRow({ stats }: { stats: StatCard[] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8 }}>
      {stats.map(stat => <StatCard key={stat.label} {...stat} />)}
    </div>
  )
}

function StatCard({ label, value, delta, deltaColor }: StatCard) {
  return (
    <div style={{
      background: 'var(--color-background-secondary)',
      borderRadius: 'var(--radius-md)',
      padding: '10px 12px'
    }}>
      <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 4 }}>{label}</p>
      <p style={{ fontSize: 20, fontWeight: 500 }}>{value}</p>
      <p style={{ fontSize: 11, color: deltaColor, marginTop: 2 }}>{delta}</p>
    </div>
  )
}
```

**Mobile (< 768px):** stats grid becomes `repeat(2, minmax(0, 1fr))` — 2×2.

---

## 8. Approval queue — the most important component

The approval queue is the Registrar's primary work surface. It is used more than any other component. Build it perfectly.

```tsx
interface ApprovalItem {
  id: string
  title: string
  subtitle: string
  priority: 'urgent' | 'review' | 'routine'
  slaPercent: number      // 0–100, represents TIME REMAINING (not elapsed)
  module: ALISModule
  canAutoApprove: boolean
}

function ApprovalQueue({ items }: { items: ApprovalItem[] }) {
  const { canvas } = useALISStore()
  return (
    <div style={{ border: 'var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
      {items.map((item, i) => (
        <ApprovalRow
          key={item.id}
          item={item}
          isHighlighted={canvas.highlightedItemId === item.id}
          isLast={i === items.length - 1}
        />
      ))}
    </div>
  )
}

function ApprovalRow({ item, isHighlighted, isLast }: ApprovalRowProps) {
  return (
    <div
      id={`qi-${item.id}`}
      onClick={() => selectItem(item.id)}
      style={{
        display: 'grid',
        gridTemplateColumns: '3fr 1.2fr 1fr auto',
        alignItems: 'center',
        gap: 8,
        padding: '9px 12px',
        background: isHighlighted ? 'var(--color-background-secondary)' : 'var(--color-background-primary)',
        borderLeft: isHighlighted ? '2.5px solid var(--alis-teal)' : '2.5px solid transparent',
        borderBottom: isLast ? 'none' : 'var(--border)',
        cursor: 'pointer',
        transition: 'background 0.12s',
      }}
    >
      <div>
        <p style={{ fontSize: 13, fontWeight: 500 }}>{item.title}</p>
        <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 1 }}>{item.subtitle}</p>
      </div>
      <PriorityBadge priority={item.priority} />
      <SLABar percent={item.slaPercent} />
      <ApprovalActions itemId={item.id} canAutoApprove={item.canAutoApprove} />
    </div>
  )
}
```

### SLA bar — color rules are strict

```tsx
function SLABar({ percent }: { percent: number }) {
  // percent = time REMAINING, not time elapsed
  const color = percent < 30 ? '#E24B4A' : percent < 60 ? '#EF9F27' : '#1D9E75'
  return (
    <div>
      <div style={{ width: 50, height: 4, borderRadius: 2, background: 'var(--color-border-tertiary)', overflow: 'hidden' }}>
        <div style={{ width: `${percent}%`, height: '100%', borderRadius: 2, background: color, transition: 'width 0.3s' }} />
      </div>
      <p style={{ fontSize: 10, color: 'var(--color-text-secondary)', marginTop: 2 }}>SLA {percent}%</p>
    </div>
  )
}
// If percent === 0: add pulsing red border to the entire row
```

### Mobile swipe on approval rows

On mobile, approval rows support swipe gestures:
- Swipe right → approve (green flash, then remove row)
- Swipe left → reject (red flash, then remove row)

Use `@use-gesture/react` for swipe detection. Threshold: 80px movement in < 300ms.

---

## 9. Badge component — complete spec

```tsx
type BadgeVariant = 'red' | 'amber' | 'green' | 'blue' | 'gray'

const BADGE_STYLES: Record<BadgeVariant, { bg: string; color: string }> = {
  red:   { bg: '#FCEBEB', color: '#A32D2D' },
  amber: { bg: '#FAEEDA', color: '#854F0B' },
  green: { bg: '#EAF3DE', color: '#3B6D11' },
  blue:  { bg: '#E6F1FB', color: '#185FA5' },
  gray:  { bg: 'var(--color-background-secondary)', color: 'var(--color-text-secondary)' },
}

// Priority → badge variant mapping
const PRIORITY_BADGE: Record<ApprovalItem['priority'], BadgeVariant> = {
  urgent: 'red',
  review: 'amber',
  routine: 'blue',
}

function Badge({ variant, children }: { variant: BadgeVariant; children: React.ReactNode }) {
  const s = BADGE_STYLES[variant]
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 7px',
      borderRadius: 'var(--radius-pill)',
      fontSize: 10,
      fontWeight: 500,
      background: s.bg,
      color: s.color,
    }}>
      {children}
    </span>
  )
}
```

---

## 10. Data tables — density rules

ALIS tables are high-density. Never use cards in place of tables for tabular data (approval queues, fee lists, student lists, grade tables).

```tsx
// Standard table pattern
<div style={{ border: 'var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
  {/* Header row */}
  <div style={{ display: 'grid', gridTemplateColumns, background: 'var(--color-background-secondary)', padding: '6px 12px', borderBottom: 'var(--border)' }}>
    {columns.map(col => (
      <span key={col.key} style={{ fontSize: 10, fontWeight: 500, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {col.label}
      </span>
    ))}
  </div>
  {/* Data rows */}
  {rows.map((row, i) => (
    <div key={row.id} style={{
      display: 'grid',
      gridTemplateColumns,
      padding: '8px 12px',
      borderBottom: i < rows.length - 1 ? 'var(--border)' : 'none',
      background: 'var(--color-background-primary)',
      alignItems: 'center',
    }}>
      {/* row cells */}
    </div>
  ))}
</div>
```

**Mobile table → card list:** On mobile (< 768px), tables convert to card stacks. Each row becomes a card showing the 2 most important columns. Tap to expand full detail. Never force a horizontal-scrolling data table on mobile.

---

## 11. Module-specific canvas views

### Registrar view
- 4-up stats: pending approvals, enrolled students, exams this week, docs issued today
- Primary content: Approval queue (sorted: urgent first)
- Secondary content: Activity chart (this week's enrollments vs approvals)

### Faculty / HOD view
- 4-up stats: students mentored, avg attendance, pending marking, lectures this week
- Primary content: At-risk student list (attendance %, IA score, risk bar)
- Secondary content: Course tiles grid (2×2), each showing syllabus coverage progress bar

### Student view
- 4-up stats: attendance %, CGPA, pending dues, days to exam
- Primary content: Exam schedule table (course, date, session, eligibility status)
- No bulk actions — students operate only on their own data

### Finance Officer view
- 4-up stats: collected (month), defaulters count, pending refunds, reconciliation status
- Primary content: Defaulter table (name, amount due, days overdue, last reminder, action button)
- Secondary content: Daily collection bar chart (14-day rolling)

### Exam Controller view
- 4-up stats: eligible students, hall tickets dispatched, papers in vault, exam days remaining
- Primary content: Exam schedule with conflict flags
- Secondary content: Room allocation summary

---

## 12. Risk score visualization

Risk scores appear in student lists across Faculty, HOD, and Registrar views.

```tsx
function RiskBar({ score }: { score: number }) {
  // score: 0–100, higher = more at risk
  const color = score > 70 ? '#E24B4A' : score > 40 ? '#EF9F27' : '#1D9E75'
  const label = score > 70 ? 'High' : score > 40 ? 'Medium' : 'Low'
  return (
    <div>
      <div style={{ width: `${score}%`, height: 5, borderRadius: 3, background: color }} />
      <p style={{ fontSize: 10, color: 'var(--color-text-secondary)', marginTop: 1 }}>{label}</p>
    </div>
  )
}
```

Risk score inputs (from Academics module): attendance drop, IA scores, consecutive absences, LMS login frequency, assignment completion.

---

## 13. Navigation sidebar — icon nav

```tsx
const MODULE_ICONS: Record<ALISModule, string> = {
  dashboard: '⌂',
  tasks: '✓',
  students: '◎',
  admissions: '→',
  academics: '▤',
  examinations: '≡',
  finance: '₹',
  hr: '☰',
  student_services: '◈',
  regulatory: '✦',
  reports: '↗',
  settings: '⚙',
}
```

Only show modules the current role has permission to access. Students see: dashboard, academics, examinations, student_services. Never show admin modules to students.

The ALIS wordmark at the top of the sidebar is a 28×28 teal square with white "A" — not a logotype. Keep it simple.

---

## 14. Interaction rules — the non-negotiables

**Agent highlights take priority over user selections.** When the agent highlights an item, it overrides any current selection. The user can click elsewhere to clear.

**Every state change driven by the agent must also be reachable by manual navigation.** The agent is a shortcut, not a replacement. If the agent navigates to "pending exam items", the user must be able to get there by clicking through the sidebar too.

**Approval actions are always reversible within 30 seconds.** Show an undo toast after every approve/reject. The toast auto-dismisses at 30s. This is not optional — mistakes happen.

```tsx
function showUndoToast(action: string, onUndo: () => void) {
  // Toast at bottom of canvas, not full-screen
  // "Hall tickets approved · Undo" with a 30s countdown bar
  // Disappears on undo click or after 30s
}
```

**Never show a loading spinner on the canvas when the agent is processing.** The typing indicator in the agent rail is enough. The canvas should show a skeleton loader only when fetching new data for a view change.

**The agent context label must update within 100ms of every canvas view change.** This is visible to the user and delays break the illusion of the agent watching in real time.

---

## 15. Responsive canvas — what changes on mobile

| Element | Desktop | Mobile |
|---|---|---|
| Shell layout | 52px + flex + 320px | Full width canvas, bottom sheet agent |
| Stats row | 4-up grid | 2×2 grid |
| Approval queue | Grid with 4 columns | Cards with swipe actions |
| Data tables | Dense, horizontal | Card list, 2 key fields visible |
| Agent rail | 320px right panel | Bottom sheet, 60% height when open |
| Quick actions | Chips in agent rail | Horizontal scroll row above input |
| Canvas header | Full with breadcrumb | Title only, controls in overflow menu |

The bottom sheet agent on mobile must have a drag handle and support drag-to-dismiss.

---

## 16. Tech stack — use these, not alternatives

```
React 19 + TypeScript 5.7
Zustand 5          — global state (canvas + agent + chat)
TanStack Query 5   — server state, data fetching, cache
Tailwind CSS 4     — utility classes (but prefer inline styles for dynamic values)
Radix UI           — Dialog, Dropdown, Select, Tabs, Toast primitives
Framer Motion      — only for: bottom sheet animation, undo toast, row removal
Lucide React       — icons (use sparingly — prefer text symbols for nav)
Vite 6             — bundler
```

**Do not use:**
- `useState` for canvas navigation state — use Zustand
- Custom chart libraries — if charts are needed, use Recharts (already in deps)
- `position: fixed` for toasts — use Radix Toast (portal-based)
- CSS animations for data updates — transitions only, no keyframe animations on data

---

## 17. File structure — where things live

```
web/src/
├── shell/
│   ├── ALISShell.tsx          # three-column layout root
│   ├── IconNav.tsx            # 52px sidebar
│   ├── PrimaryCanvas.tsx      # canvas host, view router
│   └── AgentRail/
│       ├── AgentRail.tsx      # rail container
│       ├── AgentHeader.tsx    # dot + label + context
│       ├── ChatThread.tsx     # message list
│       ├── QuickActions.tsx   # context chips
│       └── ChatInput.tsx      # input + send
├── views/                     # canvas view components (one per module)
│   ├── RegistrarDashboard.tsx
│   ├── FacultyDashboard.tsx
│   ├── StudentDashboard.tsx
│   ├── FinanceDashboard.tsx
│   ├── ApprovalQueue.tsx      # shared across registrar + finance
│   ├── ExamManagement.tsx
│   ├── AdmissionsView.tsx
│   └── ...
├── components/                # shared UI primitives
│   ├── Badge.tsx
│   ├── StatCard.tsx
│   ├── SLABar.tsx
│   ├── RiskBar.tsx
│   ├── DataTable.tsx          # the base table component
│   ├── ApprovalRow.tsx
│   └── UndoToast.tsx
├── store/
│   └── alis.store.ts          # Zustand store (canvas + agent + chat)
├── hooks/
│   ├── useALISRole.ts         # current user role + density
│   ├── useAgentCanvasSync.ts  # wires agent actions to canvas
│   └── useQuickActions.ts     # returns context-aware chips
└── lib/
    ├── canvas-actions.ts      # CanvasAction type + handler map
    ├── quick-actions.ts       # QUICK_ACTIONS lookup table
    └── role-config.ts         # density + permissions per role
```

---

## 18. What the agent API must return

Every chat completion from the ALIS agent must return a structured response. The frontend parses both fields.

```typescript
interface AgentResponse {
  message: string              // natural language, goes into chat thread
  canvasAction: CanvasAction | null  // dashboard instruction, executed immediately
  quickActions?: string[]      // optionally override the chip set
  agentContext?: string        // optionally update the context label
}

// Example: user says "show me pending exam items"
const response: AgentResponse = {
  message: "Found 3 exam-related items in the queue. I've highlighted them. The hall ticket batch (847 students) is most urgent — 3h 32m to dispatch deadline.",
  canvasAction: {
    type: 'HIGHLIGHT_MULTIPLE',
    itemIds: ['exam-hallticket-batch', 'condonation-ravi', 'grade-moderation-cs601']
  },
  agentContext: "Watching: Exam queue · 3 items highlighted",
  quickActions: ['Approve hall tickets', 'Brief me on item 2', "What's the SLA status?"]
}
```

Parse this on the frontend immediately on receipt. Execute `canvasAction` before rendering the message in the thread — so the dashboard moves first, then the text appears. This makes the agent feel faster.

---

## 19. Build sequence — what to build first

Build in this order. Each step produces a working demo.

1. **Shell + Registrar approval queue** — sidebar, canvas, agent rail, approval queue with highlight-on-command. This is the demo that sells ALIS.
2. **Bidirectional sync** — Zustand store + `useAgentCanvasSync`. Get agent ↔ canvas communication working end-to-end with mock agent responses.
3. **Faculty view** — at-risk student list, course tiles, quick actions.
4. **Mobile responsive** — bottom sheet agent, swipeable approval rows, 2×2 stats, card tables.
5. **Student view** — exam schedule, personal stats. Simplest view.
6. **Finance view** — defaulter table, fee collection chart, reconciliation status.
7. **Remaining module views** — admissions pipeline, exam management, regulatory dashboard.

Do not build all roles simultaneously. The Registrar approval queue + agent sync is the critical path.

---

## 20. Do nots — enforced for every ALIS component

```
NEVER use position: fixed — use Radix portals or in-flow layout
NEVER show loading spinners when agent is processing — typing indicator only
NEVER use animations on data rows — transitions (0.12s) only
NEVER use gradients, drop shadows, or glow effects
NEVER use more than two font weights (400 and 500)
NEVER use ALL CAPS for labels — use sentence case
NEVER put agent context in local component state — always Zustand
NEVER hide the agent rail on any breakpoint — only collapse it
NEVER use color decoratively — only for semantic status
NEVER show more than 4 quick-action chips at once
NEVER omit the undo toast on approval actions
NEVER build mobile as an afterthought — design both from the start
NEVER use integer pixel values that aren't in the token scale
```
