# ALIS — Frontend UX Specification
**Version**: Production-Ready v2.0 · **For**: External UI/UX Build Team
**Classification**: Share freely — contains no source code, credentials, or architecture internals.

---

## Core Navigation Philosophy

ALIS is **work-first, not module-first**.

Traditional ERPs make users navigate to a module and hunt for their tasks. ALIS flips this: the system finds the user's work and surfaces it automatically. Modules are tools accessed on demand — not the primary navigation structure.

```
SYSTEM  →  creates work  →  Work Panel (Incoming)
USER    →  creates work  →  Work Panel (Initiated)
USER    →  accesses tools →  My Wizards
AI      →  guides + prioritises everything
```

---

## Part 0 — App Architecture & Design System

### 0.1 Access Surfaces

| Surface | URL prefix | Primary users |
|---|---|---|
| **Staff ERP** | `/app/…` | All institution staff (role-gated) |
| **Student Portal** | `/portal/…` | Applicants + enrolled students |
| **Admin Console** | `/admin/…` | SUPER_ADMIN only |

All three surfaces share the same auth system. After login the user is routed to the correct surface based on their role.

### 0.2 Design System Anchors

**Colour tokens**:
- `--color-primary`: Blue `#2563eb`
- `--color-success`: Emerald `#16a34a`
- `--color-warning`: Amber `#f59e0b`
- `--color-danger`: Red `#dc2626`
- `--color-neutral-*`: Slate scale (50–950)
- `--color-surface`: White (light), `#0f172a` (admin dark shell)
- `--color-border`: Slate-200 (light), Slate-800 (dark)

**Typography scale**:
- Display: 24–32px, weight 700, tracking -0.02em
- Heading: 16–20px, weight 700
- Body: 13–14px, weight 400–500
- Label/caption: 11–12px, weight 600, uppercase, tracking +0.04em
- Code/ID: monospace, 12px

**Density modes**:
- **Compact** — data tables: 11–12px text, 32–36px row height
- **Comfortable** — forms and reading views: 13–14px text, generous padding

**Corner radius**: 8–12px on cards; 6–8px on inputs and buttons.

### 0.3 Shared Component Inventory

| Component | Description |
|---|---|
| **StatCard** | Large metric + label + trend arrow + period subtitle |
| **DataTable** | Sortable, selectable, paginated, inline actions, Export CSV |
| **Badge** | Colour-coded status pill |
| **TimelinePanel** | Vertical event log: icon + actor + timestamp + description |
| **SLABar** | Deadline urgency bar: green → amber → red |
| **RiskBar** | Risk level fill bar (Low/Medium/High/Critical) |
| **ApprovalRow** | Approval request with inline Approve/Reject + comment |
| **UndoToast** | "Done · Undo" with 5-second window |
| **PermissionPicker** | Permission tree with module groupings and checkboxes |
| **CampusSwitcher** | Header dropdown; globally filters all data for session |
| **ConfirmDialog** | Destructive action modal with typed confirmation for high-risk actions |
| **FileUploader** | Drag-and-drop + browse; progress bar; remove button |
| **RichTextEditor** | Bold, italic, link, lists, headings |
| **DateRangePicker** | Two calendars + preset shortcuts |
| **WorkItem** | Single item in the Work Panel — icon + title + meta + actions |
| **WizardCard** | My Wizards grid card — icon + name + description + pin toggle |
| **FrameTab** | Tab in the canvas tab bar — title + active indicator + close × |
| **Drawer** | Slide-in panel from the right (max 2 levels deep) |

---

## Part 1 — Authentication

### Screen 1.1: Login
**Route**: `/login` · **Who**: Everyone (unauthenticated)

**Layout**: Full-page split — left half is institution branding (logo, tagline, illustration); right half is the login card (max-width 400px, vertically centred).

**Inputs**:
| Field | Type | Rules |
|---|---|---|
| Email address | text | Required, email format |
| Password | password | Required; show/hide toggle |
| Remember me | checkbox | Extends session to 30 days |

**Actions**:
- **Sign In** → authenticates, redirects to Work Panel
- **Forgot password?** → Screen 1.2

**Error states**:
- "Invalid email or password."
- "Account locked — try again after X minutes." (after 5 failed attempts)
- "Account inactive — contact your administrator."

**API**: `POST /api/v1/auth/login`

---

### Screen 1.2: Forgot Password
**Route**: `/forgot-password`

**Inputs**: Email address (required)
**Actions**: **Send reset link** → success state ("Check your inbox"); no resend for 60s (countdown shown). **Back to login** link.
**API**: `POST /api/v1/auth/forgot-password`

---

### Screen 1.3: Reset Password
**Route**: `/reset-password?token=…`

**Inputs**: New password + Confirm new password (both with show/hide). Password strength meter (4-segment bar). Checklist: ≥12 chars, uppercase, number, special character.
**Actions**: **Set new password**
**Error states**: "Link expired.", "Passwords do not match."
**API**: `POST /api/v1/auth/reset-password`

---

### Screen 1.4: MFA Enroll (TOTP)
**Route**: `/mfa/enroll` · **Who**: Staff roles that require MFA (Registrar, Finance Manager, HR Manager, Super Admin)

Shown automatically after first login if MFA is not set up. 3-step progress indicator.

**Step 1 — Scan QR**: QR code image (large) + manual code string for those who cannot scan.
**Step 2 — Verify**: 6-digit OTP input (auto-submits on 6th digit).
**Step 3 — Backup codes**: 8 single-use codes in a 2×4 grid; Download .txt button; "I have saved these codes" checkbox required before Done.

**API**: `POST /api/v1/auth/mfa/enroll`, `POST /api/v1/auth/mfa/verify-enroll`

---

### Screen 1.5: MFA Verify
Shown as a modal overlay after password login for MFA-required roles. 6-digit OTP input + "Use a backup code instead" link.
**API**: `POST /api/v1/auth/mfa/verify`

---

### Screen 1.6: Session Expired
Full-page overlay: "Your session has expired. Please log in again." + Log In button. Preserves current URL for post-login redirect.

---

### Screen 1.7: Account Locked
Error state on login: lock icon + countdown timer. If locked by admin: "Contact [admin email]."

---

## Part 2 — Global Shell (Staff ERP)

### 2.1 Three-Zone Layout

Every `/app/` page uses this fixed layout. No full-page navigations after initial load.

```
┌──────────────────────┬────────────────────────────────────┬──────────────┐
│   Work Panel         │         Canvas                     │  AI Copilot  │
│   280px · fixed      │         fluid · frame-based        │  320px       │
│                      │                                    │  collapsible │
└──────────────────────┴────────────────────────────────────┴──────────────┘
```

**Header bar** spans the full width above all three zones:
- Left: Institution logo + name
- Centre: CampusSwitcher (multi-campus only)
- Right: Notification bell (unread badge) · User avatar (dropdown: Profile, Change Password, MFA Settings, Language switcher, Sign Out)

---

### 2.2 Work Panel (Left, 280px)

The Work Panel is the **default landing view** after login. It never navigates away — it always stays visible on the left.

#### Structure

```
┌─────────────────────────────────┐
│  INCOMING                       │  ← system → user
│  ├── Needs Action    [count]    │
│  ├── Snoozed         [count]    │
│  └── Completed                  │
│       ├── Approved              │
│       └── Rejected              │
│                                 │
│  INITIATED                      │  ← user → system
│  ├── In Progress     [count]    │
│  ├── Waiting         [count]    │
│  └── Completed                  │
│                                 │
│  ─────────────────────────────  │
│                                 │
│  [ ⚡ My Wizards ]              │  ← nav bar toggle
└─────────────────────────────────┘
```

#### INCOMING section

Populated automatically by system events. Items the user did not create but must act on.

**Needs Action** — items requiring the user's direct action:
- Approval requests (leave, fee waiver, re-evaluation)
- Document review assignments
- Flagged anomalies (AI-detected score outlier, attendance gap)
- Deadline alerts (merit list expiry, offer letter expiry, SLA breach)
- System-generated tasks (attendance marking reminder, payroll run due)

**Snoozed** — items the user has deferred. Each shows the snooze-until timestamp ("Remind me at 3 PM"). Snoozed items reappear in Needs Action when the timer fires.

**Completed** — actions the user has finished, subdivided:
- **Approved** — items the user approved (leave, waiver, document)
- **Rejected** — items the user rejected (with rejection reason as tooltip)
- Completed items are retained for 30 days then archived

#### INITIATED section

Work the user started themselves.

**In Progress** — wizards or workflows the user opened and hasn't finished (e.g. a timetable they're editing, a bulk message they're composing, an invoice batch that's generating)

**Waiting** — work the user submitted that now waits on someone else (e.g. "Submitted leave request — awaiting HOD approval")

**Completed** — user-initiated work that has reached a terminal state

#### Work Item anatomy

Each item in the panel is a WorkItem component:

```
┌─────────────────────────────────────┐
│ [icon]  Title of item               │
│         Subtitle / context          │
│         [SLABar if deadline exists] │
│         Time ago · From: [source]   │
│                          [⋮ menu]  │
└─────────────────────────────────────┘
```

The `⋮` context menu per item:
- Open (same as clicking the item)
- Snooze → sub-menu: 1 hour / 3 hours / Tomorrow 9AM / Custom
- Mark as done (without opening)
- Dismiss (removes from list — available only for informational items, not approvals)

**Clicking any Work Panel item** opens it in the canvas (in-place, no new tab).

#### AI Prioritisation

The AI Copilot silently reorders Needs Action items based on urgency, deadline proximity, and role context. A small "AI sorted" label appears at the top of the list. Users can toggle this off ("Sort by time received" option in the panel header).

---

### 2.3 First Login — Empty Work Panel

When a staff member logs in for the first time and has no work items yet, the Work Panel shows:

**Onboarding Checklist card** (in place of Needs Action):
```
Getting started
─────────────────────
✓  Your account is active
○  Complete your profile
○  Review your permissions
○  Explore My Wizards
○  Mark your first attendance  ← (Faculty only)
```
Each checklist item is a link that opens the relevant wizard or screen in the canvas.

**Your Hierarchy card** (below checklist):
- Your name, role, department
- Reports to: [manager name + role]
- Your direct reports (if any): list of names + roles
- Your department's org chart (compact tree, 2 levels deep)
- Click any person → opens their profile in the canvas

Both cards disappear as the user completes the checklist and real work items begin to populate.

---

### 2.4 My Wizards (Nav Toggle)

**Trigger**: "My Wizards" button at the bottom of the Work Panel (also accessible via keyboard shortcut).

**Behaviour**: Clicking My Wizards opens the My Wizards page in the canvas. The Work Panel remains visible on the left. The AI Copilot remains on the right.

Clicking any wizard on the My Wizards page opens that wizard as a **tab** in the canvas (see 2.5). The My Wizards page is replaced by the wizard content.

#### My Wizards Page Layout

```
My Wizards
────────────────────────────────────────
[ 🔍 Search wizards... ]

⭐ Pinned
┌──────────┐  ┌──────────┐  ┌──────────┐
│Timetable │  │ Reports  │  │  + Pin   │
└──────────┘  └──────────┘  └──────────┘

Recent
┌──────────┐  ┌──────────┐
│Doc Queue │  │ Invoices │
└──────────┘  └──────────┘

────────────────────────────────────────
Academics          Admissions
Timetable          Pipeline
Attendance         Document Queue
OBE Mapping        Merit List
                   Seat Matrix

Finance            HR
Invoices           Staff Directory
Payments           Leave Calendar
Scholarships       Payroll
Tally Export       Performance

Examinations       Student Services
Exam Schedule      Hostel
Hall Tickets       Library
Results Entry      Grievances

…(all modules listed)
```

**Search**: filters the grid in real-time by wizard name. Matches highlighted.

**Pinned**: up to 6 wizards pinned by the user. Drag to reorder. Pin/unpin via the ⋮ menu on any WizardCard.

**Recent**: last 5 opened wizards, most recent first.

**WizardCard** component:
- Module icon (coloured)
- Wizard name
- One-line description
- Click → opens in canvas as a tab
- ⋮ menu → Pin / Unpin, Open in new tab

---

### 2.5 Canvas — Frame & Tab System (Hybrid D)

The canvas is the centre zone where all work happens. It operates at **three depths**:

```
Level 1: Tabs          (wizard sessions, persistent)
Level 2: Drawers       (item detail, max 2 deep)
Level 3: Modals        (focused actions, task-complete)
```

#### Level 1 — Tabs

Wizard tabs appear as a tab bar at the top of the canvas.

```
[Timetable ×]  [Invoices ×]  [Merit List ×]  [+]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [active wizard content]
```

**Rules**:
- Maximum **5 tabs** open simultaneously. Opening a 6th prompts: "You have 5 open wizards. Close one to continue."
- Tabs are **persistent** — navigating away and returning restores the tab with its state intact
- Tabs are closed with the × button. Closing a tab with unsaved changes shows a "Save changes?" dialog
- The **[+]** button opens My Wizards to pick a new wizard
- **Work Panel items** (Incoming/Initiated) do **not** open as tabs — they open in-place in the canvas below the tab bar. When a work item is open, tabs remain accessible above it

**Active tab indicator**: Blue underline on the active tab, bold label.

#### Level 2 — Drawers

Clicking a row or item within a wizard opens a **Drawer** — a panel that slides in from the right, overlapping the canvas.

```
┌────────────────────────────┬──────────────────┐
│  Timetable (wizard)        │  Slot Detail     │
│  [content dimmed]          │  (Drawer 1)      │
│                            │                  │
│                    ┌───────────────────────┐  │
│                    │  Faculty Profile      │  │
│                    │  (Drawer 2)           │  │
│                    └───────────────────────┘  │
└────────────────────────────┴──────────────────┘
```

**Rules**:
- Maximum **2 drawers** deep (Drawer 1 + Drawer 2)
- Each drawer has a back arrow (←) to close it and return to the previous level
- Drawer 1 is 480px wide. Drawer 2 is 400px wide (slightly narrower to show depth)
- Both drawers have their own scroll — they do not scroll the canvas behind them
- Clicking outside a drawer closes it (with unsaved-changes guard)

#### Level 3 — Modals

Actions **within** a drawer (approve, reject, raise appeal, enter marks, write a note) open as a **Modal** — a centred overlay on top of everything.

**Rules**:
- Modals are **task-complete** — they never open further drawers or modals
- Every modal has a Cancel button and a primary action button
- Modals are dismissed by: completing the action, Cancel, or pressing Escape
- Maximum width: 560px for forms; 800px for document previews

#### Navigation summary

| User action | What opens | Depth |
|---|---|---|
| Click wizard in My Wizards | New canvas tab | Level 1 |
| Click item in Work Panel | In-place canvas frame (below tab bar) | Level 1 |
| Click row in wizard table | Drawer (slide from right) | Level 2 |
| Click related item inside Drawer 1 | Drawer 2 (narrower, layered) | Level 2 |
| Click action inside any drawer | Modal (centred overlay) | Level 3 |
| Complete modal action | Returns to drawer that triggered it | — |
| Close drawer | Returns to wizard canvas | — |

---

### 2.6 AI Copilot (Right Rail, 320px)

Permanently on the right side. Collapsible to a 40px strip with just the AI icon.

**Header**: "ALIS Assistant" + model indicator + collapse button

**Context awareness**: The Copilot reads the currently active canvas frame and automatically adjusts its context. A small label shows what it's currently looking at: "Context: Timetable" or "Context: Document Review — Rahul Sharma".

**Modes**:

**Idle mode** (no active frame):
- Quick action chips: "Summarise today's approvals", "Show overdue fees", "Which students are below 75% attendance?", "Draft an announcement", "Flag anomalies in recent scores"

**Contextual mode** (wizard active):
- Auto-populated insights relevant to the current frame
- Examples for Timetable: "2 faculty conflicts detected", "Room 301 is double-booked on Wednesday"
- Examples for Merit List: "Category-wise seat utilisation: OBC-NCL has 3 unfilled seats"
- Examples for Grievances: "Average resolution time: 4.2 days (SLA is 3 days)"
- Suggested action buttons below insights (e.g. "Resolve conflicts", "Auto-promote waitlist")

**Chat mode** (always accessible):
- Text input + Send
- Chat history persists per session
- AI cannot take write actions — it only reads and suggests

---

### 2.7 Role-Based Work Panel Content

The Work Panel UI is identical for all roles. The content is filtered by role and permissions.

#### Registrar
**Incoming — Needs Action**:
- Offer letters awaiting countersignature
- Final verification approvals (dual-control)
- Identity mismatch flags (EC-ADM-01)
- Merit list ready to publish (confirmation required)
- Fee waiver requests from Finance

**Initiated**:
- Merit list generation in progress
- Bulk offer letter dispatch (waiting for email delivery confirmation)

**My Wizards (default pinned)**: Pipeline, Document Queue, Merit List, Reports

---

#### Admissions Coordinator
**Incoming — Needs Action**:
- Documents assigned to me for review
- Lead follow-up reminders
- Reporting gate — students not yet checked in (deadline approaching)
- AI-flagged eligibility anomalies

**Initiated**:
- Bulk lead import processing
- Counsellor assignment batch running

**My Wizards (default pinned)**: Pipeline, Document Queue, Lead CRM

---

#### Faculty
**Incoming — Needs Action**:
- Attendance marking reminder (class starts in 30 min / class ongoing)
- Marks entry deadline approaching
- TA assignment notification
- Student query message

**Initiated**:
- Marks entry in progress (partially saved)

**My Wizards (default pinned)**: Attendance, Results Entry, Timetable

---

#### HOD
**Incoming — Needs Action**:
- Leave approval requests from my faculty
- Visiting faculty session verification (OTP confirmed, HOD verify pending)
- Students at-risk alert (below 75% in my dept)
- Viva scheduling request

**Initiated**:
- Performance review cycle in progress

**My Wizards (default pinned)**: Leave Calendar, Faculty Attendance, OBE Mapping

---

#### Finance Manager
**Incoming — Needs Action**:
- Payment reconciliation anomaly flagged by AI
- Scholarship approval request
- Fee waiver request (from Registrar)
- Failed payment webhook alert

**Initiated**:
- Invoice batch generating
- Payroll run in progress

**My Wizards (default pinned)**: Invoices, Payments, Scholarships, Tally Export

---

#### Exam Controller
**Incoming — Needs Action**:
- Results upload pending (deadline approaching)
- Re-evaluation request assigned
- AI anomaly flag on submitted marks
- Hall ticket generation approval

**Initiated**:
- Results verification in progress

**My Wizards (default pinned)**: Exam Schedule, Results Entry, Re-evaluation Queue

---

#### HR Manager
**Incoming — Needs Action**:
- Leave request escalated beyond HOD
- Performance review pending finalisation
- New staff account setup required

**Initiated**:
- Payroll approval in progress

**My Wizards (default pinned)**: Staff Directory, Leave Management, Payroll

---

### 2.8 Canvas Home — Role Dashboard

When the canvas has no open tab and no Work Panel item is selected, it shows the **role dashboard** — a stat card grid and quick-access charts for that role's key metrics.

This is the canvas's resting state, not the primary work surface. It answers "how is everything doing right now?" while the Work Panel answers "what do I need to do?"

**Layout**: 4-column grid of StatCards at `xl`, 2-column at `md`. One or two chart cards below the stat row.

---

#### Registrar Canvas Home

**Stat cards**:
- Total applications this cycle (with % change vs. last cycle)
- Pending document reviews (amber if > 50)
- Offer letters awaiting countersignature (red if SLA > 48h)
- Enrolled students YTD

**Charts**:
- Pipeline funnel chart (applicants by stage, bar)
- Category-wise seat utilisation (horizontal bar: filled vs total seats per category)

**API**: `GET /api/v1/admissions/pipeline/summary`, `GET /api/v1/admissions/seats/matrix`

---

#### Admissions Coordinator Canvas Home

**Stat cards**:
- Leads assigned to me (with "new today" badge)
- Documents pending my review
- Reporting gate attendance today (% of expected)
- Merit list status (badge: "Not yet run" / "Draft" / "Published")

**Charts**:
- Lead funnel (this week vs last week, grouped bar)
- Document review turnaround (avg hours per type)

**API**: `GET /api/v1/admissions/leads?assigned_to=me`, `GET /api/v1/admissions/documents?assigned_to=me`

---

#### Faculty Canvas Home

**Stat cards**:
- My subjects this semester (count)
- Classes taken today (out of scheduled)
- Average attendance across my subjects (%)
- Results pending entry (count, red if deadline < 3 days)

**Charts**:
- Attendance trend — last 30 days (line, per subject)
- Class-wise attendance comparison (horizontal bar)

**API**: `GET /api/v1/academics/timetable/my-schedule`, `GET /api/v1/academics/attendance/summary?faculty=me`

---

#### HOD Canvas Home

**Stat cards**:
- Faculty in my department (total / on leave today)
- Department average attendance (%)
- Pending leave approvals
- Students below 75% attendance (at-risk count, red if > 0)

**Charts**:
- Department attendance by subject (horizontal bar)
- Leave requests this month (line: applied vs approved)

**API**: `GET /api/v1/hr/leave-requests?department=mine&status=PENDING`, `GET /api/v1/academics/attendance/department-summary`

---

#### Finance Manager Canvas Home

**Stat cards**:
- Fees collected this month (₹, with % of target)
- Outstanding dues (₹)
- Pending scholarship approvals
- Failed payments this week (count, red if > 0)

**Charts**:
- Fee collection trend — last 6 months (area chart, ₹)
- Collection by mode (pie: Online / Cash / Cheque / NEFT)

**API**: `GET /api/v1/finance/payments/summary`, `GET /api/v1/finance/invoices?status=OVERDUE`

---

#### Exam Controller Canvas Home

**Stat cards**:
- Upcoming exams this month (count)
- Hall tickets pending generation (amber if > 0)
- Results pending entry (count, by subject)
- Re-evaluation requests pending (count)

**Charts**:
- Results status by subject (stacked bar: Entered / Pending / Verified)
- Re-evaluation turnaround (avg days this semester)

**API**: `GET /api/v1/examinations/schedule`, `GET /api/v1/examinations/results/pending`

---

#### HR Manager Canvas Home

**Stat cards**:
- Total active staff
- Leave requests this month (pending / approved / rejected)
- Payroll runs this year (last run date)
- Performance reviews pending finalisation

**Charts**:
- Leave utilisation by department (horizontal bar)
- Staff headcount by department (donut)

**API**: `GET /api/v1/hr/staff?status=ACTIVE`, `GET /api/v1/hr/leave-requests/summary`, `GET /api/v1/hr/payroll/history`

---

## Part 3 — Standalone: Attendance Marking (PWA)

Attendance marking is a **purpose-built standalone layout** — separate from the Work Panel + Canvas system. It is the only screen designed mobile-first.

### Why standalone?

Faculty need to mark attendance quickly, often on a phone, sometimes without internet. The full Work Panel + drawer system is the wrong tool. The attendance experience is optimised exclusively for speed and offline reliability.

### Entry points

- **From Work Panel**: "Mark attendance — [Subject] starts in 10 min" item → taps to open the standalone attendance view full-screen (Work Panel and Copilot hidden)
- **From My Wizards → Attendance**: opens the standalone view
- **Direct PWA**: installed on faculty phone as a home screen app → opens directly to the attendance session selector

### Layout

Full-screen, no left panel, no right rail. Clean white background, maximum content.

```
┌──────────────────────────────┐
│  ← [Subject] · [Batch]       │  ← back to ERP
│  15 Mar 2025 · 10:00 AM      │
│  ●●●●●○○  Offline            │  ← sync status
├──────────────────────────────┤
│  [Mark all present]          │
│  [Mark all absent]           │
├──────────────────────────────┤
│  📷 CS001 · Amit Sharma      │  ← roll + photo + name
│  [ Present ] [ Absent ] [Late]│
│                              │
│  📷 CS002 · Priya Nair       │
│  [ Present ] [ Absent ] [Late]│
│                              │
│  …                           │
├──────────────────────────────┤
│  23 Present · 2 Absent       │
│  [ Submit Attendance ]       │
└──────────────────────────────┘
```

### Behaviour

- **Student list** cached on first load, refreshed when online
- **Toggle buttons** (Present / Absent / Late) — tap once to select, tap again to change
- **Submit** → confirmation dialog → submits; session locked after submission
- **Offline**: submissions saved to IndexedDB; "X sessions pending sync" banner; auto-syncs on reconnect; manual "Sync now" button
- **Back button** (←) returns to the ERP shell (Work Panel restored)

### Session selector (before marking)

If opened from My Wizards (not from a specific Work Panel item):

```
Select a session to mark
────────────────────────
Today · 15 Mar 2025

10:00 AM  CS301 · Data Structures · Batch B  [Mark →]
12:00 PM  CS401 · Algorithms · Batch A       [Mark →]

Past sessions (unmarked)
14 Mar  CS301 · Batch B  [Mark →]  ⚠ 1 day late
```

Past unmarked sessions are shown with a warning badge (late submission).

**API**: `GET /api/v1/academics/attendance/my-sessions`, `POST /api/v1/academics/attendance/sessions/{id}/submit`

---

## Part 4 — Admissions Module

### Screen 4.1: Pipeline (Kanban)
**Frame**: Pipeline (Kanban) Workspace
**Who**: ADMISSIONS_COORDINATOR, REGISTRAR

**Layout**: Full-width Kanban board with horizontal scroll. Each stage is a column.

**Columns (left → right)**:
1. Lead
2. Submitted
3. Docs Review
4. Eligible
5. Merit Listed
6. Offer Sent
7. Enrolled

**Column header**: Stage name + count badge.

**Each card shows**:
- Applicant full name
- Programme preference (first choice)
- Application ID (monospace, small)
- Days in this stage (SLABar — turns amber at 5 days, red at 10 days)
- Flag icon (red) if the record has been flagged for review

**Filters bar** (above the board):
- Academic batch / cycle selector (dropdown)
- Programme filter (multi-select)
- Category filter (multi-select: General / SC / ST / OBC-NCL / EWS / PwD)
- Search (by name or application ID)
- "My assigned" toggle (shows only records assigned to me)

**Actions**:
- Click any card → opens Applicant Detail Drawer (4.2)
- Drag card to next column → moves applicant to that stage (with confirmation for backward moves)
- Select multiple cards (checkbox on hover) → bulk action bar appears at bottom: "Move to next stage", "Send reminder", "Export selected"

**API**: `GET /api/v1/admissions/applicants`, `GET /api/v1/admissions/pipeline/summary`

---

### Screen 4.2: Applicant Detail Drawer
**Trigger**: Clicking any applicant card or search result.
**Layout**: Full-height right-side panel (640px wide), overlay on the pipeline. Has a close (×) button and an "Open full page" icon.

**Header area**:
- Applicant photo (or initials avatar)
- Full name + Application ID
- Current stage badge (colour-coded)
- Programme preference badge
- "Flag for review" toggle

**8 tabs**:

**Tab 1 — Overview**:
- Personal details grid: Name, DOB, Gender, Category, Nationality, Aadhaar (masked: ••••••••1234)
- Contact: Email, Phone
- Source channel (how they found the institution)
- Programme preferences (numbered list: 1st, 2nd, 3rd choice with specialisation and intake batch)
- Hostel required: Yes / No
- Scholarship consideration: Yes / No
- Work experience (months, if entered)
- How heard about us

**Tab 2 — Documents**:
- Table: Document type | Submitted on | Method (Manual upload / DigiLocker verified / Board API) | Status badge | Actions
- Status values: `Pending` (grey) · `Under Review` (blue) · `Approved` (green) · `Rejected` (red) · `Re-upload Requested` (amber)
- Row actions per document: **View** (opens PDF preview in modal), **Approve**, **Reject** (requires reason), **Request Re-upload**
- Override button (REGISTRAR only): override any status with a mandatory reason
- DigiLocker verified documents show a blue "DigiLocker ✓" badge

**Tab 3 — Eligibility**:
- Eligibility criteria table: Criterion | Required | Applicant value | Met? (✓/✗)
- Category relaxation applied (shown if applicable)
- Overall result badge: `Eligible` / `Not Eligible` / `Conditionally Eligible`
- **Re-evaluate** button (runs eligibility check again with current data)

**Tab 4 — Entrance & Interview**:
- Entrance exam scores submitted: Exam name | Roll # | Score | Percentile | Rank | Year | Verified badge
- Interview panel (if assigned): Panel name, Interviewer names, Scheduled date/time, Mode (In-person / Video)
- Interview scorecard (if completed): Criteria → Rating (1–5) per criterion + total + recommendation (Recommend / Hold / Reject)
- Interviewer notes (read-only)

**Tab 5 — Offer**:
- Offer status: `Not Generated` / `Generated` / `Sent` / `Accepted` / `Declined` / `Expired`
- If offer exists: Programme, Campus, Intake batch, Tuition fee (₹), Scholarship applied (₹), Net fee
- Offer validity: valid-until date + days remaining countdown
- Staff actions: **Generate offer** / **Resend offer** / **Record acceptance** / **Record decline**
- Download offer letter PDF button
- Decline reason (if declined by applicant)

**Tab 6 — Payment**:
- Fee schedule table: Fee component | Amount (₹) | Due date | Status
- Payment history table: Date | Amount | Method | Reference # | Status badge
- **Record offline payment** button → modal: amount (₹), method (Cash / Cheque / NEFT / RTGS), reference number, payment date
- Refund history (if any)

**Tab 7 — Notes**:
- List of internal staff notes — note text + author + timestamp (newest first)
- Text area + **Add note** button (only visible to staff, never to applicant)

**Tab 8 — Timeline**:
- Full audit timeline using TimelinePanel component
- Every state transition, document action, communication sent — with actor, timestamp, and description

**API**: `GET /api/v1/admissions/applicants/{id}`, `GET /api/v1/admissions/documents/{applicant_id}`, `GET /api/v1/admissions/interviews/{applicant_id}`, `GET /api/v1/admissions/offers/{applicant_id}`, `GET /api/v1/admissions/payments/{applicant_id}`, `PATCH /api/v1/admissions/documents/{doc_id}/review/*`, `POST /api/v1/admissions/offers`, `POST /api/v1/admissions/payments/offline`

---

### Screen 4.3: Lead CRM
**Frame**: Lead CRM Workspace
**Who**: ADMISSIONS_COORDINATOR

**Layout**: Table (left 65%) + Detail panel (right 35%, shown when row is selected)

**Table columns**: Name | Email | Phone | Source channel | Assigned counsellor | Status | Created date

**Status values (funnel)**: New → Contacted → Interested → Ready to Apply → Converted

**Filters**: Status (multi-select), Source (multi-select), Assigned counsellor (dropdown), Date range

**Table actions**: Click row → opens detail panel

**Detail panel**:
- Lead name + contact info
- **Status dropdown** (update inline)
- **Reassign counsellor** button → dropdown of available counsellors
- Call log: list of calls with date, duration, outcome note
- **Log a call** button → modal: date, duration, outcome notes
- Internal notes: text area + add

**Top bar actions**:
- **Add lead** button → modal with: Name, Email, Phone, Intended programme, Source channel, Notes
- **Import CSV** button → upload a CSV of bulk leads
- **Export** button → downloads current filtered list as CSV

**Duplicate detection**: System automatically flags possible duplicates (same phone or email). A yellow banner on the detail panel shows: "Possible duplicate found — [Name]" with a "Review & merge" link.

**API**: `GET /api/v1/admissions/leads`, `POST /api/v1/admissions/leads`, `PATCH /api/v1/admissions/leads/{id}`, `GET /api/v1/admissions/leads/{id}/duplicates`, `POST /api/v1/admissions/leads/merge`

---

### Screen 4.4: Document Verification Queue
**Frame**: Document Verification Queue Workspace
**Who**: Document Verification Officer, REGISTRAR

**Layout**: Full-width table with filter bar

**Table columns**: Applicant name | Application ID | Document type | Submitted on | Method | Assigned to | Status | Actions

**Filters**: Status (Pending / Under Review / Approved / Rejected), Document type (multi-select), Date range, Assigned to (dropdown)

**Row actions**: **View** (PDF preview modal) · **Start review** (locks to me, changes status to Under Review) · **Approve** · **Reject** (reason required) · **Request Re-upload**

**Bulk actions** (select multiple rows): Assign to reviewer, Approve all selected, Export

**PDF Preview modal**: Full-height document preview + action buttons at the bottom (Approve / Reject / Request Re-upload)

**API**: `GET /api/v1/admissions/documents`, `POST /api/v1/admissions/documents/{id}/review/start`, `POST /api/v1/admissions/documents/{id}/review/approve`, `POST /api/v1/admissions/documents/{id}/review/reject`, `POST /api/v1/admissions/documents/{id}/reupload`

---

### Screen 4.5: Merit List
**Frame**: Merit List Workspace
**Who**: REGISTRAR

**Layout**: Left panel (policy config, 320px) + Right panel (ranked table, fluid)

**Left panel — Formula & Seats**:
- Formula weights section: Three sliders (0–100%) — Academic %, Entrance Score, Interview Score. Must sum to 100% (live validation, shows error if not).
- Category seat allocation table: Category | Seats (editable number input per row)
- Minimum cutoff per category (number input for each)
- **Save policy** button

**Right panel — Merit List**:
- Table: Rank | Name | Application ID | Category | Academic % | Entrance score | Interview score | Composite score | Status (Merit / Waitlist / Not Listed)
- Sort by any column
- Filter by category, status

**Actions**:
- **Generate merit list** button → shows preview confirmation modal ("This will generate rankings for X applicants. Continue?") → generates on confirm
- **Publish** button (visible after generation) → sends notifications to merit-listed applicants, locks the list
- **Export** button → CSV or PDF
- **Manage waitlist** button → opens panel to promote waitlisted candidates as seats open

**Waitlist panel**:
- Table of waitlisted applicants in rank order
- **Promote next** button → promotes #1 waitlist to merit and sends offer
- Manual promote by selecting a specific waitlisted applicant

**API**: `GET /api/v1/admissions/merit-list`, `POST /api/v1/admissions/merit-list/generate`, `POST /api/v1/admissions/merit-list/publish`, `PUT /api/v1/admissions/merit-list/policy`

---

### Screen 4.6: Seat Matrix
**Frame**: Seat Matrix Workspace
**Who**: REGISTRAR

**Layout**: Full-width editable grid

**Rows**: One per programme
**Columns**: Programme | Total Seats | General | SC | ST | OBC-NCL | EWS | PwD | Filled | Vacant

Each cell in the seat-count columns is editable inline (click to edit, Enter to confirm, Escape to cancel). Filled and Vacant columns are calculated (read-only).

**Actions**:
- Inline edit any seat count
- **Save all changes** button (bottom)
- **Discard changes** button
- **View history** button → side panel showing all past seat count changes with who changed what and when

**API**: `GET /api/v1/admissions/seat-matrix`, `PUT /api/v1/admissions/seat-matrix`

---

### Screen 4.7: Reporting Gate
**Frame**: Reporting Gate Workspace
**Who**: ADMISSIONS_COORDINATOR

**Purpose**: Track which admitted students have physically reported to the institution.

**Layout**: Table with top stats

**Top stats**: Total admitted this batch | Reported | Not yet reported | Overdue (past deadline)

**Table columns**: Name | Programme | Allocated seat | Reporting deadline | Days remaining (SLABar) | Method | Status

**Status values**: Pending · Reported · Excused · No-show

**Row actions**:
- **Mark as reported** button → records method (Walk-in or QR scan) + timestamp
- **Extend deadline** → modal with new date + reason
- **Send reminder** → triggers SMS/email to student

**Bulk action**: Select multiple → Send reminder to all

**QR Scan mode**: Large "Scan QR" button toggles a camera input (on supported devices) that reads the student's hall pass QR and auto-marks as reported.

**API**: `GET /api/v1/admissions/reporting-gate`, `POST /api/v1/admissions/reporting-gate/{id}/mark-reported`, `POST /api/v1/admissions/reporting-gate/{id}/extend-deadline`

---

### Screen 4.8: Re-admissions
**Frame**: Re-admissions Workspace
**Who**: REGISTRAR

**Layout**: Table + detail drawer

**Table columns**: Name | Programme | Semesters completed | Gap period | Reason for gap | Status | Applied on

**Status values**: Pending Review · Documents Requested · Approved · Rejected

**Row actions**: Click → detail drawer showing full re-admission application

**Detail drawer**:
- Academic history (semesters, CGPA)
- Gap period explanation
- Supporting documents (upload area)
- Staff actions: **Approve**, **Reject** (reason required), **Request more documents**

**API**: `GET /api/v1/admissions/readmissions`, `POST /api/v1/admissions/readmissions/{id}/approve`, `POST /api/v1/admissions/readmissions/{id}/reject`

---

### Screen 4.9: Identity Match Review (EC-ADM-01)
**Frame**: Identity Match Review (EC-ADM-01) Workspace
**Who**: ADMISSIONS_COORDINATOR, REGISTRAR

**Purpose**: The system automatically flags applicants where the name on submitted documents doesn't match the name on Aadhaar/DigiLocker records. Staff reviews and resolves.

**Layout**: Table of flagged records

**Table columns**: Name (as entered) | Name (as on document) | Document type | Match confidence | Flag reason | Status | Assigned to

**Match confidence**: Colour-coded percentage (green ≥90%, amber 70–89%, red <70%)

**Status values**: Flagged · Under Review · Name Mismatch Confirmed · False Positive · Resolved

**Row actions**: Click → detail panel

**Detail panel**:
- Side-by-side comparison: "Application name" vs "Document name" with character-level diff highlighting
- Document preview (right side)
- Staff decision: **Confirm mismatch** (escalates to student for clarification) · **Mark as false positive** (e.g. common name variations like "Mohammed" / "Mohammad") · **Override and approve** (Registrar only, with reason)
- Notes field for decision rationale

**API**: `GET /api/v1/admissions/identity-mismatches`, `POST /api/v1/admissions/identity-mismatches/{id}/resolve`

---

### Screen 4.10: Access Lift Panel (EC-ADM-05)
**Frame**: Access Lift Panel (EC-ADM-05) Workspace
**Who**: REGISTRAR

**Purpose**: When a student whose UTR (Unique Transaction Reference) needs urgent fee verification, Registrar can grant a temporary 48-hour access lift — allowing enrollment to proceed while fee confirmation is pending.

**Layout**: Table of active and past access lifts

**Table columns**: Student name | Application ID | UTR submitted | Lift granted by | Granted at | Expires at | Status | Auto-revoke countdown

**Status values**: Active · Expired · Manually Revoked

**Actions**:
- **Grant lift** button → modal: select student, enter UTR, confirm 48-hour window
- **Revoke** button on active lifts (if fee not confirmed in time)
- Expired lifts show greyed-out rows with reason (auto-expired or manually revoked)

**Banner on applicant detail** (shown when an active lift exists): "⚠ Temporary 48h access lift active — expires [time]. Fee verification pending."

**API**: `POST /api/v1/admissions/access-lift`, `DELETE /api/v1/admissions/access-lift/{id}`

---

## Part 5 — Academics Module

### Screen 5.1: Programmes & Courses
**Frame**: Programmes & Courses Workspace
**Who**: ACADEMICS_MANAGER, HOD (read), FACULTY (read)

**Tabs**: Programmes | Courses

**Programmes tab**:
- Table: Programme name | Code | Type (UG/PG/Diploma/PhD) | Duration | School/Dept | Total credits | Status
- **Add programme** button → drawer with: Name, Code, Type, Duration, School, Description, Total credits
- Click row → programme detail page: curriculum structure (semesters as accordion → courses within each semester)
- Edit / Archive buttons per row

**Courses tab**:
- Table: Code | Course name | Credits | Type (Theory/Lab/Project/Elective) | Assigned faculty | Semester | Status
- **Add course** button → drawer with: Code, Name, Credits, Type, Semester, Prerequisites (multi-select from existing courses), Syllabus description
- **Assign faculty** button per course → dropdown of available faculty
- Filter by: Programme, Semester, Type, Faculty

**API**: `GET /api/v1/academics/programmes`, `POST /api/v1/academics/programmes`, `GET /api/v1/academics/courses`, `POST /api/v1/academics/courses`, `PATCH /api/v1/academics/courses/{id}/assign-faculty`

---

### Screen 5.2: Timetable
**Frame**: Timetable Workspace
**Who**: ACADEMICS_MANAGER, HOD, FACULTY (read-only view of own schedule)

**Layout**: Week-grid calendar (Monday–Saturday columns, 8:00 AM–6:00 PM rows in 1-hour slots)

**View modes** (toggle pills): By Batch | By Faculty | By Room

**Slot card content**: Subject code + name, Faculty initials, Room number; colour-coded by subject type (Theory = blue, Lab = green, Elective = purple)

**Conflict indicator**: Overlapping slots highlighted in red; a conflict summary banner appears at the top.

**Actions**:
- Click empty slot → **Add class** modal: Day, Time, Duration, Subject (dropdown), Faculty (dropdown), Room (dropdown), Batch (dropdown); system auto-checks for conflicts before saving
- Click existing slot → **Edit** or **Delete**
- **Auto-detect conflicts** button → highlights all conflicts in red
- **Publish timetable** button → sends push notification to all students and faculty in affected batches
- **Export as PDF** button

**API**: `GET /api/v1/academics/timetable`, `POST /api/v1/academics/timetable/slots`, `PUT /api/v1/academics/timetable/slots/{id}`, `POST /api/v1/academics/timetable/publish`

---

### Screen 5.3: Attendance Marking (Faculty View — PWA)
**Frame**: Attendance Marking (Faculty View — PWA) Workspace
**Who**: FACULTY

**This screen must work fully offline (PWA). Attendance marked offline syncs when connectivity is restored.**

**Step 1 — Select session**:
- Dropdown: Subject (shows only my assigned subjects)
- Date picker (defaults to today)
- Class/batch selector
- System auto-fills the session if there is an ongoing class per timetable

**Step 2 — Mark attendance**:
- Student list: Roll number | Name | Present / Absent / Late (toggle button group per row)
- **Mark all present** button, **Mark all absent** button
- Total: X present, Y absent, Z late (live counter as marks are entered)
- Student photo shown next to name (aids recognition)

**Step 3 — Submit**:
- **Submit attendance** button → confirmation dialog ("This cannot be edited after submission. Continue?") → submits
- Submitted sessions are locked; REGISTRAR/HOD can override

**Offline indicator**: If device is offline, a banner shows "Offline mode — X session(s) pending sync." Session is saved locally. On reconnect, auto-syncs with a success toast.

**Sync status banner**: Shows sync time ("Last synced: 2 minutes ago") or a "Sync now" button if automatic sync hasn't run.

**API**: `POST /api/v1/academics/attendance/sessions`, `GET /api/v1/academics/attendance/students/{batch_id}`, `POST /api/v1/academics/attendance/sessions/{id}/submit`

---

### Screen 5.4: Attendance Report (Admin View)
**Frame**: Attendance Report (Admin View) Workspace
**Who**: HOD, ACADEMICS_MANAGER, REGISTRAR

**Layout**: Filter bar + summary table

**Filters**: Department, Programme/Batch, Subject, Faculty, Date range, Minimum % threshold (slider: 0–100%)

**Table columns**: Roll no. | Name | Programme | Sessions conducted | Present | Absent | Late | Attendance % | Status

**Status values and colours**:
- ✓ OK (≥75%) — green
- ⚠ Warning (60–74%) — amber
- ✗ Detained (<60%) — red

**Actions**:
- **Export CSV** button
- Click student row → student attendance detail (per-subject breakdown with calendar heatmap)
- **Override attendance** button (REGISTRAR only) → modal: student, subject, date, corrected value, reason
- **Send warnings** bulk action → sends email/SMS to selected students below threshold

**API**: `GET /api/v1/academics/attendance/report`, `GET /api/v1/academics/attendance/students/{id}`, `POST /api/v1/academics/attendance/override`

---

### Screen 5.5: OBE / CO-PO Mapping
**Frame**: OBE / CO-PO Mapping Workspace
**Who**: FACULTY (edit own courses), ACADEMICS_MANAGER (edit all)

**4 tabs**:

**Programme Outcomes (POs)**:
- Table: PO code | Description | Bloom's Taxonomy Level (dropdown: Remember / Understand / Apply / Analyse / Evaluate / Create)
- **Add PO** button → inline row with code and description inputs
- Edit / Delete per row

**Course Outcomes (COs)**:
- Programme selector + Course selector (dropdowns at top)
- Table: CO code | Description | BT Level
- **Add CO** button
- Edit / Delete per row

**Mapping Matrix**:
- Course selector at top
- Grid: COs (rows) × POs (columns)
- Each cell: dropdown — None / Low (1) / Medium (2) / High (3)
- Cells with no correlation are visually dimmed
- **Save mapping** button (bottom)

**Attainment**:
- Course + Semester selectors
- CO Attainment: horizontal bar chart per CO (% attainment calculated from mapped exam marks)
- PO Attainment: horizontal bar chart per PO (aggregated from CO-PO matrix)
- Summary table: CO/PO | Target % | Attained % | Gap
- **Export attainment report** button (PDF)

**API**: `GET/POST/PUT /api/v1/academics/obe/pos`, `GET/POST/PUT /api/v1/academics/obe/cos`, `GET/PUT /api/v1/academics/obe/mapping`, `GET /api/v1/academics/obe/attainment`

---

## Part 6 — Examinations Module

### Screen 6.1: Exam Schedule Management
**Frame**: Exam Schedule Management Workspace
**Who**: EXAM_CONTROLLER

**Layout**: Table + calendar toggle

**Table columns**: Exam name | Subject | Programme/Batch | Date | Time | Duration | Venue | Status | Hall ticket status

**Status values**: Draft · Scheduled · Ongoing · Completed · Cancelled

**Calendar toggle**: Same data shown as month-view calendar with exam cards on date cells.

**Actions**:
- **Create exam** button → modal: Exam name, Subject (dropdown), Batch(es) (multi-select), Date, Start time, Duration, Venue, Max marks, Instructions
- Edit exam (click row → drawer)
- Cancel exam (with reason + notification to students)
- **Generate hall tickets** button per exam (or bulk) → confirmation showing count of eligible students

**API**: `GET /api/v1/examinations/schedules`, `POST /api/v1/examinations/schedules`, `PUT /api/v1/examinations/schedules/{id}`, `POST /api/v1/examinations/schedules/{id}/hall-tickets/generate`

---

### Screen 6.2: Hall Ticket Management
**Frame**: Hall Ticket Management Workspace
**Who**: EXAM_CONTROLLER (generate), STUDENT (download — via portal)

**Staff view**:
- Filter by: Exam, Batch, Status (Generated / Sent / Downloaded)
- Table: Roll no. | Student name | Exam | Status | Generated on | Downloaded?
- **Generate all** button, **Generate selected** button
- **Send to students** bulk action → pushes email/WhatsApp notification with download link
- **Download all as ZIP** button (bulk PDF download)

**Student view (portal — see Section 20)**:
- Simple list of upcoming exams with a **Download Hall Ticket** button per exam

**API**: `POST /api/v1/examinations/hall-tickets/generate`, `GET /api/v1/examinations/hall-tickets`, `GET /api/v1/examinations/hall-tickets/{id}/download`

---

### Screen 6.3: Results Entry
**Frame**: Results Entry Workspace
**Who**: FACULTY (enter), EXAM_CONTROLLER (review + publish)

**Layout**: Subject/exam selector at top + grade sheet below

**Selector**: Exam dropdown → Subject dropdown → Batch dropdown

**Grade sheet table**: Roll no. | Name | Max marks | Internal marks | External marks | Total | Grade (auto-calculated) | Pass/Fail (auto)

**Each mark cell is editable inline**. Tab to move to next cell. Enter to confirm.

**Validation**: Real-time — if a value exceeds max marks, the cell turns red.

**AI Anomaly Detection**: After entering all marks, an "Analyse scores" button runs AI checks and flags:
- Marks exactly at passing threshold for unusually many students
- Unusually uniform scores across students
- Single student with outlier score (very high or very low vs cohort)
Flags shown as yellow warning icons on affected rows with explanation tooltip.

**Actions**:
- **Upload CSV** button → download template + upload filled CSV
- **Submit for review** button (Faculty) → sends to Exam Controller for verification
- **Publish results** button (Exam Controller, after review) → makes results visible to students and sends notifications

**API**: `GET /api/v1/examinations/results/{exam_id}/{subject_id}`, `PUT /api/v1/examinations/results/bulk`, `POST /api/v1/examinations/results/publish`

---

### Screen 6.4: Re-evaluation Queue
**Frame**: Re-evaluation Queue Workspace
**Who**: EXAM_CONTROLLER

**Table columns**: Request # | Student | Programme | Subject | Exam | Current marks | Reason | Status | Assigned evaluator | Request date

**Status values**: Pending · Assigned · Under Review · Revised · Closed

**Row actions**: Click → detail drawer

**Detail drawer**:
- Original answer sheet (PDF preview if uploaded)
- Current marks + student's reason
- **Assign evaluator** dropdown (select faculty)
- **Enter revised marks** field (enabled only when status = Under Review)
- **Approve revised marks** / **Reject revision** (keeps original marks)
- Decision notes field

**Fee status indicator**: Whether the re-evaluation fee has been paid (must be paid before processing begins).

**API**: `GET /api/v1/examinations/reevaluation`, `POST /api/v1/examinations/reevaluation/{id}/assign`, `POST /api/v1/examinations/reevaluation/{id}/submit-revised`

---

## Part 7 — Finance Module

### Screen 7.1: Fee Structures
**Frame**: Fee Structures Workspace
**Who**: FINANCE_MANAGER

**Tabs**: Fee Structures | Invoices | Payments | Scholarships | Refunds | Export

**Fee Structures tab**:
- Table: Structure name | Programme | Intake batch | Total amount | Status
- Click row → fee structure detail: line items table (component name, amount), due date schedule, late penalty %

**Create fee structure** button → multi-step drawer:
1. Basic info: Name, Programme, Intake batch
2. Fee components: Table with + row button — Component name (text), Amount ₹ (number)
3. Due dates: Table — Instalment name, Due date, Amount, Grace period days
4. Penalties: Late fee type (flat ₹ / % per month), value

**Edit / Archive** per structure.

**API**: `GET /api/v1/finance/fee-structures`, `POST /api/v1/finance/fee-structures`, `PUT /api/v1/finance/fee-structures/{id}`

---

### Screen 7.2: Invoices
**Tabs → Invoices tab**

**Table columns**: Invoice # | Student | Programme | Issue date | Due date | Amount (₹) | Paid | Balance | Status | IRN

**Status values**: `Unpaid` · `Partial` · `Paid` · `Overdue` · `Waived` · `Cancelled`

**IRN column** (production feature): If e-invoice is configured, shows the IRN number in a monospace badge. If not yet generated, shows a "Generate IRN" button.

**Filters**: Status, Programme, Date range, Amount range

**Row action**: Click → Invoice detail page

**Invoice detail page**:
- Header: Institution letterhead (logo, address, GSTIN)
- Invoice metadata: Invoice #, issue date, due date, student name, roll number, programme
- Line items table: Description | HSN/SAC code | Amount (₹) | GST (%) | Total
- Payment history (if partial)
- **IRN / QR section** (production feature): if e-invoice is active, shows the IRN number, AckNo, AckDate, and a QR code image (for GST-compliant invoice). **Download e-Invoice PDF** button includes the QR.
- Actions: **Send invoice** (email + WhatsApp), **Download PDF**, **Record payment**, **Cancel invoice**, **Apply waiver**

**Bulk actions** (from table): Generate invoices for batch (select programme + batch → generates for all), Export selected, Send reminders to overdue

**API**: `GET /api/v1/finance/invoices`, `GET /api/v1/finance/invoices/{id}`, `POST /api/v1/finance/invoices/bulk-generate`, `POST /api/v1/finance/einvoice/{invoice_id}/generate`

---

### Screen 7.3: Payments
**Tabs → Payments tab**

**Table columns**: Date | Student | Programme | Amount (₹) | Method | Reference # | Status | Recorded by

**Status values**: `Success` · `Pending` · `Failed` · `Refunded`

**Filters**: Method, Status, Date range, Programme

**Record offline payment** button → modal:
| Field | Type | Notes |
|---|---|---|
| Student | search dropdown | Required |
| Invoice | dropdown (student's outstanding invoices) | Required |
| Amount (₹) | number | Required |
| Payment method | dropdown: Cash / Cheque / DD / NEFT / RTGS / UPI | Required |
| Reference / Transaction # | text | Required |
| Payment date | date picker | Required, defaults to today |
| Remarks | text area | Optional |

**Reconciliation view** (tab within Payments): Expected collections vs actual, gap report per batch.

**API**: `GET /api/v1/finance/payments`, `POST /api/v1/finance/payments/offline`

---

### Screen 7.4: Scholarships
**Tabs → Scholarships tab**

**Table columns**: Student | Programme | Scholarship type | Amount / % | Validity | Status

**Status values**: `Active` · `Pending Approval` · `Expired` · `Revoked`

**Award scholarship** button → modal:
| Field | Type |
|---|---|
| Student | search dropdown |
| Scholarship type | dropdown: Merit / Need-based / Sports / Government / Donor-funded |
| Value type | radio: Fixed amount (₹) / Percentage of fee (%) |
| Value | number |
| Applicable to | dropdown: All fees / Tuition only / Hostel only |
| Valid from / to | date range |
| Justification | text area (required) |

**Row actions**: **Revoke** (with reason), **Renew**, **View history**

**API**: `GET /api/v1/finance/scholarships`, `POST /api/v1/finance/scholarships`, `DELETE /api/v1/finance/scholarships/{id}`

---

### Screen 7.5: Refunds
**Tabs → Refunds tab**

**Table columns**: Request # | Student | Invoice # | Refund amount (₹) | Reason | Status | Requested on | Processed on

**Status values**: `Requested` · `Under Review` · `Approved` · `Processed` · `Rejected`

**Row actions**: **Approve** (with processing date and method), **Reject** (with reason)

**Approve modal**: Refund amount (₹, editable — can be less than requested), processing method (dropdown: Bank transfer / Cash / Credit to account), processing date, reference number.

**API**: `GET /api/v1/finance/refunds`, `POST /api/v1/finance/refunds/{id}/approve`, `POST /api/v1/finance/refunds/{id}/reject`

---

### Screen 7.6: Tally / Busy Export (Production Feature)
**Tabs → Export tab**
**Who**: FINANCE_MANAGER

**Purpose**: Export journal entries in Tally XML or Busy CSV format for the institution's accounting software.

**Layout**: Simple form + preview panel

**Form fields**:
| Field | Type | Notes |
|---|---|---|
| Export format | radio: Tally XML / Busy CSV | |
| Date range | date range picker | Required |
| Ledger type | multi-select: Fee receipts / Scholarships / Refunds / All | |
| GL mapping override | optional — table mapping ALIS fee components to Tally ledger names |

**Preview panel**: After clicking "Preview", shows a summary table of the journal entries that will be exported (Debit account, Credit account, Amount, Narration, Date). No detailed data — just counts and totals for confirmation.

**Actions**:
- **Preview** button
- **Download** button (generates and downloads the file)
- **Email to accountant** button (sends the file to a configured email address)

**API**: `POST /api/v1/finance/export/tally`, `POST /api/v1/finance/export/busy`

---

## Part 8 — HR Module

### Screen 8.1: Staff Directory & Profile
**Frame**: Staff Directory & Profile Workspace
**Who**: HR_MANAGER

**Tabs**: Staff | Leave | Payroll | Performance | Visiting Faculty

**Staff tab**:
- Table: Staff ID | Name | Designation | Department | Employment type | Join date | Status
- Filters: Department, Designation, Employment type (Permanent / Contract / Visiting), Status
- **Add staff** button → multi-section drawer:
  - Personal: First name, Last name, DOB, Gender, Nationality, Aadhaar (optional), PAN
  - Contact: Email, Mobile, Address
  - Employment: Designation, Department, Join date, Employment type, Salary grade, Reporting manager
  - Qualifications: Table — Degree, University, Year, % / Grade
  - Bank details: Account number, IFSC, Bank name, Branch
  - Upload photo

**Click row → Staff Profile page** (full page, same sections as above but in view mode with Edit button). Additional sections on profile:
- Leave balance summary
- Current course assignments
- Performance review history
- Documents (uploaded certificates, contracts)

**API**: `GET /api/v1/hr/staff`, `POST /api/v1/hr/staff`, `GET /api/v1/hr/staff/{id}`, `PUT /api/v1/hr/staff/{id}`

---

### Screen 8.2: Leave Management
**Tabs → Leave tab**

**Two sub-views based on role**:

**Staff view** (any staff member viewing own leave):
- Leave balance cards: Casual (used/remaining), Sick (used/remaining), Earned (used/remaining)
- Leave history table: Type | From | To | Days | Status | Applied on
- **Apply for leave** button → modal:
  | Field | Type |
  |---|---|
  | Leave type | dropdown: Casual / Sick / Earned / Maternity / Paternity / Compensatory |
  | From date | date picker |
  | To date | date picker |
  | Half day | checkbox (if from = to) |
  | Reason | text area (required) |
  | Handover notes | text area (optional) |
  | Attachments | file upload (medical certificate for sick leave) |

**HOD/Manager view** (approver):
- Pending approvals: Name | Leave type | From | To | Days | Reason | Actions
- Row actions: **Approve** (optional comment) · **Reject** (reason required)
- Leave calendar: Month view showing all staff leaves by colour-coded type
- Overlap warnings: If two faculty from same dept are on leave simultaneously, row is highlighted

**API**: `POST /api/v1/hr/leave/apply`, `GET /api/v1/hr/leave/pending`, `POST /api/v1/hr/leave/{id}/approve`, `POST /api/v1/hr/leave/{id}/reject`, `GET /api/v1/hr/leave/calendar`

---

### Screen 8.3: Payroll
**Tabs → Payroll tab**

**Layout**: Month selector at top + staff payroll table

**Month/Year selector** (dropdown). Shows "Draft" badge until approved, "Finalized" badge after.

**Table columns**: Staff ID | Name | Designation | Basic | HRA | DA | Allowances | Gross | PF | ESI | TDS | Deductions | Net pay | Status

**Actions**:
- **Run payroll** button (for selected month) → calculates all staff salaries based on attendance + leaves; shows preview
- **Approve payroll** button → locks the run for that month; cannot be edited after
- Click any row → staff payslip detail view
- **Download all payslips** (bulk PDF, one per staff)
- **Export bank transfer file** (CSV with: Account no., IFSC, Name, Amount — ready for bulk NEFT upload)

**Payslip detail**: Full formatted payslip — earnings breakdown, deductions breakdown, net pay, YTD totals, digital signature line.

**API**: `GET /api/v1/hr/payroll`, `POST /api/v1/hr/payroll/run`, `POST /api/v1/hr/payroll/approve`, `GET /api/v1/hr/payroll/{staff_id}/{month}/payslip`

---

### Screen 8.4: Performance Reviews
**Tabs → Performance tab**

**Table columns**: Staff | Review period | Type (Annual/Mid-year/Probation) | Reviewer | Status | Overall rating

**Status values**: Draft · Submitted · Acknowledged · Finalized

**Create review** button → modal: Staff (dropdown), Review period (text, e.g. "Q1-2025"), Type (dropdown)

**Click row → Review form page**:
- Criteria ratings table: Each criterion (Quality, Timeliness, Collaboration, Communication, Initiative) | Rating (1–5 stars) | Comments
- Text sections: Strengths (text area), Areas for improvement (text area), Goals for next period (text area)
- Overall rating (auto-calculated average, displayed as number and stars)
- **Submit** button (sends to staff for acknowledgement)
- After submission: staff sees a read-only view + **Acknowledge** button
- **Finalize** button (Reviewer/HR) → locks the review

**API**: `GET /api/v1/hr/performance-reviews`, `POST /api/v1/hr/performance-reviews`, `PUT /api/v1/hr/performance-reviews/{id}`, `POST /api/v1/hr/performance-reviews/{id}/submit`, `POST /api/v1/hr/performance-reviews/{id}/acknowledge`

---

### Screen 8.5: Visiting Faculty Sessions
**Tabs → Visiting Faculty tab**

**Purpose**: Visiting faculty attendance is verified via OTP before billing.

**Table columns**: Faculty name | Subject | Session date | Duration | OTP status | HOD verified | Billed | Amount (₹)

**Workflow per session row** (status steps shown as breadcrumb):
1. **Create session** → auto-generates OTP
2. **OTP sent** → faculty receives OTP
3. **Faculty confirms** → faculty enters OTP (on their device or via staff)
4. **HOD verifies** → HOD approves the session
5. **Billed** → session included in visiting faculty invoice

**Row actions** (context-sensitive per step):
- Generate OTP
- Confirm with OTP (input field)
- HOD Verify
- Cancel session

**Billing summary panel**: Total sessions by faculty, pending billing, total amount (₹).

**API**: `POST /api/v1/hr/visiting-faculty/sessions`, `POST /api/v1/hr/visiting-faculty/sessions/{id}/generate-otp`, `POST /api/v1/hr/visiting-faculty/sessions/{id}/confirm`, `POST /api/v1/hr/visiting-faculty/sessions/{id}/hod-verify`

---

## Part 9 — Student Services Module

### Screen 9.1: Hostel
**Frame**: Hostel Workspace
**Who**: STUDENT_SERVICES_MANAGER

**Tabs**: Hostel | Transport | Library | Grievances

**Hostel tab**:
- **Summary cards**: Total rooms | Occupied | Vacant | Maintenance hold
- **Occupancy grid** (toggle between list and visual floor plan): Rooms shown as grid cards — Room number, Block, Occupied/Vacant badge, student count
- Room detail drawer (click any room): Room number, Block, Capacity, Current occupants (names, roll numbers), Maintenance status
- **Allocate room** button → modal: Student (search dropdown), Room (dropdown of available rooms)
- **Checkout** button per room → records vacate date
- **Raise maintenance** button per room → maintenance request form

**List view** (table): Room # | Block | Capacity | Occupied | Status | Students
- Search and filter by block, status

**API**: `GET /api/v1/student-services/hostel/rooms`, `POST /api/v1/student-services/hostel/allocate`, `POST /api/v1/student-services/hostel/checkout`, `POST /api/v1/student-services/hostel/maintenance`

---

### Screen 9.2: Transport
**Tabs → Transport tab**

**Layout**: Routes table + student assignment panel

**Routes table**: Route name | Start point | End point | Bus # | Driver name | Driver phone | Capacity | Enrolled students

**Add route** button → modal: Route name, Stops (ordered list with + button), Bus number, Driver name, Driver phone, Capacity, Schedule (morning/evening timings per stop)

**Student assignment**: Select route → shows students on this route. **Assign student** button → search dropdown. **Remove** button per student.

**API**: `GET /api/v1/student-services/transport/routes`, `POST /api/v1/student-services/transport/routes`, `POST /api/v1/student-services/transport/assign`

---

### Screen 9.3: Library
**Tabs → Library tab**

**Sub-tabs**: Catalogue | Issued | Overdue | Reservations

**Catalogue sub-tab**:
- Table: ISBN | Title | Author | Category | Copies total | Copies available
- **Add book** button → form: ISBN (auto-fills title/author via ISBN lookup), Title, Author, Category, Publisher, Year, Copies
- Search by title, author, ISBN, category

**Issued sub-tab**:
- Table: Student | Roll # | Book title | ISBN | Issue date | Due date | Fine (₹, 0 if on time)
- **Return book** button per row → calculates fine (if overdue), records return
- Fine = (days overdue) × (fine rate per day from policy)

**Overdue sub-tab**:
- Same as Issued but filtered to overdue only; sorted by days overdue descending
- **Send reminder** bulk action

**Reservations sub-tab**:
- Students who have reserved a book currently out
- Shows queue position; when book is returned, first in queue is notified

**Issue book** button (top of page) → modal: Student (search), Book (search), Due date (auto-calculated from policy: typically 14 days)

**API**: `GET /api/v1/student-services/library/catalogue`, `POST /api/v1/student-services/library/issue`, `POST /api/v1/student-services/library/return/{issue_id}`, `GET /api/v1/student-services/library/overdue`

---

### Screen 9.4: Grievances
**Tabs → Grievances tab**

**Layout**: Table + detail drawer

**Table columns**: Ticket # | Student | Category | Subject | Status | Assigned to | Opened on | Days open (SLABar)

**Status values**: Open · In Progress · Awaiting Info · Resolved · Closed · Escalated

**SLABar**: Turns amber at 3 days, red at 7 days open.

**Filters**: Category, Status, Assigned to, Date range

**Detail drawer**:
- Student info + original grievance text + category
- Attachment previews (if any)
- Conversation thread: staff messages + student replies (chronological)
- **Reply** text area + Send button
- **Assign** dropdown (reassign to another staff member)
- **Escalate** button → escalates to HOD or Registrar with a note
- **Resolve** button → requires resolution note
- **Close** button (after resolved)

**New grievance** button (staff can raise on behalf of a student): Student, Category, Subject, Description.

**API**: `GET /api/v1/student-services/grievances`, `POST /api/v1/student-services/grievances/{id}/reply`, `POST /api/v1/student-services/grievances/{id}/resolve`, `POST /api/v1/student-services/grievances/{id}/escalate`

---

## Part 10 — Communications Module

### Screen 10.1: Compose Announcement
**Frame**: Compose Announcement Workspace
**Who**: COMMUNICATIONS_MANAGER, HOD (limited to own dept), FACULTY (own courses only)

**Layout**: Full compose form (left 55%) + Preview panel (right 45%)

**Form fields**:
| Field | Type | Notes |
|---|---|---|
| Title | text | Required, max 120 chars |
| Body | Rich Text Editor | Required |
| Target audience | Multi-select tree | Groups: All students / By programme / By batch / By dept / All faculty / All staff / Custom list upload |
| Channels | Checkboxes | In-app · Email · SMS · WhatsApp |
| Schedule | date-time picker | Leave empty to send now |
| Priority | toggle: Normal / Urgent | Urgent shows banner in-app |
| Attachments | file upload | Optional, max 10MB |

**Preview panel**: Shows how the announcement will look on each selected channel (tab per channel: In-app card, Email template, SMS preview, WhatsApp bubble).

**Actions**:
- **Send now** button
- **Schedule** button (if schedule date is set)
- **Save draft** button

**Sent announcements table** (below): Title | Sent on | Audience | Delivered | Opened | Status

**API**: `POST /api/v1/communications/announcements`, `GET /api/v1/communications/announcements`

---

### Screen 10.2: Bulk Messaging
**Frame**: Bulk Messaging Workspace
**Who**: COMMUNICATIONS_MANAGER

**Step 1 — Select template**:
- Template picker: shows card per template with name, channel badge, preview snippet
- Or: write a custom message (not using a template)

**Step 2 — Select recipients**:
- Option A: By filter — Programme, Batch, Status (Active / Alumni / Applicant), Category
- Option B: Upload CSV (download template → fill → upload; CSV must have `name` and `phone/email` columns)
- Preview: "X recipients selected"

**Step 3 — Variables**:
- Table of variable placeholders found in template: Variable | Sample value | Source field
- E.g. `{name}` → pulled from student profile, `{due_date}` → pulled from fee structure
- Test send: enter your own phone/email to preview with one recipient's data

**Step 4 — Review & Send**:
- Summary: Template name, Channel, Recipient count, Estimated cost (SMS)
- **Send** button or **Schedule** button

**Delivery report** (after send): Table — Recipient | Status (Sent / Delivered / Failed / Read) | Timestamp; export CSV.

**API**: `POST /api/v1/communications/bulk-messages`, `GET /api/v1/communications/bulk-messages/{id}/delivery-report`

---

### Screen 10.3: Message Templates
**Frame**: Message Templates Workspace
**Who**: COMMUNICATIONS_MANAGER, SUPER_ADMIN

**Table columns**: Template name | Channel | Category | Status | WhatsApp DLT ID

**Status values**: `Active` · `Draft` · `Pending DLT Approval` (WhatsApp only) · `Rejected`

**WhatsApp DLT ID column** (production feature): For WhatsApp templates, shows the DLT-registered template ID. If empty, shows "Pending registration" badge. Templates without a valid DLT ID cannot be used for WhatsApp delivery.

**Create/Edit template drawer**:
| Field | Notes |
|---|---|
| Template name | Internal name |
| Channel | dropdown: Email / SMS / WhatsApp / In-app |
| Category | dropdown: Transactional / Promotional / OTP / Reminder |
| Subject | (Email only) |
| Body | text area with `{variable}` placeholder support; character count for SMS (160 char limit per segment) |
| WhatsApp DLT template ID | shown for WhatsApp channel; enter after Meta/DLT approval |

**API**: `GET /api/v1/communications/templates`, `POST /api/v1/communications/templates`, `PUT /api/v1/communications/templates/{id}`

---

## Part 11 — Reporting Module

### Screen 11.1: Pre-built Dashboards
**Frame**: Pre-built Dashboards Workspace
**Who**: REPORTING_MANAGER, REGISTRAR, FINANCE_MANAGER, HOD (scoped)

**Workspace selector**: Tab pills — Admissions | Academics | Finance | HR

**Global filter bar** (applies to all widgets on the active workspace): Academic year, Campus (if multi-campus), Programme, Semester

**Admissions workspace**:
- Funnel chart: stage-by-stage conversion rates
- Source channel breakdown (pie chart): how applicants found the institution
- Category-wise distribution (stacked bar): General/SC/ST/OBC/EWS/PwD per programme
- Applications over time (line chart: daily/weekly)
- Stat cards: Total applications, Conversion rate, Avg days to offer, Enrollment rate

**Academics workspace**:
- Department-wise attendance % (horizontal bar)
- Pass/fail rate by subject (table + colour coding)
- Subjects with highest failure rate (top 10)
- Attendance trend over weeks (line chart)

**Finance workspace**:
- Fee collection vs target (gauge chart)
- Overdue trend over months (area chart)
- Scholarship utilisation (% of total fee revenue)
- Payment method distribution (pie chart)

**HR workspace**:
- Headcount by department (bar chart)
- Leave utilisation by type (stacked bar)
- Performance rating distribution (histogram)
- Vacancy count by department

**API**: `GET /api/v1/reporting/workspace/{type}?year=&programme=&campus=`

---

### Screen 11.2: Custom Report Builder
**Frame**: Custom Report Builder Workspace
**Who**: REPORTING_MANAGER

**Step-by-step builder (wizard within the page)**:

**Step 1 — Choose module**: Card grid — Admissions, Academics, Finance, HR, Examinations, Student Services

**Step 2 — Select fields**: Two-column layout. Left: available fields (grouped by entity). Right: selected fields (drag to reorder). Checkboxes to add to right column.

**Step 3 — Add filters**: + Filter button → picker: field, operator (equals / contains / greater than / less than / between / is blank), value

**Step 4 — Grouping & Aggregation** (optional): Group by field (dropdown), Aggregate (Count / Sum / Average / Min / Max) on numeric fields

**Step 5 — Preview**: Live preview table showing first 25 rows. "X total rows" shown.

**Actions**:
- **Save as report** button → name + optional description
- **Export now** button → CSV / XLSX / PDF
- **Schedule** button → recurring email (daily/weekly/monthly) + recipient email list

**Saved reports table**: Name | Created by | Last run | Next run | Export button

**API**: `POST /api/v1/reporting/custom`, `GET /api/v1/reporting/custom/saved`, `POST /api/v1/reporting/custom/{id}/run`

---

### Screen 11.3: AI Insights
**Frame**: AI Insights Workspace
**Who**: REPORTING_MANAGER

**Layout**: Large prompt input box at top + response area below

**Prompt input**: Multi-line text area with placeholder "Ask anything about your institution data…" + **Ask** button

**Example prompts** shown as clickable chips:
- "Which programmes have the highest dropout rate this year?"
- "Compare fee collection to last year same period"
- "Show me faculty with more than 3 leave absences this semester"
- "Which students in B.Tech are at risk of detention?"

**Response area**: AI response in a white card — may contain:
- Narrative text answer
- A table (if the answer is data)
- A chart (bar/line/pie, auto-selected by AI)
- A "View full data" link → opens in Report Builder

**History**: Previous queries listed below the input, clickable to restore.

**API**: `POST /api/v1/reporting/ai-insights`

---

## Part 12 — Alumni & Placement Module

### Screen 12.1: Alumni Directory
**Frame**: Alumni Directory Workspace
**Who**: TPO

**Layout**: Table + detail drawer

**Table columns**: Name | Batch year | Programme | Current employer | Designation | Location | Last updated

**Filters**: Batch year, Programme, Employer, Location, Status (Employed / Self-employed / Higher studies / Abroad / Unknown)

**Search**: by name, employer, location

**Row action**: Click → detail drawer showing full profile + contact info

**Add / Edit alumni** button → drawer form: Name, Batch, Programme, Roll #, Current employer, Designation, Location, LinkedIn URL, Phone, Email

**Send message** (select multiple rows) → compose email to selected alumni (bulk, uses email template)

**API**: `GET /api/v1/alumni/directory`, `POST /api/v1/alumni/alumni`, `PUT /api/v1/alumni/alumni/{id}`

---

### Screen 12.2: Placement Drives
**Frame**: Placement Drives Workspace
**Who**: TPO

**Layout**: Table + detail page

**Table columns**: Company | Drive date | Eligible programmes | CTC offered | Role | Status | Placed count

**Status values**: Upcoming · Registration Open · Ongoing · Completed · Cancelled

**Create drive** button → multi-section drawer:
- Company: Name, Industry, Logo upload, JD PDF upload
- Drive details: Date, Venue / Video call link, Rounds (table: Round name, Type, Date)
- Eligibility: Min CGPA, Max active backlogs, Eligible programmes (multi-select), Eligible batches
- Package: CTC (₹ LPA), Role, Location

**Drive detail page** (click row):
- Overview tab: all fields from above
- Registered students tab: Table of students who registered — Name, Roll #, CGPA, Backlogs; **Register more** button
- Results tab: Per student — Round | Cleared? | Final status (Selected / Rejected / No-show); **Mark results** button → inline editing
- Statistics: Placed count, Avg CTC, Highest CTC

**API**: `GET /api/v1/alumni/placement-drives`, `POST /api/v1/alumni/placement-drives`, `POST /api/v1/alumni/placement-drives/{id}/results`

---

### Screen 12.3: TPO Workspace
**Frame**: TPO Workspace Workspace
**Who**: TPO

**Stat cards**: Placement % (current batch) | Average CTC (₹ LPA) | Highest CTC (₹ LPA) | Drives completed

**Charts**:
- Placement % by programme (horizontal bar)
- Company-wise hiring count (bar chart, top 15)
- CTC distribution histogram (current batch)
- Placement trend over past 5 years (line chart)

**Upcoming drives calendar**: Week-view calendar showing drives in the next 30 days.

---

## Part 13 — PhD Module

**Frame**: TPO Workspace Workspace
**Who**: PHD_COORDINATOR, REGISTRAR

**4 tabs**:

### Tab 13.1: Scholars
- Table: Scholar name | Reg # | Department | Supervisor | Current stage | Registration date | Status
- Stages: Coursework · Comprehensive Exam · Synopsis Approved · Thesis Submitted · Viva Scheduled · Awarded
- **Add scholar** button → form: Name, Reg #, Department, Supervisor (dropdown), Research area, Registration date, Funding source
- Click row → scholar profile (all detail tabs)

### Tab 13.2: Supervisors
- Table: Supervisor (faculty) | Department | Designation | Current scholars | Max capacity | Specialisation
- **Set capacity** button per row (max number of PhD scholars per supervisor — policy-controlled)

### Tab 13.3: Progress
- Per scholar: milestone timeline showing completed and upcoming milestones
- **Progress report log**: Date | Type (6-monthly / Annual) | Status (Submitted / Overdue) | Remarks
- **Flag delayed** banner (auto-shown if >6 months since last progress report)
- **Submit progress report** button (for coordinator on behalf of scholar) → form: report period, summary, supervisor remarks, DC meeting date

### Tab 13.4: Viva
- Table: Scholar | Thesis title | Internal examiner | External examiner | Viva date | Venue | Outcome
- **Schedule viva** button → modal: Scholar (dropdown), Date + time, Internal examiner (dropdown of faculty), External examiner (text — may be from another institution), Venue/link
- **Record outcome** button: Passed without corrections / Passed with minor corrections / Major revisions required / Failed

**API**: `GET /api/v1/phd/scholars`, `POST /api/v1/phd/scholars`, `GET /api/v1/phd/progress/{scholar_id}`, `POST /api/v1/phd/viva`, `PUT /api/v1/phd/viva/{id}/outcome`

---

## Part 14 — Regulatory Module

**Frame**: TPO Workspace Workspace
**Who**: COMPLIANCE_OFFICER, REGISTRAR

**3 tabs**:

### Tab 14.1: Compliance Checklist
- Regulatory body selector (pills): NAAC | NBA | UGC | AICTE | State Body
- Checklist table: Requirement # | Description | Category | Status | Evidence file | Last updated | Updated by
- Status values: `Met` (green) · `Partial` (amber) · `Not Met` (red) · `Not Applicable` (grey)
- Row actions: **Upload evidence** (file upload) · **Mark status** (dropdown) · **Add notes**
- Overall compliance score shown at top: X% of requirements met (progress ring chart per body)

### Tab 14.2: Audit Trail
- Full read-only event log of all system actions
- Columns: Timestamp | Actor | Action | Module | Entity | Changes (before → after)
- Filters: Module (multi-select), Actor (search), Action type, Date range
- **Export to CSV** button, **Export to PDF** (formatted for regulatory submission)
- Each row expandable: shows full JSON diff of before/after values

### Tab 14.3: Data Export for Regulators
- Select data category (NAAC / AICTE data return / UGC format)
- Date range
- **Generate export** button → downloads formatted XLSX/CSV matching the regulatory template

**API**: `GET /api/v1/regulatory/compliance-checklist`, `PUT /api/v1/regulatory/compliance-checklist/{id}`, `GET /api/v1/audit/log`, `POST /api/v1/regulatory/export`

---

## Part 15 — Convocation Module

**Frame**: TPO Workspace Workspace
**Who**: REGISTRAR, Convocation Committee

**4 tabs**:

### Tab 15.1: Eligible Students
- Students who have: completed all required credits + cleared all fee dues + no academic holds
- Table: Name | Roll # | Programme | CGPA | Fee clearance | Holds | Eligible?
- **Place hold** button per student (with reason — prevents convocation eligibility)
- **Remove hold** button
- Filters: Programme, Eligibility status

### Tab 15.2: Registration
- Shows eligible students who have been invited to register
- Columns: Name | Status | Gown size (M/L/XL/XXL) | Guest count | Dietary requirement | Registered on
- **Send registration link** button (bulk — emails students the convocation registration form)
- Status: `Invited` · `Registered` · `Opted Out` · `Not Responded`

### Tab 15.3: Ceremony
- **Seating arrangement** section: auto-generate button (sorts by programme → alphabetical within programme)
- Seating table: Seat # | Name | Programme | Row | Column
- **Print admit passes** button (bulk PDF — one per student, includes seat number + QR code)
- **Programme order** section: draggable list of ceremony segments (Procession, National Anthem, Welcome speech, Award of degrees by programme, etc.)

### Tab 15.4: Degrees
- Table: Name | Roll # | Programme | Certificate # | Printed? | Dispatched? | Collected? | Tracking #
- **Generate certificates** button (bulk) → PDF generation with digital signature
- Per row: **Print** · **Mark dispatched** (with courier tracking #) · **Mark collected**
- **Duplicate certificate request** workflow: student requests → staff verifies identity → generates duplicate → records fee payment

**API**: `GET /api/v1/convocation/eligible`, `GET /api/v1/convocation/registrations`, `POST /api/v1/convocation/seating/generate`, `POST /api/v1/convocation/degrees/generate`, `PUT /api/v1/convocation/degrees/{id}/dispatch`

---

## Part 16 — Workflows & Approvals

**Frame**: TPO Workspace Workspace
**Who**: All staff (content filtered by role)

**2 tabs**:

### Tab 16.1: My Approvals
- Table: Request title | Module | Requested by | Raised on | Deadline | Days left (SLABar) | Actions
- **Approve** button → optional comment field → confirm
- **Reject** button → mandatory reason field → confirm
- **Delegate** button (if user is going on leave) → select delegate + validity period
- Filter: Module, Status (Pending / Approved / Rejected), Date range

### Tab 16.2: History
- All completed approvals the user was part of: Title | Outcome | Date | My decision | Comment

**API**: `GET /api/v1/approvals/pending`, `POST /api/v1/approvals/{id}/approve`, `POST /api/v1/approvals/{id}/reject`, `POST /api/v1/approvals/delegate`

---

## Part 17 — Process Engine

**Frame**: TPO Workspace Workspace
**Who**: SUPER_ADMIN, REGISTRAR

**2 tabs**:

### Tab 17.1: Process Definitions
- Table: Process name | Module | Steps count | Active instances | Created by | Status
- **Create process** button → step builder page (see below)
- Edit / Archive / Clone per row

**Step Builder Page**:
- Process name + description at top
- Visual step flow: steps shown as connected boxes; drag to reorder; click + button to add a step
- Each step has a type selector and a configuration panel (right side):

| Step type | Configuration fields |
|---|---|
| **Form** | Field list builder — per field: name, label, type (text/number/date/select/checkbox/textarea), required flag, validation rules (min/max length, pattern) |
| **Approval** | Reviewer: role or specific users; Quorum (how many must approve); Timeout (hours); On timeout: Escalate / Auto-approve / Auto-reject |
| **Condition** | Expression builder (visual: field + operator + value); Pass label; Fail label |
| **Notification** | Template picker; Recipient (from context field); Channel |
| **AI Evaluation** | Prompt template (with `${context}` placeholder); Output field name; Pass condition |
| **Auto Action** | Action picker from registered list; Parameters |

- Step routing: each step has "On pass → [next step]" and "On fail → [next step]" dropdowns
- **Save definition** button

### Tab 17.2: Active Instances
- Table: Process name | Entity type | Entity ID | Launched on | Current step | Status
- Status values: Running · Completed · Failed · Cancelled
- Click row → instance detail page: step-by-step progress timeline; if current step is a Form → shows the form inline; if current step is Approval → shows Approve/Reject buttons

**API**: `GET /api/v1/processes`, `POST /api/v1/processes`, `GET /api/v1/processes/instances`, `POST /api/v1/processes/instances/{id}/steps/{step_id}/submit`

---

## Part 18 — Consent Management

**Frame**: TPO Workspace Workspace
**Who**: COMPLIANCE_OFFICER, REGISTRAR

**2 tabs**:

### Tab 18.1: Consent Policies
- Table: Policy name | Version | Purpose summary | Required? | Status | Effective from
- **Create policy** button → drawer:
  - Name, Version
  - Purpose (short, one-line)
  - Full consent text (Rich Text Editor — this is what students read and agree to)
  - Required or Optional toggle
  - Effective from date
- **Publish** button per draft policy → triggers consent prompts for all active students/applicants
- View consent text (click row)

### Tab 18.2: Student Consent Status
- Filters: Policy, Consent status (Consented / Not Consented / Revoked), Date range, Programme
- Table: Student | Policy name | Version | Status | Date | IP address | Revoked?
- **Export CSV** button
- Row action: **View consent record** → full audit entry (timestamp, IP, user agent)

**API**: `GET /api/v1/consent/policies`, `POST /api/v1/consent/policies`, `POST /api/v1/consent/policies/{id}/publish`, `GET /api/v1/consent/status`

---

## Part 19 — Admin Console

### Screen 19.1: Institution Onboarding Wizard
**Frame**: Institution Onboarding Wizard Workspace
**Who**: SUPER_ADMIN
**Access**: One-time setup. Once completed, the wizard is replaced by a "Re-configure" link.

**6 steps** shown in a horizontal step bar at the top.

**Step 1 — Hierarchy (Schools & Departments)**:
- List of schools; each school is an expandable card
- Per school: name input, auto-generated code (editable), **Add department** button
- Per department: name input, auto-generated code (editable), delete button
- **Add school** button at the bottom
- Pre-populated with one sample school for first-time users

**Step 2 — Module Managers**:
- Dynamic list of manager cards (collapsible)
- **Add manager** button creates a new card
- Per manager card: Title (free text e.g. "Admissions Head"), Name, Email, Temporary password (auto-generated, with show/hide), Permissions (PermissionPicker component)
- Delete button per card

**Step 3 — Module Scope Matrix**:
- Grid: 9 predefined modules (M1 Admissions through M9 Alumni) as rows × Schools from Step 1 as columns
- Each cell: checkbox (which module oversees which school)
- Row shortcuts: "All" / "None" buttons per module
- Second matrix below: Cross-grants — which modules can read data from other modules (M× row × M× column)

**Step 4 — HOD Mapping**:
- Auto-populated from departments in Step 1
- Per department: Name input, Email input, Temporary password (auto-generated, show/hide)
- Skip toggle per HOD (if not assigning an HOD yet)

**Step 5 — Policy Defaults**:
- 6 policy inputs with defaults:
  - Minimum attendance % (default: 75)
  - Minimum eligibility marks (default: 55)
  - Offer letter validity — days (default: 30)
  - Fee grace period — days (default: 7)
  - Late fee penalty — % per month (default: 2)
  - Minimum passing marks — % (default: 40)
- All editable; units shown next to each (%, days, %/month)

**Step 6 — Provision & Launch**:
- Summary panel: Schools created, Departments, Managers, HODs, Policies
- **Launch** button → triggers provisioning
- Live log panel: streaming list of steps with ✓ (complete) or ✗ (error) per step
- On completion: success screen with institution ID + admin credentials summary + "Go to workspace" button

**API**: `POST /api/v1/orgs/schools`, `POST /api/v1/orgs/departments`, `POST /api/v1/users/bulk`, `POST /api/v1/roles/delegate`, `POST /api/v1/policies/bulk`

---

### Screen 19.2: Policy Studio
**Frame**: Policy Studio Workspace
**Who**: SUPER_ADMIN, REGISTRAR (limited)

**Layout**: Left sidebar (policy category tree, 260px) + Right content area

**Policy category tree**:
- Academics
- Admissions
- Finance
- HR
- Examinations
- (expandable sub-items under each)

**Right content area — Policy editor**:
- Policy key (system identifier, read-only, monospace)
- Policy label (human-readable)
- Current value + unit
- Effective from: immediately / choose date (date picker)
- **Save** button

**Change history** section below editor: table of past values — Old value → New value | Changed by | Changed on | Effective from

**Actions**:
- **Restore previous** button (restores to the selected historical value)
- **Bulk import** button → upload CSV with columns: key, value, effective_from

**API**: `GET /api/v1/policies`, `PUT /api/v1/policies/{key}`, `GET /api/v1/policies/{key}/history`, `POST /api/v1/policies/bulk`

---

### Screen 19.3: Team Management
**Frame**: Team Management Workspace
**Who**: SUPER_ADMIN

**3 tabs**:

**Users tab**:
- Table: Name | Email | Role | Department | Status | Last login
- **Invite user** button → modal: Name, Email, Role (dropdown), Department (dropdown)
- Row actions: **Edit role**, **Deactivate**, **Reset password**

**Roles tab**:
- Table: Role name | Description | Permissions count | Users with this role
- Click row → role detail (permission list grouped by module; read-only for system roles)
- **Create custom role** button → name + description + PermissionPicker component
- **Edit** / **Delete** for custom roles only (system roles cannot be deleted)

**Delegations tab**:
- Active delegations: From staff → To staff | Modules | Permissions granted | Valid until | Status
- **Create delegation** button → modal:
  | Field | Notes |
  |---|---|
  | From (delegator) | staff search dropdown |
  | To (delegate) | staff search dropdown |
  | Modules | multi-select |
  | Permissions | PermissionPicker (subset of delegator's own permissions) |
  | Valid from / to | date range |
  | Reason | text (optional) |
- **Revoke** button on active delegations

**API**: `GET /api/v1/users`, `POST /api/v1/users/invite`, `GET /api/v1/roles`, `POST /api/v1/roles`, `GET /api/v1/roles/delegations`, `POST /api/v1/roles/delegate`, `DELETE /api/v1/roles/delegations/{id}`

---

### Screen 19.4: Feature Flags
**Frame**: Feature Flags Workspace
**Who**: SUPER_ADMIN

**Purpose**: Toggle experimental or institutional features per campus without code deployment.

**Layout**: Table with toggle switches

**Table columns**: Feature key | Description | Module | Status (On/Off toggle) | Enabled since | Last changed by

**Feature flag categories** (filter tabs): All | Integrations | AI Features | Regional | Experimental

Examples:
- `admissions.digilocker_enabled` — "Enable DigiLocker document verification"
- `finance.einvoice_enabled` — "Generate GST e-invoices with IRN"
- `examinations.question_paper_vault` — "Encrypt exam papers via Vault"
- `finance.tally_export` — "Show Tally XML export option"
- `attendance.offline_mode` — "Enable offline PWA attendance marking"

**Actions**: Toggle switch per row (with confirmation dialog for production flags), changelog view per flag.

**API**: `GET /api/v1/feature-flags`, `PUT /api/v1/feature-flags/{key}`

---

### Screen 19.5: Settings
**Frame**: Settings Workspace
**Who**: SUPER_ADMIN

**6 sections** (left sidebar nav):

**General**:
- Institution name, Short name, Logo upload
- Primary address (multi-line)
- Timezone (dropdown)
- Academic year start month (dropdown)
- Date format preference (DD/MM/YYYY | MM/DD/YYYY | YYYY-MM-DD)

**Communications (WhatsApp / SMS)**:
- WhatsApp Business phone number
- WhatsApp access token (masked, reveal button)
- Webhook verify token
- Default SMS sender ID
- MSG91 auth key (masked)
- **Test WhatsApp** button → sends a test message to a phone number you enter

**Email**:
- SMTP host, port
- SMTP username, password (masked)
- From name, From email, Reply-to email
- Use TLS toggle
- **Send test email** button → sends to your logged-in email

**Payment Gateway**:
- Provider (Razorpay / PayU)
- API key (masked, reveal)
- Webhook secret (masked)
- **Test connection** button → verifies credentials with gateway

**External Integrations** (status cards for each):
- DigiLocker: Connected / Not configured (Configure button)
- NTA Score API: Connected / Not configured
- LMS (Moodle): Connected / Not configured
- Email provisioning (Google/Microsoft): Connected / Not configured
- Each card: last connection test timestamp, Configure button → opens credential form for that integration

**Security**:
- Password policy (min length, require special chars, expiry days)
- MFA required for roles (multi-select)
- Session timeout (minutes)
- Max failed login attempts before lockout

**API**: `GET /api/v1/admin/settings`, `PUT /api/v1/admin/settings`, `POST /api/v1/admin/settings/test-email`, `POST /api/v1/admin/settings/test-whatsapp`

---

### Screen 19.6: Audit Log Viewer
**Frame**: Audit Log Viewer Workspace
**Who**: SUPER_ADMIN, COMPLIANCE_OFFICER

**Full-page read-only log.**

**Filters**: Module (multi-select), Actor (staff search), Action type (multi-select: CREATE / UPDATE / DELETE / LOGIN / APPROVE / REJECT / EXPORT), Entity type, Date range

**Table columns**: Timestamp | Actor | Action | Module | Entity type | Entity ID | Summary | IP address

**Row expand**: Shows full before/after JSON diff in a side-by-side panel.

**Export**: CSV / PDF (formatted for regulatory use).

**API**: `GET /api/v1/audit/log`

---

## Part 20 — Student Portal

The portal has its own layout: clean white background, institution logo at top, simple bottom navigation on mobile. No Work Panel, no AI Copilot rail. Calm, approachable design suitable for prospective students.

### Screen 20.1: Portal Home
**Frame**: Portal Home Workspace
**Who**: Applicants (pre-admission), STUDENT (post-enrollment)

**For applicants**:
- Welcome banner with name
- Application status card: stage badge (large, colour-coded) + "Next action required" CTA (if any)
- Quick links: Continue application, Check status, Download offer letter, Contact admissions
- Recent notifications from institution

**For enrolled students**:
- Welcome banner with name + programme + roll number
- Today's schedule card (next 2 classes)
- Quick links: View timetable, Check attendance, Pay fee, Download hall ticket, View results, Raise grievance

---

### Screen 20.2: Application Wizard
**Frame**: Application Wizard Workspace
**Who**: Applicants

**Layout**: Left sidebar showing step progress (numbered list, completed steps show checkmark), right main content area. Top progress bar.

**Step navigation**: Back / Save draft / Next buttons. Steps are non-linear — user can jump to any step via sidebar.

**10 steps**:

**Step 1 — Personal Details**:
| Field | Type | Notes |
|---|---|---|
| First name | text | Required |
| Last name | text | Required |
| Date of birth | date picker | Required |
| Gender | dropdown: Male / Female / Non-binary / Prefer not to say | Required |
| Nationality | text | Required, default: Indian |
| Category | dropdown: General / SC / ST / OBC-NCL / EWS / PwD | Required |
| Aadhaar number | text | Optional, 12 digits |
| Disability details | text area | Shows only if Category = PwD |

**Step 2 — Contact & Address**:
| Field | Type |
|---|---|
| Permanent address (line 1, line 2) | text |
| City | text |
| State | dropdown |
| Pincode | text (6 digits) |
| Country | dropdown, default India |
| Correspondence address | same fields + "Same as permanent" checkbox |
| Emergency contact name | text |
| Emergency contact relation | dropdown |
| Emergency contact phone | text |

**Step 3 — Academic — 10th Standard**:
| Field | Type |
|---|---|
| Board | dropdown: CBSE / ICSE / State board / Other |
| School name | text |
| Year of passing | number (4 digit) |
| Total marks | number |
| Marks obtained | number |
| Percentage | number (auto-calculated if marks entered) |

**Step 4 — Academic — 12th Standard**:
Same fields as Step 3, plus:
| Field | Type |
|---|---|
| Subjects (comma-separated) | text |
| Status | dropdown: Passed / Appearing |

**Step 5 — Entrance Exam Scores**:
| Field | Type |
|---|---|
| Exam name | dropdown: JEE Mains / NEET / CAT / MAT / XAT / SAT / State CET / Other |
| Roll number | text |
| Score or percentile | number |
| Rank | number |
| Year of exam | number |

**Production feature — NTA Auto-import button**: If the institution has NTA integration enabled, a "Import from NTA" button appears. Clicking opens a modal: enter JEE/NEET roll number → fetches and pre-fills scores from NTA API.

Multiple entrance exam entries allowed (+ Add another exam button). Each saved entry shown as a summary card with edit/delete.

**Step 6 — Programme Preference**:
| Field | Type |
|---|---|
| Programme | dropdown (institution's active programmes) |
| Specialisation | text (optional) |
| Intake batch | text (e.g. "July 2025") |
| Study mode | dropdown: Full-time / Part-time / Distance |
| Hostel required | Yes / No |
| Scholarship consideration | Yes / No |

Up to 3 programme preferences (+ Add preference button). Preferences are numbered and can be reordered.

**Step 7 — Documents**:
Required documents based on eligibility rules (shown as a checklist):
- Class 10 marksheet
- Class 12 marksheet
- Passport-size photograph
- Government ID proof (Aadhaar / Passport / Driving licence)
- Category certificate (if SC/ST/OBC/EWS/PwD)

Per document: FileUploader component, supported formats shown (PDF/JPG/PNG, max 2MB), status badge.

**Production feature — DigiLocker verify button**: If DigiLocker is enabled by the institution, a "Verify via DigiLocker" button appears next to eligible documents (Aadhaar, marksheets). Clicking redirects to DigiLocker OAuth consent → on return, document is auto-uploaded and marked "DigiLocker verified" (green badge).

**Step 8 — Other Information**:
| Field | Type |
|---|---|
| How did you hear about us? | dropdown: Google / Social media / Friend / Consultant / Fair / Other |
| Work experience (months) | number (optional) |
| Any disability or special needs? | text area (optional) |

**Step 9 — Review & Declaration**:
- Full summary of all entered data (collapsible sections per step)
- "Edit" link per section → navigates back to that step
- Checkbox: "I confirm that all information provided is accurate and complete."
- Digital signature field: "Type your full name as your digital signature"
- **Submit Application** button

**Step 10 — Payment**:
- Application fee breakdown: Application processing fee ₹1,000 (or institution's configured amount)
- Payment button: "Pay ₹X via [gateway name]" → redirects to payment gateway
- After successful payment: success screen with Application ID prominently displayed, email confirmation note.

**Draft auto-save**: Each step saves on Next click. User can return later and resume from where they left off (stored against their account, not just localStorage).

**API**: `POST /api/v1/admissions/applications/{id}/start`, `PATCH /api/v1/admissions/applications/{id}/personal`, `PATCH /api/v1/admissions/applications/{id}/address`, `POST /api/v1/admissions/applications/{id}/qualifications`, `POST /api/v1/admissions/applications/{id}/entrance-scores`, `PUT /api/v1/admissions/applications/{id}/preferences`, `POST /api/v1/admissions/documents/upload`, `POST /api/v1/admissions/applications/{id}/declaration`, `POST /api/v1/admissions/applications/{id}/submit`, `POST /api/v1/admissions/applications/fee`

---

### Screen 20.3: Application Status
**Frame**: Application Status Workspace
**Who**: Applicants

**Layout**: Stage timeline (left, sticky) + Status detail (right)

**Stage timeline**: Vertical list of all 10 stages. Each stage has: icon (circle), stage name, date completed (if done), status indicator (✓ complete / ● current / ○ upcoming).

**Status detail panel**:
- Current stage name (large heading) + description of what is happening
- Estimated next action date (if available)
- **Action required banner** (amber, full-width) if applicant must do something: e.g. "Upload revised marksheet by 15 March"
- Document status list: each required document + its current review status
- Offer details (if offer has been generated)
- Contact: "Have a question? Message your counsellor" button

**API**: `GET /api/v1/admissions/applicants/{id}`, `GET /api/v1/admissions/documents/{applicant_id}`

---

### Screen 20.4: Offer Letter
**Frame**: Offer Letter Workspace
**Who**: Applicants with a generated offer

**Layout**: Offer letter preview (left, 60%) + Actions panel (right, 40%)

**Offer letter preview**: Formatted like an official letter — institution letterhead, applicant name, programme, campus, intake batch, tuition fee, scholarship (if any), net fee, list of conditions, validity date.

**Actions panel**:
- Offer validity countdown: "Offer valid for X more days" (red when ≤3 days)
- **Accept offer** button (primary, green) → confirmation modal: "By accepting, you agree to the terms and conditions. A seat deposit of ₹X will be charged." → Confirm → redirects to payment
- **Decline offer** button (secondary, outlined) → modal: reason (dropdown + optional text) → confirm
- **Download PDF** button

**After acceptance**: Actions panel changes to "Offer accepted ✓" with next steps: "Pay seat deposit to confirm your seat" button.

**API**: `GET /api/v1/admissions/offers/{applicant_id}`, `POST /api/v1/admissions/offers/{id}/accept`, `POST /api/v1/admissions/offers/{id}/decline`

---

### Screen 20.5: Enrolled Student Home
**Frame**: Enrolled Student Home Workspace
**Who**: STUDENT (enrolled)

**This is the post-admission portal home — different from the applicant home.**

**Layout**: Workspace-style with cards

**Cards**:
- Today's classes (timetable snippet: time + subject + room for today's remaining classes)
- Attendance summary: % overall + % per subject (mini table)
- Fee dues: next due amount + due date + Pay Now button
- Upcoming exams (next 7 days): exam name, date, venue
- Recent announcements (last 3)

**Quick actions**: View full timetable | Download hall ticket | View results | Apply leave | Raise grievance | View profile

---

### Screen 20.6: Fee Payment Portal
**Frame**: Fee Payment Portal Workspace
**Who**: STUDENT

**Layout**: Two panels — Fee summary (left) + Payment history (right)

**Fee summary panel**:
- Pending invoices table: Invoice # | Description | Amount (₹) | Due date | Status
- Select invoice(s) to pay (checkbox per row)
- Total selected: ₹X
- **Pay now** button → redirects to payment gateway

**Payment history panel**:
- Table: Date | Description | Amount (₹) | Method | Reference # | Status | Receipt
- **Download receipt** button per row → PDF receipt with e-invoice QR if applicable

**API**: `GET /api/v1/finance/invoices?student_id={id}`, `POST /api/v1/finance/payments/initiate`, `GET /api/v1/finance/receipts/{payment_id}`

---

### Screen 20.7: Profile & Document Vault
**Frame**: Profile & Document Vault Workspace
**Who**: All portal users

**2 tabs**: My Profile | Documents

**My Profile tab**:
- View personal details (read-only for most; editable: phone, address, emergency contact)
- **Edit** button → inline editing of editable fields
- **Change password** button

**Documents tab**:
- All documents uploaded by the student or verified via DigiLocker
- Table: Document type | Uploaded on | Source | Verification status | Actions
- **Upload new document** button
- **Download** button per document
- DigiLocker-verified documents show green badge; manually uploaded show grey badge

**API**: `GET /api/v1/students/{id}/profile`, `PUT /api/v1/students/{id}/profile`, `GET /api/v1/admissions/documents/{applicant_id}`, `POST /api/v1/admissions/documents/upload`

---

## Part 21 — Guardian Portal

**Who**: PARENT (linked to one or more students)
**Login**: Via `/login` using guardian credentials OR via a magic link sent to registered guardian phone/email.

### Screen 21.1: Guardian Home
**Frame**: Guardian Home Workspace

**Layout**: Simple card grid

**Linked students**: One card per linked student — student name, photo/initials, programme, roll number, current status (Enrolled / Applicant)

**Quick stats per student**:
- Attendance % (colour-coded)
- Next fee due (₹ + date)
- Unread messages from institution (count)

**Click any student card** → opens frame that student's detail pages (21.2–21.4)

**API**: `GET /api/v1/guardian/students`

---

### Screen 21.2: Student Attendance View
**Frame**: Student Attendance View Workspace

**Layout**: Summary cards + subject-wise breakdown

**Summary cards**: Overall attendance % (colour-coded), Total classes conducted, Total classes attended, Absences

**Subject-wise table**: Subject | Conducted | Present | Absent | % | Status
Status: OK (≥75%) / Warning (60–74%) / At Risk (<60%)

**Attendance calendar**: Mini month-view heatmap — green = present, red = absent, grey = no class.

**Note**: Read-only view. Guardian cannot modify attendance.

**API**: `GET /api/v1/guardian/students/{id}/attendance`

---

### Screen 21.3: Fee Dues & Payment History
**Frame**: Fee Dues & Payment History Workspace

**Layout**: Two sections

**Pending dues section**:
- Table: Invoice # | Description | Amount (₹) | Due date | Days overdue (if applicable)
- **Pay now** button → redirects to payment portal (logs in as student account context)

**Payment history section**:
- Table: Date | Description | Amount (₹) | Method | Reference # | Receipt
- **Download receipt** per row

**Note**: Guardian sees fee information only; cannot change fee structures.

**API**: `GET /api/v1/guardian/students/{id}/fees`

---

### Screen 21.4: Notifications Feed
**Frame**: Notifications Feed Workspace

**Layout**: Chronological notification list (newest first)

**Each notification**: Icon by type (exam, fee, attendance, announcement) + title + description + timestamp + Read/Unread indicator

**Filters**: Type (All / Exam / Fee / Attendance / General)

**API**: `GET /api/v1/guardian/students/{id}/notifications`

---

### Screen 21.5: Contact Counsellor
**Frame**: Contact Counsellor Workspace

**Layout**: Simple form

**Fields**:
| Field | Notes |
|---|---|
| Student | dropdown (linked students) |
| Subject | text, required |
| Message | text area, required |
| Preferred callback time | text, optional |

**Submit** button → sends to the counsellor assigned to the selected student.

**Enquiry history**: table of past enquiries — subject, sent on, response (if any).

**API**: `POST /api/v1/guardian/enquiry`, `GET /api/v1/guardian/enquiries`

---

## Part 22 — Production-Only Screens

These screens are absent from the pilot but required for full production deployment.

### Screen 22.1: Language Switcher
**Location**: User avatar dropdown in the header (all surfaces)

**Language options**: English / हिंदी / ಕನ್ನಡ / मराठी / தமிழ்

**Behaviour**: Selecting a language immediately re-renders all UI strings in that language. Preference is saved to the user's profile (persists across sessions). Number formatting (dates, currency) also adapts to locale. No page reload required.

---

### Screen 22.2: MFA Trusted Devices
**Frame**: MFA Trusted Devices Workspace

After completing MFA verification, user is shown:
- "Trust this device for 30 days?" checkbox
- If checked, this device skips MFA for 30 days

**Trusted devices management** (on Security settings page):
- Table: Device name (browser + OS) | Last used | Added on | Actions
- **Revoke** button per device
- **Revoke all devices** button

**API**: `GET /api/v1/auth/trusted-devices`, `DELETE /api/v1/auth/trusted-devices/{id}`, `DELETE /api/v1/auth/trusted-devices`

---

### Screen 22.3: Offline Sync Status (PWA — Attendance Marking)
**Location**: Banner at the top of Screen 5.3 (Attendance Marking)

**Online state**: Green dot + "Online — last synced [time]"
**Offline state**: Amber banner — "You are offline. X session(s) saved locally. They will sync automatically when you reconnect."
**Sync in progress**: Spinner + "Syncing…"
**Sync error**: Red banner — "Sync failed for 1 session. Tap to retry." with retry button.

**Sync log** (accessible via info icon): table of locally cached sessions — subject, date, student count, sync status.

---

### Screen 22.4: e-Invoice with QR (Finance — Invoice Detail)
**Location**: Within Screen 7.2 (Invoice detail page), production feature

**When e-invoice is active**: An "e-Invoice" section appears at the bottom of the invoice:
- **IRN**: monospace string (64 chars)
- **Acknowledgement number**
- **Acknowledgement date**
- **QR code image** (large, scannable) — encodes the IRN + invoice summary for GST verification
- **Download e-Invoice PDF** button — includes the QR code and all IRN details per GST norms

**When e-invoice is not yet generated**: A "Generate IRN" button (FINANCE_MANAGER only). Disabled state with tooltip if invoice amount is below the e-invoice threshold.

---

### Screen 22.5: Duplicate Student Merge
**Frame**: Duplicate Student Merge Workspace
**Who**: REGISTRAR

**Purpose**: The system automatically flags possible duplicate student records (same phone, same Aadhaar, or very similar name + DOB). Staff reviews and merges.

**Layout**: Table of flagged pairs

**Table columns**: Primary record | Duplicate candidate | Similarity score | Match fields | Status | Flagged on

**Similarity score**: colour-coded percentage.

**Row action**: Click → Merge Review page

**Merge Review page**:
- Side-by-side comparison: all fields of both records shown in parallel columns
- Differences highlighted in amber
- Per field: radio button to select which record's value to keep (or manually enter a merged value)
- **Confirm merge** button → confirmation modal warning this is irreversible; requires typing "MERGE" to confirm
- **Mark as false positive** button → dismisses the flag without merging

**API**: `GET /api/v1/admissions/duplicates`, `POST /api/v1/students/merge/initiate`, `POST /api/v1/students/merge/execute`

---

## Part 23 — Complete Route Map

| Path | Screen | Roles |
|---|---|---|
| `/login` | Login | All unauthenticated |
| `/forgot-password` | Forgot Password | All |
| `/reset-password` | Reset Password | All |
| `/mfa/enroll` | MFA Enroll | MFA-required staff |
| `/app/workspace` | Work Panel home — canvas shows role dashboard (2.8) | All staff |
| `/app/admissions` | Admissions Pipeline | ADMISSIONS_COORDINATOR, REGISTRAR |
| `/app/admissions/leads` | Lead CRM | ADMISSIONS_COORDINATOR |
| `/app/admissions/documents` | Document Queue | Doc officer, REGISTRAR |
| `/app/admissions/merit` | Merit List | REGISTRAR |
| `/app/admissions/seats` | Seat Matrix | REGISTRAR |
| `/app/admissions/reporting-gate` | Reporting Gate | ADMISSIONS_COORDINATOR |
| `/app/admissions/readmissions` | Re-admissions | REGISTRAR |
| `/app/admissions/identity-review` | Identity Match Review | ADMISSIONS_COORDINATOR, REGISTRAR |
| `/app/admissions/access-lift` | Access Lift Panel | REGISTRAR |
| `/app/admissions/duplicates` | Duplicate Merge | REGISTRAR |
| `/app/academics` | Programmes & Courses | ACADEMICS_MANAGER, HOD, FACULTY |
| `/app/academics/timetable` | Timetable | ACADEMICS_MANAGER, HOD |
| `/app/academics/attendance/mark` | Attendance Marking (PWA) | FACULTY |
| `/app/academics/attendance/report` | Attendance Report | HOD, REGISTRAR |
| `/app/academics/obe` | OBE / CO-PO Mapping | FACULTY, ACADEMICS_MANAGER |
| `/app/examinations` | Exam Schedule | EXAM_CONTROLLER |
| `/app/examinations/hall-tickets` | Hall Tickets | EXAM_CONTROLLER |
| `/app/examinations/results` | Results Entry | FACULTY, EXAM_CONTROLLER |
| `/app/examinations/reevaluation` | Re-evaluation Queue | EXAM_CONTROLLER |
| `/app/finance` | Finance (tabs) | FINANCE_MANAGER |
| `/app/hr` | HR (tabs) | HR_MANAGER |
| `/app/student-services` | Student Services (tabs) | STUDENT_SERVICES_MANAGER |
| `/app/communications` | Compose Announcement | COMMUNICATIONS_MANAGER, HOD, FACULTY |
| `/app/communications/bulk` | Bulk Messaging | COMMUNICATIONS_MANAGER |
| `/app/communications/templates` | Message Templates | COMMUNICATIONS_MANAGER |
| `/app/reports` | Pre-built Dashboards | REPORTING_MANAGER + scoped |
| `/app/reports/custom` | Custom Report Builder | REPORTING_MANAGER |
| `/app/reports/ai` | AI Insights | REPORTING_MANAGER |
| `/app/alumni` | Alumni Directory | TPO |
| `/app/alumni/drives` | Placement Drives | TPO |
| `/app/alumni/stats` | TPO Workspace | TPO |
| `/app/phd` | PhD Module (tabs) | PHD_COORDINATOR, REGISTRAR |
| `/app/regulatory` | Regulatory (tabs) | COMPLIANCE_OFFICER, REGISTRAR |
| `/app/convocation` | Convocation (tabs) | REGISTRAR |
| `/app/workflows` | Approvals | All staff |
| `/app/process-engine` | Process Engine | SUPER_ADMIN, REGISTRAR |
| `/app/consent` | Consent Management | COMPLIANCE_OFFICER, REGISTRAR |
| `/admin/onboarding` | Onboarding Wizard (6 steps) | SUPER_ADMIN |
| `/admin/policies` | Policy Studio | SUPER_ADMIN, REGISTRAR |
| `/admin/team` | Team Management | SUPER_ADMIN |
| `/admin/feature-flags` | Feature Flags | SUPER_ADMIN |
| `/admin/settings` | Settings | SUPER_ADMIN |
| `/admin/audit` | Audit Log | SUPER_ADMIN, COMPLIANCE_OFFICER |
| `/portal` | Portal Home | Applicants, STUDENT |
| `/portal/apply` | Application Wizard (10 steps) | Applicants |
| `/portal/status` | Application Status | Applicants |
| `/portal/offer` | Offer Letter | Applicants |
| `/portal/home` | Enrolled Student Home | STUDENT |
| `/portal/fees` | Fee Payment Portal | STUDENT |
| `/portal/profile` | Profile & Document Vault | All portal users |
| `/portal/guardian` | Guardian Home | PARENT |
| `/portal/guardian/students/:id/attendance` | Student Attendance View | PARENT |
| `/portal/guardian/students/:id/fees` | Fee Dues & Payment | PARENT |
| `/portal/guardian/students/:id/notifications` | Notifications Feed | PARENT |
| `/portal/guardian/contact` | Contact Counsellor | PARENT |

---

## Part 24 — Common UI States

Every data-fetching screen must handle four states consistently. Design these as system-level patterns — not screen-by-screen custom designs.

### 24.1 Loading State

**Rule**: Never show a blank page or spinner in the centre of the content area. Use **skeleton screens** — placeholder shapes matching the exact layout of the loaded content.

**Skeleton patterns by component**:

| Component | Skeleton description |
|---|---|
| **StatCard** | Rounded rect (full card size), pulsing grey |
| **DataTable** | Header row (full width, short height) + 8 placeholder rows (alternating widths per cell to look realistic) |
| **Kanban pipeline** | 7 column outlines, each with 3–4 placeholder cards |
| **Detail drawer** | Header block + 3 section blocks with label-value skeletons |
| **Chart / dashboard** | Card outline with a short horizontal rectangle where the chart title would be, tall rectangle where the chart would be |
| **Form** | Label-input pairs stacked, each label is a short rectangle and each input is a full-width taller rectangle |
| **Timeline** | Vertical line with 5 circle-and-text pairs |

**Animation**: CSS pulse animation (opacity cycles 0.4→0.8→0.4, 1.5s loop). Do not use shimmer unless the design system explicitly calls for it — pulse is subtler and less distracting.

**Duration guard**: If loading takes more than 3 seconds, show a "Taking longer than expected…" note below the skeleton. At 10 seconds, show an error state with a retry option.

---

### 24.2 Empty State

**Rule**: Every empty state must have three elements: an illustration or icon, a message, and (where relevant) a primary action.

**Empty state content by context**:

| Screen / context | Icon | Message | Action |
|---|---|---|---|
| Admissions pipeline — no applicants | Funnel icon | "No applications yet for this cycle." | "Set up seat matrix" |
| Document queue — nothing to review | Checkmark circle | "All documents reviewed. Queue is clear." | None |
| Lead CRM — no leads | Magnifying glass | "No leads found. Add your first lead or import from CSV." | "Add lead" button |
| Notifications — none | Bell with Z | "You're all caught up." | None |
| Approvals queue — none | Checkmark | "No pending approvals." | None |
| Search with no results | Search icon | "No results for '[query]'. Try different keywords." | Clear search link |
| Table with active filters that return nothing | Filter icon | "No records match these filters." | "Clear filters" link |
| Report builder — no saved reports | Chart icon | "No saved reports yet. Build your first report." | "Create report" button |
| Grievances — no open tickets | Smiley face | "No open grievances." | None |
| Alumni directory — no alumni | People icon | "No alumni records yet. Import from CSV to get started." | "Import CSV" button |

**Empty state layout**: Centred vertically and horizontally in the content area. Icon 64–80px, message in body text, action is a secondary button below the message. Never use primary blue button for empty-state actions.

---

### 24.3 Error State

**Three error tiers**:

**Tier 1 — Inline field validation error** (form inputs):
- Red border on the input
- Red error message directly below the field, 11px, left-aligned
- Shown on blur (not on every keystroke)
- Examples: "Email address is required.", "Percentage must be between 0 and 100.", "Passwords do not match."

**Tier 2 — Component-level error** (one widget or table fails to load):
- Within the component's card/container: warning icon + "Couldn't load this data." + "Retry" link
- Does not affect the rest of the page
- Example: A dashboard stat card that failed its API call shows this inline; other cards still load

**Tier 3 — Page-level error** (entire page fails):
- Full-page centred layout: error icon, heading ("Something went wrong"), brief description ("We couldn't load this page. This has been reported."), "Retry" button and "Go home" link
- HTTP 401/403: redirect to login or show "You don't have permission to view this page."
- HTTP 404: "This page doesn't exist." with navigation link back to dashboard
- HTTP 500: Generic error page with support contact

**Toast notifications for action errors**:
When a user action fails (e.g. "Approve" API call returns 422), show a red toast at the bottom-right:
- Icon: ✗ in red circle
- Text: Brief description of what failed (e.g. "Couldn't approve — document is already in terminal status.")
- Auto-dismisses after 5 seconds; also has a manual close ×

---

### 24.4 Success & Confirmation States

**Toast pattern** (non-destructive actions):
- Bottom-right toast, green background, checkmark icon
- Auto-dismisses after 3 seconds
- Examples: "Application submitted.", "Leave approved.", "Timetable published."

**Undo toast pattern** (reversible actions — uses UndoToast component):
- Bottom-centre toast, neutral background
- "Done · Undo" — clicking Undo reverses the action within 5 seconds
- Use for: moving applicants between pipeline stages, sending announcements (if scheduled), recording payments
- After 5 seconds the Undo option disappears and the action is permanent

**Confirmation dialog** (destructive or irreversible actions — uses ConfirmDialog component):
- Modal overlay
- Title: states what will happen (e.g. "Delete this fee structure?")
- Body: describes consequence (e.g. "This will remove the fee structure and cannot be undone. Active invoices referencing it will be preserved.")
- Buttons: Cancel (secondary) + Confirm (red primary)
- For very destructive actions (merge students, revoke all sessions, archive programme): require the user to type a confirmation string (e.g. "DELETE" or the entity name)

**Full-page success state** (multi-step workflows that complete):
- Centred: large checkmark animation, success heading, summary of what was done, next-step CTA
- Used for: Application wizard submission, Enrollment provisioning completion, Onboarding wizard launch

---

### 24.5 Pagination & Infinite Scroll

**Rule**: Use **pagination** (not infinite scroll) for all data tables in the Staff ERP and Admin Console. Infinite scroll is allowed only in notification feeds and chat threads.

**Pagination pattern**:
- Page size selector: 25 / 50 / 100 rows (dropdown at top-right of table)
- Pagination bar at the bottom: ← Previous | Page X of Y | Next →
- Jump-to-page input for tables with more than 10 pages
- Total record count shown: "Showing 26–50 of 218 records"
- URL reflects current page: `?page=2&per_page=50` (allows bookmarking and back-button navigation)

**Optimistic updates**: For approve/reject/status change actions on a table row, update the row UI immediately (don't wait for API response). If the API call fails, revert the UI and show an error toast.

---

## Part 25 — Mobile & Responsive Layout

### 25.1 Breakpoints

| Name | Min width | Target devices |
|---|---|---|
| `xs` | 0px | Small phones |
| `sm` | 480px | Large phones |
| `md` | 768px | Tablets |
| `lg` | 1024px | Small laptops / landscape tablets |
| `xl` | 1280px | Desktops |
| `2xl` | 1536px | Large monitors |

### 25.2 Staff ERP — Responsive Behaviour

The Staff ERP is primarily designed for desktop (`xl`+). At smaller sizes:

**`lg` (1024px)**:
- AI Copilot collapses by default (toggle button in header restores it)
- Work Panel narrows to 220px; My Wizards button still visible
- Tables: horizontal scroll rather than collapsing columns

**`md` (768px — tablet)**:
- Work Panel collapses into a slide-out sheet triggered by a "⊟ Work" button in the header
- My Wizards accessible via the same header button (sheet opens to My Wizards view)
- Canvas is full width
- AI Copilot accessible via a floating button (bottom-right, opens as a sheet from the bottom)
- Dashboard stat cards: 2-column grid instead of 4
- Kanban pipeline: horizontal scroll (each column 240px wide)

**`sm` and below (phone)**:
- Staff ERP is not the primary mobile experience. Show a banner: "For the best experience, use a desktop or tablet."
- Core approvals and attendance marking are optimised for mobile (see PWA note below)

### 25.3 Student Portal — Responsive Behaviour

The portal must be fully functional on mobile — many applicants will apply on a phone.

**Mobile layout** (`sm` and below):
- Navigation: bottom tab bar — Home, Apply, Status, Profile
- Application wizard: full-screen step view, step sidebar collapses into a progress bar at the top
- Forms: single-column layout (no 2-column grids)
- Buttons: full-width at mobile sizes
- Documents upload: tap to open camera roll or files app
- Payment: the payment gateway page must be mobile-optimised (Razorpay and PayU both support this natively)

**Guardian portal**: Designed mobile-first — parents primarily access on phones. Full mobile layout from `sm`.

### 25.4 PWA — Attendance Marking (Offline)

The attendance marking screen (`/app/academics/attendance/mark`) is a **Progressive Web App** that installs on the device and works fully offline.

**Install prompt**: When a faculty member visits the attendance marking screen on a mobile device, show an "Add to home screen" banner.

**Offline behaviour**:
- Student list is cached on first load and refreshed when online
- Attendance submissions are stored in the browser's local storage (IndexedDB)
- Visual indicator of offline mode: amber banner "Offline"
- Pending sync indicator: shows count of sessions not yet synced
- Auto-sync: triggers 30 seconds after connectivity is restored
- Manual sync: "Sync now" button in the offline banner

**What does NOT work offline**: Creating new sessions, loading timetable, accessing any other module. Only the attendance marking form for already-loaded sessions.

---

## Part 26 — Accessibility Requirements

### 26.1 WCAG 2.1 AA Compliance

All screens must meet WCAG 2.1 Level AA. Key requirements:

**Colour contrast**:
- Normal text (< 18pt): minimum 4.5:1 contrast ratio against background
- Large text (≥ 18pt or ≥ 14pt bold): minimum 3:1 ratio
- Status badges: text within badge must meet 4.5:1 against the badge background
- Do not rely on colour alone to convey status — always pair colour with an icon or text label

**Focus indicators**:
- All interactive elements must have a visible focus ring when navigated by keyboard
- Focus ring: 2px solid, `--color-primary` (#2563eb), 2px offset
- Never use `outline: none` without providing a custom focus indicator

**Keyboard navigation**:
- All functionality accessible without a mouse
- Logical tab order (left-to-right, top-to-bottom)
- Modal dialogs: trap focus within the modal while open; restore focus to the trigger element when closed
- Dropdown menus: arrow keys to navigate options, Escape to close
- Data tables: Tab moves between interactive elements; arrow keys move between cells if cells contain interactive content

**Screen readers**:
- All images must have descriptive `alt` text (or `alt=""` for decorative images)
- All form inputs must have associated `<label>` elements
- Status badges use `aria-label` to convey the full meaning (not just colour)
- Icons used as buttons must have `aria-label`
- Loading skeletons: `aria-busy="true"` on the container while loading; remove when loaded
- Dynamic content updates (toasts, error messages): use ARIA live regions (`aria-live="polite"` for non-critical, `aria-live="assertive"` for errors)

**Forms**:
- Required fields: marked with a visible indicator (asterisk *) and `aria-required="true"`
- Error messages: associated with their input via `aria-describedby`
- Success/error states: not communicated by colour alone — always include text

### 26.2 Specific Component Accessibility Notes

| Component | Accessibility note |
|---|---|
| **DataTable** | `<table>` with proper `<thead>`, `<th scope="col">`, `<td>`. Sort buttons within `<th>` use `aria-sort`. Row checkboxes: `aria-label="Select [entity name]"` |
| **Kanban board** | Each card is a `<button>` or `<a>`. Provide a list-view alternative for users who cannot use drag-and-drop |
| **Modal/Dialog** | `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing to the dialog title |
| **Toast notifications** | `role="status"` for informational toasts, `role="alert"` for errors |
| **Date picker** | Keyboard-navigable calendar; also allow direct date text input as a fallback |
| **File uploader** | `<input type="file">` hidden but accessible; visible label clickable to trigger it |
| **Rich text editor** | Must be keyboard accessible; provide toolbar keyboard shortcuts (Ctrl+B, Ctrl+I, etc.) |
| **Permission picker tree** | Group items with `role="tree"` and `role="treeitem"`; arrow keys expand/collapse groups |
| **Progress steps (wizard)** | Use `aria-current="step"` on the current step; completed steps: `aria-label="Step X: [title] — Completed"` |
| **Status badges** | Never use only colour; include icon + text. E.g. "✓ Approved" not just a green dot |

### 26.3 Language & Internationalisation Accessibility

- `lang` attribute on `<html>` must update when the language is changed
- All UI strings must come from the i18n translation layer — no hardcoded English strings in components
- Number formatting (currency ₹, percentages, dates) must adapt to the selected locale
- Text containers must be tested with 40% longer strings (Hindi and Kannada text is significantly longer than English equivalents)

---

## Part 27 — Notification & Feedback System

### 27.1 In-App Notification Types

All notifications are delivered to the notification bell in the header. Four categories:

| Category | Icon | Colour | Examples |
|---|---|---|---|
| **Action required** | ! in circle | Amber | "Document review pending", "Approval waiting", "Student reported — mark attendance" |
| **Informational** | ℹ in circle | Blue | "Merit list has been published", "Timetable updated for your batch" |
| **Success** | ✓ in circle | Green | "Payment received from [student]", "Offer letter sent to [student]" |
| **System / Warning** | ⚠ triangle | Red | "System maintenance at 2AM", "Backup failed" |

### 27.2 Toast / Snackbar System

**Position**: Bottom-right of viewport (Staff ERP); Bottom-centre (Portal)

**Stacking**: Multiple toasts stack vertically (newest on top). Maximum 3 toasts visible at once; older ones dismissed to make room.

**Duration**:
- Success: 3 seconds
- Info: 4 seconds
- Error: persistent until manually dismissed (close button always visible)
- Undo toast: 5 seconds before action becomes permanent

**Content structure**: Icon + Short message (max 80 chars) + Optional action link (Undo / View / Retry) + Close ×

### 27.3 Confirmation Dialog Patterns

**Use confirmation dialogs for**:
- Deleting any record
- Publishing (sending to all recipients — irreversible)
- Approving or rejecting items that affect real people
- Revoking access or sessions
- Merging records

**Do not use confirmation dialogs for**:
- Saving a draft
- Navigating away (use browser's `beforeunload` for unsaved form changes instead)
- Filtering or sorting

**Double-confirm pattern** (for the most destructive actions): Require the user to type a specific string before the action proceeds. Use for: student record merge, account deletion, programme archive, payroll approval.

---

## Part 28 — Integration Flows (User-Facing)

These are complex multi-screen flows involving external services. Each must be designed end-to-end.

### 28.1 DigiLocker Document Verification Flow

**Trigger**: "Verify via DigiLocker" button on Step 7 of the Application Wizard (Portal).
**Prerequisite**: Feature flag `admissions.digilocker_enabled` must be On.

**Step-by-step user flow**:

1. Applicant clicks "Verify via DigiLocker" next to a document (e.g. Class 12 marksheet)
2. A modal appears: "You'll be redirected to DigiLocker to authorise ALIS to access your [document type]. This will take 1–2 minutes." — Continue button + Cancel
3. Clicking Continue → browser redirects to DigiLocker OAuth login (DigiLocker's own page — ALIS has no control over this screen)
4. On successful DigiLocker authorisation → browser redirects back to ALIS (with an auth code in the URL)
5. ALIS shows a "Verifying your document..." spinner (while the backend fetches the document from DigiLocker)
6. On success: the document card updates to show "DigiLocker Verified ✓" green badge; the upload zone is replaced by "Verified via DigiLocker — no upload needed"
7. On failure (document not found in DigiLocker, or permission denied): show a message "Couldn't fetch your document from DigiLocker. Please upload it manually." and show the regular file upload zone

**Design notes**:
- The redirect is a full-page navigation (not a popup — popups are blocked by mobile browsers)
- Preserve the wizard's step state across the redirect (stored server-side, keyed to session)
- The "Verify via DigiLocker" button must be clearly optional ("Or upload manually" link beside it)
- Show which documents support DigiLocker verification (not all document types are available via DigiLocker)

---

### 28.2 NTA Score Auto-Import Flow

**Trigger**: "Import from NTA" button on Step 5 (Entrance Exam Scores) of the Application Wizard.
**Prerequisite**: Feature flag `admissions.nta_auto_import` must be On.

**Step-by-step**:

1. Applicant clicks "Import from NTA"
2. A modal appears with a form:
   - Exam type (dropdown: JEE Mains / JEE Advanced / NEET / CUET)
   - Roll number (text, required)
   - Exam year (dropdown, last 3 years)
3. Applicant submits → ALIS fetches from NTA API
4. On success: modal shows the fetched scores ("We found your JEE Mains score: Percentile 87.4, Rank 42,311") with a "Use these scores" button
5. On "Use these scores": modal closes, scores pre-filled into the entrance exam form fields, marked with "NTA Imported" badge
6. On not found: "No record found for this roll number. Please enter your scores manually."

**Design note**: The imported scores are pre-filled but editable — applicant can correct them before submitting.

---

### 28.3 Payment Gateway Flow (Razorpay / PayU)

**Trigger**: "Pay ₹X via [gateway]" button on Step 10 of the Application Wizard, or on the Fee Payment Portal.

**Flow**:

1. User clicks Pay button
2. ALIS creates an order on the backend and receives an order ID
3. The payment gateway's JavaScript SDK is loaded (Razorpay Checkout or PayU lightbox)
4. A payment modal appears (the gateway's own UI) — prefilled with: amount, student name, email, phone
5. User completes payment within the gateway modal (card / UPI / netbanking / wallet)
6. On payment success: gateway callback → ALIS backend records the payment → user sees a success screen with: transaction ID, amount paid, "Download receipt" button
7. On payment failure: gateway callback → user sees failure screen with: reason (card declined / network issue), "Try again" button, "Pay later" option
8. On gateway modal closed without paying: user is returned to the payment screen (no change)

**Important**: The payment amount and order details must be set server-side (never client-side) to prevent tampering. The frontend only initiates the SDK with the order ID received from the backend.

**Retry behaviour**: After a failed payment, the same order ID can be reused for retry (Razorpay supports this). Do not create a new order per retry attempt.

---

### 28.4 WhatsApp Notification Delivery

**Note for design team**: WhatsApp messages are sent by the backend — the frontend shows delivery status only.

**Delivery report UI** (in the Bulk Messaging delivery report screen):

| Status | Meaning | Visual |
|---|---|---|
| Queued | Backend has accepted the job | Grey clock icon |
| Sent | Submitted to WhatsApp API | Single tick (✓) |
| Delivered | Received on recipient's device | Double tick (✓✓) |
| Read | Recipient has opened the message | Blue double tick |
| Failed | WhatsApp rejected or number invalid | Red × with error reason |

**DLT approval status** (in Message Templates screen):
- Templates must be approved by Meta / DLT before they can be used for WhatsApp delivery
- Show a status badge per template: `Pending Approval` (amber) / `Approved` (green) / `Rejected` (red)
- Rejected templates show the rejection reason on hover
- Cannot select an unapproved template when composing a WhatsApp message

---

## Part 29 — Backend Readiness Status

This section tells the design team which screens are fully backed by real APIs and which require backend work before they can be wired.

**Legend**: ✅ Ready · ⚠ Partial · 🔲 Pending build

| Screen | Status | Notes |
|---|---|---|
| Login / Auth / MFA | ✅ Ready | Full auth + MFA + session management |
| Role Dashboards (all 6) | ✅ Ready | All data endpoints exist |
| Admissions Pipeline | ✅ Ready | 87 routes, all 10 stages |
| Applicant Detail Drawer | ✅ Ready | All 8 tabs wired |
| Lead CRM | ✅ Ready | Including duplicate detection |
| Document Verification Queue | ✅ Ready | Including DigiLocker integration |
| Merit List | ✅ Ready | Policy formula + seat allocation |
| Seat Matrix | ✅ Ready | |
| Reporting Gate | ✅ Ready | |
| Re-admissions | ✅ Ready | |
| Identity Match Review | ✅ Ready | Migration 0040 |
| Access Lift Panel | ✅ Ready | EC-ADM-05 |
| Duplicate Student Merge | ✅ Ready | `initiate_merge` + `execute_merge` |
| Academics — Programmes/Courses | ✅ Ready | |
| Timetable | ✅ Ready | |
| Attendance Marking (PWA) | ✅ Ready | Offline mode included |
| Attendance Report | ✅ Ready | |
| OBE / CO-PO Mapping | ✅ Ready | |
| Exam Schedule | ✅ Ready | |
| Hall Tickets | ✅ Ready | |
| Results Entry | ✅ Ready | |
| Re-evaluation Queue | ✅ Ready | |
| Finance — Fee Structures | ✅ Ready | |
| Finance — Invoices | ✅ Ready | |
| Finance — e-Invoice / IRN | ✅ Ready | NIC API + stub mode |
| Finance — Payments | ✅ Ready | |
| Finance — Scholarships | ✅ Ready | |
| Finance — Refunds | ✅ Ready | |
| Finance — Tally / Busy Export | ✅ Ready | Feature-flagged |
| HR — Staff Directory | ✅ Ready | |
| HR — Leave Management | ✅ Ready | |
| HR — Payroll | ✅ Ready | |
| HR — Performance Reviews | ✅ Ready | |
| HR — Visiting Faculty Sessions | ✅ Ready | OTP flow |
| Student Services — Hostel | ✅ Ready | |
| Student Services — Transport | ✅ Ready | |
| Student Services — Library | ✅ Ready | |
| Student Services — Grievances | ✅ Ready | |
| Communications — Announcements | ✅ Ready | |
| Communications — Bulk Messaging | ✅ Ready | |
| Communications — Templates | ✅ Ready | |
| Reporting — Dashboards | ✅ Ready | |
| Reporting — Custom Builder | ✅ Ready | |
| Reporting — AI Insights | ✅ Ready | |
| Alumni Directory | ✅ Ready | |
| Placement Drives | ✅ Ready | |
| PhD Module | ✅ Ready | |
| Regulatory / Audit | ✅ Ready | |
| Convocation | ✅ Ready | |
| Workflows / Approvals | ✅ Ready | |
| Process Engine | ✅ Ready | |
| Consent Management | ✅ Ready | |
| Admin Onboarding Wizard | ✅ Ready | |
| Policy Studio | ✅ Ready | |
| Team Management | ✅ Ready | |
| Feature Flags | ✅ Ready | |
| Settings | ✅ Ready | |
| Audit Log Viewer | ✅ Ready | |
| Application Wizard (10 steps) | ✅ Ready | |
| Application Status | ✅ Ready | |
| Offer Letter | ✅ Ready | |
| Enrolled Student Home | ✅ Ready | |
| Fee Payment Portal | ✅ Ready | |
| Profile & Document Vault | ✅ Ready | |
| **Guardian Home** | ⚠ Partial | Auth exists; attendance/fees/notifications endpoints being built |
| **Guardian Attendance View** | 🔲 Pending | Endpoint `GET /guardian/students/{id}/attendance` — in build |
| **Guardian Fee View** | 🔲 Pending | Endpoint `GET /guardian/students/{id}/fees` — in build |
| **Guardian Notifications** | ⚠ Partial | `GET /comms/parent/{id}/notifications` exists |
| **Guardian Contact Counsellor** | 🔲 Pending | Endpoint `POST /guardian/enquiry` — in build |
| DigiLocker OAuth flow | ✅ Ready | Toggle via feature flag `admissions.digilocker_enabled` |
| NTA Score Import | ✅ Ready | Toggle via feature flag `admissions.nta_auto_import` |
| Language Switcher | ⚠ Partial | Backend sends English only; i18n strings exist at ~10% for kn/mr/ta |
| MFA Trusted Devices | ✅ Ready | |

**For screens marked 🔲 Pending**: Design the UI fully — the backend implementation will catch up. Use mock data in the prototype. Expected completion: before production go-live.

---

## Part 30 — Data Formats & Display Conventions

Consistent data formatting matters for a coherent, professional product. These rules apply everywhere.

### 30.1 Currency

- Always display in Indian Rupees (₹)
- Use Indian number formatting: ₹1,23,456 (not ₹1,23,456.00 unless decimal places are relevant)
- When displaying zero outstanding: "₹0" not "₹0.00"
- In tables: right-align currency columns
- For large sums on stat cards: abbreviate — ₹12.4L (lakh), ₹1.2Cr (crore); show full value on hover tooltip

### 30.2 Dates & Times

- Date format: DD MMM YYYY (e.g. 15 Mar 2025) — readable, unambiguous across locales
- Short date: DD/MM (e.g. 15/03) — used in compact table cells where year is obvious from context
- Time: 12-hour with AM/PM (e.g. 2:30 PM) for user-facing displays; 24-hour in log/audit views
- Relative time: use "X minutes ago", "Yesterday", "2 days ago" for recent events in timelines and feeds; switch to absolute date after 7 days
- Date pickers: always show the full DD MMM YYYY format in the input field (not an ambiguous MM/DD/YYYY)

### 30.3 Application & Roll Number IDs

- Application IDs: `APP-2025-000047` — monospace font, never truncated
- Roll numbers: programme-prefix + year + sequence (e.g. `CS-2025-0001`) — monospace font
- Staff IDs, Invoice numbers, IRN: always monospace; truncate long strings with `…` and show full on hover tooltip
- UUIDs: never display raw UUIDs to end users — always use human-readable IDs where available

### 30.4 Status Badges — Colour Map

Use these exact semantics consistently across all modules:

| Status | Colour | Use for |
|---|---|---|
| Active / Enrolled / Approved / Paid / Published | Green | Positive terminal states |
| Pending / Under Review / Submitted / Draft | Blue | In-progress states |
| Warning / Expiring / Low attendance | Amber | Needs attention |
| Rejected / Failed / Overdue / Detained / Cancelled | Red | Negative terminal states |
| Inactive / Archived / Expired | Grey | Soft-deleted or historical |
| Waitlisted / On Hold | Purple | Deferred / special queue |

### 30.5 Percentages & Scores

- Attendance percentage: always show one decimal place (e.g. 74.3%, not 74%)
- CGPA: two decimal places (e.g. 7.85)
- Entrance exam percentile: two decimal places (e.g. 87.42)
- Composite merit score: two decimal places, shown in a dedicated column — never rounded

### 30.6 File Uploads — Accepted Formats & Limits

| Document type | Accepted formats | Max size |
|---|---|---|
| Academic certificates / marksheets | PDF, JPG, PNG | 2 MB |
| Photograph (applicant) | JPG, PNG | 500 KB |
| Aadhaar / ID proof | PDF, JPG, PNG | 2 MB |
| Category certificate | PDF, JPG, PNG | 2 MB |
| Answer sheet (re-evaluation) | PDF | 10 MB |
| Bulk import CSV | CSV | 5 MB |
| Announcement attachment | PDF, DOCX, XLSX, JPG, PNG | 10 MB |
| Exam paper (encrypted) | PDF | 50 MB |

All file uploads show: file name, file size, upload progress bar, and a remove button after upload. Compressed image preview shown for image files.

---

## Part 31 — Role Access Matrix (Quick Reference)

A condensed view of which roles can access which modules — useful for designing role-based nav and permission gates.

| Module | SUPER_ADMIN | REGISTRAR | ADMISSIONS | FACULTY | HOD | FINANCE | HR | EXAM | STUDENT_SVC | COMMS | REPORTING | TPO | PHD | COMPLIANCE | STUDENT | PARENT |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Dashboard | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Admissions | ✓ | ✓ | ✓ | — | — | — | — | — | — | — | R | — | — | — | — | — |
| Academics | ✓ | R | — | ✓ | ✓ | — | — | — | — | — | R | — | — | — | — | — |
| Examinations | ✓ | R | — | ✓ | R | — | — | ✓ | — | — | R | — | — | — | — | — |
| Finance | ✓ | R | — | — | — | ✓ | — | — | — | — | R | — | — | — | — | — |
| HR | ✓ | R | — | Self | HOD | — | ✓ | — | — | — | R | — | — | — | — | — |
| Student Services | ✓ | R | — | — | — | — | — | — | ✓ | — | R | — | — | — | — | — |
| Communications | ✓ | ✓ | — | Limited | Limited | — | — | — | — | ✓ | — | — | — | — | — | — |
| Reporting | ✓ | R | R | — | R | R | R | R | R | — | ✓ | R | R | R | — | — |
| Alumni/Placement | ✓ | R | — | — | — | — | — | — | — | — | R | ✓ | — | — | — | — |
| PhD | ✓ | R | — | Supervisor | — | — | — | — | — | — | R | — | ✓ | — | — | — |
| Regulatory | ✓ | R | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | — |
| Convocation | ✓ | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| Workflows | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — |
| Process Engine | ✓ | R | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| Consent | ✓ | ✓ | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | — |
| Admin Console | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| Student Portal | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — |
| Guardian Portal | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ |

**Key**: ✓ = Full access · R = Read-only access · Limited = Scoped to own records · Self = Own profile only · HOD = Subordinates only · — = No access

---

*End of ALIS Frontend UX Specification — Production-Ready v2.0*
*Total screens: 62 · Total routes: 52 · Surfaces: 3 (Staff ERP, Student Portal, Admin Console)*
*Navigation model: Work-first (Work Panel + My Wizards + Hybrid D canvas frames)*
*Safe to share with external UI/UX teams — contains no source code, credentials, or internal architecture details.*
