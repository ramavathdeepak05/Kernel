# ALIS OS — Frontend Rebuild Specification
## Role-Based Shell, Navigation & Dashboards
**QUAICU Solutions Private Limited | Confidential**

> **🧑‍💻 Frontend Intern**: Before working on any frontend code, read [CONTRIBUTING.md](../CONTRIBUTING.md) for PR rules, [ONBOARDING.md](./ONBOARDING.md) for setup, and [CODEBASE_MAP.md](./CODEBASE_MAP.md) § Frontend for the file map.

---

## 0. Read This First

This document specifies a **full frontend rebuild** of the ALIS OS web application. Read every section before touching any file. Do not assume anything not written here. If something is unclear, stop and ask rather than infer.

### What this task covers
1. Rebuild `ALISShell` — the 3-column layout wrapper
2. Rebuild `IconNav` — collapsible icon-only nav that expands on hover
3. Build `AgentRail` — role-aware AI panel with quick-action chips (skeleton/placeholder)
4. Build `RoleDashboard` — central component that renders the correct dashboard by role
5. Build all 9 role-specific dashboard pages
6. Update `ROLE_MODULES` and role config to control nav, agent chips, and routing per role
7. Update routing to wire everything together

### What this task does NOT cover
- Auth flow — do not modify `authService`, `useAuthStore`, `ProtectedRoute`, or login
- Any public/standalone routes: `/login`, `/apply/*`, `/guardian`, `/attendance/mark/:sessionId`
- The 40+ inner pages (AdmissionsPage, FinancePage, etc.) — leave them untouched
- Backend — no backend changes

### Hardcoded truth from this conversation (do not contradict)
- Auth is fully working. `useAuthStore` has `isAuthenticated`, `user`, `token`
- `useALISRole()` returns `{ role, ... }` — use this everywhere for role detection
- Session is stored in `sessionStorage` — do not change to localStorage
- 401 interceptor and token refresh are already handled by `apiFetch`

---

## 1. Tech Stack

```
React 19 + TypeScript
Vite 7
Tailwind CSS v4
Radix UI (use for accessible primitives only — Tooltip, Dialog, Popover)
React Router DOM v7 (react-router-dom ^7.1.1)
Zustand (already in use — do not swap)
```

No additional packages unless absolutely unavoidable. Do not install shadcn, MUI, Ant Design, or any other component library.

---

## 2. Design System

### 2.1 Colour Tokens

Define these as CSS custom properties in `src/styles/tokens.css` (or equivalent Tailwind config):

```css
:root {
  /* Brand */
  --color-primary:        #16a34a;   /* Green-600 — primary actions, active states */
  --color-primary-dark:   #15803d;   /* Green-700 — hover on primary */
  --color-primary-light:  #f0fdf4;   /* Green-50  — backgrounds, selected rows */
  --color-primary-border: #86efac;   /* Green-300 — subtle borders on green surfaces */

  /* Surfaces */
  --color-bg-page:        #f9fafb;   /* Gray-50   — page background */
  --color-bg-surface:     #ffffff;   /* White     — cards, panels */
  --color-bg-elevated:    #ffffff;   /* White     — modals, popovers */

  /* Text */
  --color-text-primary:   #111827;   /* Gray-900  — headings, body */
  --color-text-secondary: #6b7280;   /* Gray-500  — labels, metadata */
  --color-text-muted:     #9ca3af;   /* Gray-400  — placeholders, hints */
  --color-text-on-primary:#ffffff;   /* White     — text on green backgrounds */

  /* Borders */
  --color-border:         #e5e7eb;   /* Gray-200  — default borders */
  --color-border-strong:  #d1d5db;   /* Gray-300  — hover, focus borders */

  /* Semantic */
  --color-danger:         #dc2626;   /* Red-600   */
  --color-danger-bg:      #fef2f2;   /* Red-50    */
  --color-danger-border:  #fca5a5;   /* Red-300   */
  --color-warning:        #d97706;   /* Amber-600 */
  --color-warning-bg:     #fffbeb;   /* Amber-50  */
  --color-warning-border: #fcd34d;   /* Amber-300 */
  --color-info:           #2563eb;   /* Blue-600  */
  --color-info-bg:        #eff6ff;   /* Blue-50   */
  --color-info-border:    #93c5fd;   /* Blue-300  */
  --color-success:        #16a34a;   /* Green-600 */
  --color-success-bg:     #f0fdf4;   /* Green-50  */
  --color-success-border: #86efac;   /* Green-300 */

  /* Nav */
  --nav-width-collapsed:  56px;
  --nav-width-expanded:   220px;
  --nav-transition:       200ms ease;
}
```

**Rules:**
- Never use hardcoded hex values in components — always use these CSS variables or their Tailwind equivalents
- Green is the ONLY brand colour. No navy, no blue as primary.
- White surfaces with green accents. Page background is `--color-bg-page` (very light gray)
- Status colours (red, amber, blue) are for semantic use only — never decorative

### 2.2 Typography

```css
/* Base */
font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
font-size: 14px;      /* base body */
line-height: 1.5;

/* Scale */
--text-xs:    11px;
--text-sm:    12px;
--text-base:  14px;
--text-md:    15px;
--text-lg:    16px;
--text-xl:    18px;
--text-2xl:   22px;
--text-3xl:   26px;
```

### 2.3 Spacing & Shape

```
Border radius: 6px (sm), 8px (md/default), 12px (lg/cards)
Card padding: 16px
Section gap: 16px between cards, 12px within
Metric card padding: 14px 16px
```

### 2.4 Reusable UI Components to Build

Build these as shared components in `src/components/ui/`. These are used across all 9 dashboards.

#### `<MetricCard>`
```tsx
// Props
label: string
value: string | number
delta?: string          // e.g. "+4.2% this cycle"
deltaVariant?: 'positive' | 'negative' | 'neutral'
urgent?: boolean        // adds red left border if true

// Layout: white card, green-50 bg option, muted label above, large value, small delta below
```

#### `<ApprovalQueueItem>`
```tsx
// Props
tag: string             // 2-4 char label e.g. "APP" "PAY" "GR"
title: string
subtitle: string
meta: string            // third line — timestamp, policy version, etc.
status: 'pending' | 'review' | 'active' | 'urgent' | 'done'
showApproveReject?: boolean   // shows Approve + Reject buttons if true
onApprove?: () => void
onReject?: () => void
onView?: () => void

// Tag renders as a small colored square
// Approve = green button, Reject = red button, View = gray button
```

#### `<ProgressRow>`
```tsx
// Props
label: string
value: number           // 0–100
variant?: 'default' | 'warn' | 'danger' | 'success'

// Horizontal bar: label (fixed 140px) | bar (flex) | percentage (32px)
// default = green fill, warn = amber, danger = red, success = green
```

#### `<StatusBadge>`
```tsx
// Props
status: 'pending' | 'review' | 'active' | 'urgent' | 'done'

// Pill badge with semantic colours
// pending = amber, review = blue, active = green, urgent = red, done = gray
```

#### `<TimelineItem>`
```tsx
// Props
title: string
subtitle: string
done: boolean           // done = green filled dot, undone = gray ring

// Vertical connector line between items
```

#### `<AlertBar>`
```tsx
// Props
variant: 'info' | 'warning' | 'danger' | 'success'
children: ReactNode

// Full-width coloured alert strip. Uses semantic colour variables.
```

#### `<SectionCard>`
```tsx
// Props
title: string
action?: { label: string; onClick: () => void }
children: ReactNode

// White card with border, title + optional right-side action link, children below
```

---

## 3. File Structure

```
web/src/
├── styles/
│   └── tokens.css                          # CSS variables (Section 2.1)
│
├── config/
│   └── roleConfig.ts                       # ROLE_MODULES, nav items, agent chips per role
│
├── components/
│   ├── shell/
│   │   ├── ALISShell.tsx                   # 3-column layout: nav | canvas | agent
│   │   ├── IconNav.tsx                     # Collapsible icon nav
│   │   └── AgentRail.tsx                   # Role-aware AI panel
│   │
│   ├── dashboard/
│   │   └── RoleDashboard.tsx               # Switches to correct dashboard by role
│   │
│   └── ui/
│       ├── MetricCard.tsx
│       ├── ApprovalQueueItem.tsx
│       ├── ProgressRow.tsx
│       ├── StatusBadge.tsx
│       ├── TimelineItem.tsx
│       ├── AlertBar.tsx
│       └── SectionCard.tsx
│
├── pages/
│   └── dashboards/
│       ├── SuperAdminDashboard.tsx
│       ├── RegistrarDashboard.tsx
│       ├── DeanDashboard.tsx
│       ├── HODDashboard.tsx
│       ├── FacultyDashboard.tsx
│       ├── StudentDashboard.tsx
│       ├── FinanceDashboard.tsx
│       ├── CoEDashboard.tsx
│       └── HRDashboard.tsx
│
└── routes/
    └── index.tsx                           # Update routing — preserve all 40+ existing routes
```

**Files you must NOT touch:**
- `src/services/authService.ts` (or wherever auth lives)
- `src/store/useAuthStore.ts`
- `src/hooks/useALISRole.ts` — read it but only modify if BACKEND_ROLE_MAP is missing roles
- `src/components/ProtectedRoute.tsx`
- Any page file except the 9 dashboard files above
- `src/pages/LoginPage.tsx`
- `src/pages/PortalHomePage.tsx`, `ApplicationWizardPage.tsx`, `GuardianPortalPage.tsx`, `OfflineAttendancePage.tsx`

---

## 4. Role Configuration

Create `src/config/roleConfig.ts`. This is the single source of truth for what each role sees.

### 4.1 Backend Role Map

The backend returns these role strings. Map them to frontend role keys:

```ts
export type FrontendRole =
  | 'SUPER_ADMIN'
  | 'REGISTRAR'
  | 'DEAN'
  | 'HOD'
  | 'FACULTY'
  | 'STUDENT'
  | 'FINANCE_OFFICER'
  | 'COE'
  | 'HR_MANAGER';

export const BACKEND_ROLE_MAP: Record<string, FrontendRole> = {
  'SUPER_ADMIN':     'SUPER_ADMIN',
  'REGISTRAR':       'REGISTRAR',
  'DEAN':            'DEAN',
  'HOD':             'HOD',
  'FACULTY':         'FACULTY',
  'STUDENT':         'STUDENT',
  'FINANCE_OFFICER': 'FINANCE_OFFICER',
  'COE':             'COE',
  'HR_MANAGER':      'HR_MANAGER',
};
```

### 4.2 Nav Items Per Role

Each role sees only their relevant nav items in `IconNav`. Define as:

```ts
export interface NavItem {
  icon: string;        // Lucide icon name as string, e.g. 'LayoutDashboard'
  label: string;
  path: string;
  badge?: number;      // optional notification count
}

export interface NavSection {
  section: string;
  items: NavItem[];
}

export const ROLE_NAV: Record<FrontendRole, NavSection[]> = {

  SUPER_ADMIN: [
    { section: 'Platform', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'Building2',       label: 'Institution',         path: '/settings' },
      { icon: 'Users',           label: 'Users & Roles',       path: '/users' },
      { icon: 'Sliders',         label: 'Policy Studio',       path: '/admin/policies' },
      { icon: 'Flag',            label: 'Feature Flags',       path: '/settings' },
    ]},
    { section: 'Modules', items: [
      { icon: 'GraduationCap',   label: 'Admissions',          path: '/admissions' },
      { icon: 'BookOpen',        label: 'Academics',           path: '/academics' },
      { icon: 'ClipboardList',   label: 'Examinations',        path: '/examinations' },
      { icon: 'Wallet',          label: 'Finance',             path: '/finance' },
      { icon: 'Users2',          label: 'HR & Payroll',        path: '/hr' },
      { icon: 'Heart',           label: 'Student Services',    path: '/students' },
      { icon: 'BarChart3',       label: 'Regulatory',          path: '/regulatory' },
    ]},
    { section: 'System', items: [
      { icon: 'Activity',        label: 'Audit Ledger',        path: '/reports' },
      { icon: 'Zap',             label: 'Domain Events',       path: '/reports' },
      { icon: 'Eye',             label: 'Observability',       path: '/reports' },
    ]},
  ],

  REGISTRAR: [
    { section: 'Admissions', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'Inbox',           label: 'Application Queue',   path: '/admissions',  badge: 47 },
      { icon: 'CheckCircle',     label: 'Eligibility',         path: '/admissions' },
      { icon: 'ListOrdered',     label: 'Merit List',          path: '/admissions' },
      { icon: 'UserCheck',       label: 'Enrollment',          path: '/admissions' },
    ]},
    { section: 'Academic', items: [
      { icon: 'Calendar',        label: 'Academic Calendar',   path: '/academics' },
      { icon: 'Clock',           label: 'Timetable',           path: '/academics' },
      { icon: 'BarChart2',       label: 'Results',             path: '/examinations' },
      { icon: 'FileText',        label: 'Document Issuance',   path: '/academics' },
    ]},
    { section: 'Compliance', items: [
      { icon: 'Shield',          label: 'NAAC / NIRF',         path: '/regulatory' },
      { icon: 'FileArchive',     label: 'UGC Returns',         path: '/regulatory' },
      { icon: 'ScrollText',      label: 'Audit Ledger',        path: '/reports' },
    ]},
  ],

  DEAN: [
    { section: 'Oversight', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'BarChart3',       label: 'Dept Reports',        path: '/reports' },
      { icon: 'UserPlus',        label: 'Faculty Appts',       path: '/recruitment' },
      { icon: 'BookOpen',        label: 'Curriculum',          path: '/academics' },
      { icon: 'ArrowUpCircle',   label: 'Escalations',         path: '/dashboard',   badge: 5 },
    ]},
    { section: 'Student Affairs', items: [
      { icon: 'Award',           label: 'Scholarships',        path: '/students',    badge: 3 },
      { icon: 'AlertTriangle',   label: 'Disciplinary',        path: '/students' },
      { icon: 'MessageCircle',   label: 'Grievances',          path: '/students' },
    ]},
    { section: 'Regulatory', items: [
      { icon: 'Shield',          label: 'NAAC Criteria',       path: '/regulatory' },
      { icon: 'Star',            label: 'NBA Program',         path: '/regulatory' },
    ]},
  ],

  HOD: [
    { section: 'Department', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'CheckSquare',     label: 'Approval Queue',      path: '/dashboard',   badge: 8 },
      { icon: 'UserX',           label: 'Attendance',          path: '/academics' },
      { icon: 'BookOpen',        label: 'Courses',             path: '/academics' },
      { icon: 'Calendar',        label: 'Timetable',           path: '/academics' },
      { icon: 'BarChart2',       label: 'Faculty Workload',    path: '/reports' },
    ]},
    { section: 'Academic', items: [
      { icon: 'Edit3',           label: 'IA Marks',            path: '/examinations' },
      { icon: 'Target',          label: 'OBE / CO-PO',         path: '/academics' },
      { icon: 'Shield',          label: 'NAAC — C2',           path: '/regulatory' },
    ]},
    { section: 'Escalations', items: [
      { icon: 'ArrowUp',         label: 'To Dean',             path: '/dashboard',   badge: 1 },
      { icon: 'ArrowDown',       label: 'From Faculty',        path: '/dashboard',   badge: 7 },
    ]},
  ],

  FACULTY: [
    { section: 'My Classes', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'Calendar',        label: 'Schedule',            path: '/my/courses' },
      { icon: 'UserCheck',       label: 'Attendance',          path: '/my/courses' },
      { icon: 'ClipboardList',   label: 'Assignments',         path: '/my/courses' },
      { icon: 'Edit3',           label: 'IA Marks Entry',      path: '/examinations' },
      { icon: 'MessageCircle',   label: 'Grievances',          path: '/students',    badge: 3 },
    ]},
    { section: 'Content', items: [
      { icon: 'FileText',        label: 'Course Materials',    path: '/academics' },
      { icon: 'Monitor',         label: 'LMS',                 path: '/academics' },
      { icon: 'Target',          label: 'CO Progress',         path: '/academics' },
    ]},
    { section: 'Self-Service', items: [
      { icon: 'Umbrella',        label: 'Leave',               path: '/training' },
      { icon: 'Star',            label: 'CAS Appraisal',       path: '/training' },
    ]},
  ],

  STUDENT: [
    { section: 'Academics', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'Calendar',        label: 'Timetable',           path: '/my/courses' },
      { icon: 'UserCheck',       label: 'Attendance',          path: '/my/courses' },
      { icon: 'BarChart2',       label: 'Marks & Grades',      path: '/my/exams' },
      { icon: 'ClipboardList',   label: 'Assignments',         path: '/my/courses' },
      { icon: 'FileText',        label: 'Results',             path: '/my/exams' },
    ]},
    { section: 'Services', items: [
      { icon: 'Wallet',          label: 'Fee Account',         path: '/my/fees' },
      { icon: 'BookOpen',        label: 'Library',             path: '/my/library' },
      { icon: 'Home',            label: 'Hostel',              path: '/students' },
      { icon: 'Award',           label: 'Scholarships',        path: '/students' },
      { icon: 'MessageCircle',   label: 'Grievances',          path: '/students',    badge: 1 },
    ]},
    { section: 'Career', items: [
      { icon: 'Briefcase',       label: 'Placement',           path: '/alumni' },
      { icon: 'Users',           label: 'Clubs & Events',      path: '/clubs' },
    ]},
  ],

  FINANCE_OFFICER: [
    { section: 'Revenue', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'CreditCard',      label: 'Fee Collection',      path: '/finance',     badge: 256 },
      { icon: 'Award',           label: 'Scholarships',        path: '/finance' },
      { icon: 'RotateCcw',       label: 'Refunds',             path: '/finance' },
    ]},
    { section: 'Expenditure', items: [
      { icon: 'ShoppingCart',    label: 'Vendors',             path: '/vendors' },
      { icon: 'Users2',          label: 'Payroll',             path: '/hr' },
      { icon: 'PieChart',        label: 'Budget',              path: '/budget' },
    ]},
    { section: 'Compliance', items: [
      { icon: 'Receipt',         label: 'GST / e-Invoice',     path: '/finance' },
      { icon: 'Percent',         label: 'TDS Returns',         path: '/finance' },
      { icon: 'FileBarChart',    label: 'Reports',             path: '/reports' },
      { icon: 'RefreshCw',       label: 'Bank Recon',          path: '/finance' },
    ]},
  ],

  COE: [
    { section: 'Exam Operations', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'Ticket',          label: 'Hall Tickets',        path: '/examinations', badge: 1 },
      { icon: 'Calendar',        label: 'Exam Schedule',       path: '/examinations' },
      { icon: 'Lock',            label: 'Question Papers',     path: '/examinations', badge: 3 },
      { icon: 'Map',             label: 'Seating',             path: '/examinations' },
      { icon: 'UserCheck',       label: 'Invigilation',        path: '/examinations' },
    ]},
    { section: 'Results', items: [
      { icon: 'Edit3',           label: 'Marks Entry',         path: '/examinations' },
      { icon: 'BarChart2',       label: 'Result Computation',  path: '/examinations' },
      { icon: 'RefreshCw',       label: 'Revaluation',         path: '/examinations', badge: 12 },
    ]},
    { section: 'Records', items: [
      { icon: 'FileText',        label: 'Transcripts',         path: '/examinations' },
      { icon: 'AlertTriangle',   label: 'Malpractice',         path: '/examinations' },
    ]},
  ],

  HR_MANAGER: [
    { section: 'Recruitment', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'Briefcase',       label: 'Job Requisitions',    path: '/recruitment',  badge: 4 },
      { icon: 'Users',           label: 'Applicant Tracking',  path: '/recruitment' },
      { icon: 'FileText',        label: 'Appointment Letters', path: '/recruitment' },
    ]},
    { section: 'Payroll', items: [
      { icon: 'Wallet',          label: 'Payroll Cycle',       path: '/hr',           badge: 3 },
      { icon: 'Umbrella',        label: 'Leave Management',    path: '/hr' },
      { icon: 'Star',            label: 'CAS Appraisals',      path: '/hr' },
    ]},
    { section: 'Records', items: [
      { icon: 'Users2',          label: 'Employee Directory',  path: '/hr' },
      { icon: 'GraduationCap',   label: 'Training & FDP',      path: '/training' },
      { icon: 'Shield',          label: 'Statutory Compliance',path: '/hr' },
      { icon: 'LogOut',          label: 'Exit Management',     path: '/hr' },
    ]},
  ],
};
```

### 4.3 AgentRail Quick-Action Chips Per Role

```ts
export interface AgentChip {
  label: string;
  prompt: string;   // What gets sent to the AI when clicked
}

export const ROLE_AGENT_CHIPS: Record<FrontendRole, AgentChip[]> = {
  SUPER_ADMIN: [
    { label: 'System health',      prompt: 'Show me current system health across all containers' },
    { label: 'Domain events',      prompt: 'Show the last 20 domain events across all modules' },
    { label: 'Compliance check',   prompt: 'What compliance items are due or overdue right now?' },
    { label: 'Export audit log',   prompt: 'Prepare an audit log export for the last 7 days' },
  ],
  REGISTRAR: [
    { label: 'Pending eligibility',prompt: 'Show all applications awaiting eligibility decision' },
    { label: 'Merit list status',  prompt: 'What is the current status of the merit list?' },
    { label: 'Enrollment queue',   prompt: 'Show students with pending enrollment clearance' },
    { label: 'NAAC export',        prompt: 'Generate the NAAC AQAR data export' },
  ],
  DEAN: [
    { label: 'My escalations',     prompt: 'List all items currently escalated to me' },
    { label: 'Scholarship queue',  prompt: 'Show pending scholarship disbursement approvals' },
    { label: 'Faculty vacancies',  prompt: 'What are the current faculty vacancies by department?' },
    { label: 'Dept summary',       prompt: 'Give me a performance summary across all departments' },
  ],
  HOD: [
    { label: 'Shortfall list',     prompt: 'List all students below 75% attendance in my department' },
    { label: 'IA marks status',    prompt: 'Which faculty have not submitted IA marks yet?' },
    { label: 'CO attainment',      prompt: 'Show CO attainment status for current semester courses' },
    { label: 'Faculty workload',   prompt: 'Show faculty workload distribution for my department' },
  ],
  FACULTY: [
    { label: 'Mark attendance',    prompt: 'Help me mark attendance for my next class' },
    { label: 'My grievances',      prompt: 'Show all open grievances assigned to me' },
    { label: 'IA marks entry',     prompt: 'Open IA marks entry for my courses' },
    { label: 'My schedule',        prompt: 'What is my teaching schedule for this week?' },
  ],
  STUDENT: [
    { label: 'My attendance',      prompt: 'Show my attendance percentage for all courses' },
    { label: 'My fees',            prompt: 'What is my current fee status and any dues?' },
    { label: 'Library status',     prompt: 'Show my issued books and any fines' },
    { label: 'Raise grievance',    prompt: 'Help me raise a grievance' },
  ],
  FINANCE_OFFICER: [
    { label: 'Fee summary',        prompt: 'Show fee collection summary for the current month' },
    { label: 'Overdue accounts',   prompt: 'List the top 20 overdue fee accounts by amount' },
    { label: 'Bank recon status',  prompt: 'What is the status of today\'s bank reconciliation?' },
    { label: 'Payroll status',     prompt: 'What is the status of the current payroll cycle?' },
  ],
  COE: [
    { label: 'Hall ticket status', prompt: 'Show hall ticket generation status for current semester' },
    { label: 'Q-paper vault',      prompt: 'Which question papers are missing from the vault?' },
    { label: 'Exam schedule',      prompt: 'Show the current exam schedule' },
    { label: 'Revaluation queue',  prompt: 'List all pending revaluation requests' },
  ],
  HR_MANAGER: [
    { label: 'Payroll exceptions', prompt: 'Show all payroll exceptions for this cycle' },
    { label: 'Leave approvals',    prompt: 'List all pending leave approval requests' },
    { label: 'Open requisitions',  prompt: 'Show all open job requisitions and their status' },
    { label: 'CAS due',            prompt: 'Which faculty are due for CAS appraisal?' },
  ],
};
```

### 4.4 Role Display Names

```ts
export const ROLE_DISPLAY: Record<FrontendRole, { name: string; initials: string; description: string }> = {
  SUPER_ADMIN:     { name: 'Super Admin',       initials: 'SA', description: 'Full system access' },
  REGISTRAR:       { name: 'Registrar',          initials: 'RG', description: 'Admissions · Academic · Compliance' },
  DEAN:            { name: 'Dean',               initials: 'DN', description: 'Academic & Student Affairs' },
  HOD:             { name: 'Head of Department', initials: 'HD', description: 'Department Operations' },
  FACULTY:         { name: 'Faculty',            initials: 'FC', description: 'Teaching & Assessment' },
  STUDENT:         { name: 'Student',            initials: 'ST', description: 'Self-Service Portal' },
  FINANCE_OFFICER: { name: 'Finance Officer',    initials: 'FO', description: 'FM-1 through FM-7 · MFA Active' },
  COE:             { name: 'Controller of Exams',initials: 'CE', description: 'Examination Operations' },
  HR_MANAGER:      { name: 'HR Manager',         initials: 'HR', description: 'HR & Payroll · MFA Active' },
};
```

---

## 5. Shell Components

### 5.1 `ALISShell.tsx`

3-column layout. Renders inside `ProtectedRoute` at all protected routes.

```
┌─────────────────────────────────────────────────────────┐
│  IconNav (56px collapsed → 220px on hover)              │
│  ┌──────┬──────────────────────────────┬──────────────┐ │
│  │      │                              │              │ │
│  │ Nav  │       Canvas (Outlet)        │  AgentRail   │ │
│  │      │                              │  (320px)     │ │
│  │      │                              │              │ │
│  └──────┴──────────────────────────────┴──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Layout rules:**
- Full viewport height, no body scroll — each column scrolls independently
- Nav column: `width: var(--nav-width-collapsed)` normally, expands to `var(--nav-width-expanded)` on hover — use CSS transition, not JS
- Canvas column: `flex: 1`, `overflow-y: auto`, `background: var(--color-bg-page)`
- AgentRail column: `width: 320px`, `flex-shrink: 0`, `border-left: 1px solid var(--color-border)`
- Shell header (topbar): rendered at the top of the Canvas column — NOT full-width. Contains page title, breadcrumb, and topbar actions for the current route.

**Component:**
```tsx
export function ALISShell() {
  const { role } = useALISRole();
  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <IconNav role={role} />
      <main style={{ flex: 1, overflowY: 'auto', background: 'var(--color-bg-page)' }}>
        <Outlet />
      </main>
      <AgentRail role={role} />
    </div>
  );
}
```

### 5.2 `IconNav.tsx`

**Behaviour:**
- Default state: collapsed to 56px — only icons visible, no labels
- On mouse enter (hover over the nav): smoothly expands to 220px — labels fade in
- On mouse leave: collapses back to 56px
- Use CSS transition on `width` and opacity for labels — no JS state needed for the expand/collapse
- Active route highlighted with green-50 background and green-600 text/icon
- Badge appears as a small red dot with number — always visible (even in collapsed state)
- Section headers appear only in expanded state (opacity: 0 → 1)

**Visual structure (collapsed):**
```
┌────────┐
│  logo  │  ← ALIS logomark only (no text)
├────────┤
│  [ic]  │  ← nav icon, 40×40px touch target
│  [ic]  │
│  [ic]  │
│        │  ← section gap
│  [ic]  │
└────────┘
│  [av]  │  ← user avatar at bottom
```

**Visual structure (expanded):**
```
┌────────────────────┐
│  ALIS OS           │  ← full logo with wordmark
│  QUAICU Demo       │
├────────────────────┤
│  PLATFORM          │  ← section header (small caps, muted)
│  [ic] Dashboard    │
│  [ic] Institution  │
│                    │
│  MODULES           │
│  [ic] Admissions   │
└────────────────────┘
│  [av] Dr. Meenakshi│  ← user name + role badge
│       REGISTRAR    │
```

**Implementation notes:**
- Use `group` Tailwind pattern or direct CSS `:hover` on the nav element to trigger expansion
- Icons: use `lucide-react` — import individual icons by name
- The nav sections and items come from `ROLE_NAV[role]` — render only the sections for the logged-in role
- Bottom of nav: user avatar (initials circle, green-100 bg, green-700 text), name, role label

### 5.3 `AgentRail.tsx`

This is a **skeleton/placeholder with role-aware quick-action chips**. It is NOT a functional AI chat yet — that comes in a future task. Build the structure correctly so it can be wired later.

**Layout:**
```
┌─────────────────────────────┐
│  ALIS Assistant      [×]    │  ← header, 48px
│  HOD — CS Department        │
├─────────────────────────────┤
│                             │
│  ┌─────────────────────┐   │
│  │  AI is ready        │   │  ← empty state illustration (simple)
│  │  Ask anything about │   │
│  │  your department    │   │
│  └─────────────────────┘   │
│                             │
│  Quick actions:             │  ← section label
│  [Shortfall list] [IA marks]│  ← chips from ROLE_AGENT_CHIPS[role]
│  [CO attainment] [Workload] │
│                             │
├─────────────────────────────┤
│  [Type a message...    ] [↑]│  ← input, disabled — shows "Coming soon"
└─────────────────────────────┘
```

**Behaviour:**
- Chips are clickable — on click, populate the input field with `chip.prompt` text
- Input is disabled for now — clicking it shows a tooltip: "AI chat coming soon"
- The role description in the header changes per role (e.g. "HOD — CS Department")
- Chips come from `ROLE_AGENT_CHIPS[role]` — render all 4 chips for the role
- Empty state text is role-specific: `"Ask anything about your ${ROLE_DISPLAY[role].description.toLowerCase()}"`

---

## 6. RoleDashboard Component

`src/components/dashboard/RoleDashboard.tsx`

```tsx
import { useALISRole } from '@/hooks/useALISRole';
import { SuperAdminDashboard }  from '@/pages/dashboards/SuperAdminDashboard';
import { RegistrarDashboard }   from '@/pages/dashboards/RegistrarDashboard';
import { DeanDashboard }        from '@/pages/dashboards/DeanDashboard';
import { HODDashboard }         from '@/pages/dashboards/HODDashboard';
import { FacultyDashboard }     from '@/pages/dashboards/FacultyDashboard';
import { StudentDashboard }     from '@/pages/dashboards/StudentDashboard';
import { FinanceDashboard }     from '@/pages/dashboards/FinanceDashboard';
import { CoEDashboard }         from '@/pages/dashboards/CoEDashboard';
import { HRDashboard }          from '@/pages/dashboards/HRDashboard';

const DASHBOARD_MAP = {
  SUPER_ADMIN:     SuperAdminDashboard,
  REGISTRAR:       RegistrarDashboard,
  DEAN:            DeanDashboard,
  HOD:             HODDashboard,
  FACULTY:         FacultyDashboard,
  STUDENT:         StudentDashboard,
  FINANCE_OFFICER: FinanceDashboard,
  COE:             CoEDashboard,
  HR_MANAGER:      HRDashboard,
};

export function RoleDashboard() {
  const { role } = useALISRole();
  const Dashboard = DASHBOARD_MAP[role];
  if (!Dashboard) return <div>Unknown role: {role}</div>;
  return <Dashboard />;
}
```

---

## 7. Dashboard Page Structure

Every dashboard page follows this layout pattern:

```
Page
├── DashboardHeader       ← title, date, primary CTA buttons
├── MetricsRow            ← 4 MetricCard components in a grid (always 4)
├── [AlertBars]           ← 0-2 urgent alerts, only if data warrants
├── PrimaryContent        ← usually full-width approval queue or action list
└── SecondaryContent      ← usually 2-column: left card + right card
```

**DashboardHeader pattern:**
```tsx
<header style={{ padding: '16px 20px', background: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
  <div>
    <h1 style={{ fontSize: '18px', fontWeight: 500, color: 'var(--color-text-primary)' }}>{title}</h1>
    <p style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: 2 }}>{subtitle}</p>
  </div>
  <div style={{ display: 'flex', gap: 8 }}>
    {actions}
  </div>
</header>
```

**Content area:**
```tsx
<div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
  {/* 4 metric cards */}
  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
    ...
  </div>
  {/* rest of content */}
</div>
```

---

## 8. Dashboard Specifications — All 9 Roles

### 8.1 Super Admin Dashboard (`SuperAdminDashboard.tsx`)

**Data strategy: MOCK DATA with TODO comments**

**Title:** Institution Overview  
**Subtitle:** QUAICU Demo Institution · {current date}  
**Header CTAs:** "Export Report" | "+ System Settings"

**Metric Cards (4):**
1. Total Students — `6,412` — "+4.2% this cycle" (positive)
2. Active Faculty — `341` — "Filled / Sanctioned: 94%" (neutral)
3. Open Approvals — `47` — "Across all modules" (urgent=true)
4. System Health — `99.2%` — "All 15 containers healthy" (positive)

**Primary Card — Pending Approvals (All Modules):**
Section title: "Pending Approvals — All Modules" | Action: "View all"
Queue items (show approve/reject buttons):
- TAG: `M1` | Title: "47 applications awaiting eligibility decision" | Sub: "Batch 2026-27 · Stage 4 — Eligibility Screening" | Meta: "Admissions Module · AI evaluated all 47 · Human approval required" | Status: pending
- TAG: `M4` | Title: "3 scholarship disbursement requests" | Sub: "Dean approval received · ₹2.4L total" | Meta: "Finance Module · FM-2 Scholarships · Awaiting Finance Officer release" | Status: review
- TAG: `M6` | Title: "Hall ticket batch ready for CoE approval" | Sub: "6,412 students · Semester 6 End-Sem" | Meta: "Examinations Module · Eligibility + dues auto-verified" | Status: pending
- TAG: `M8` | Title: "2 faculty appointment letters pending VC sign-off" | Sub: "Assistant Professor — CS Dept · UGC-NET qualified" | Meta: "HR Module · Selection committee recommended" | Status: urgent

**Two-column secondary:**

Left — Module Health:
```
// TODO: GET /api/v1/admin/module-health or equivalent
Section title: "Module Health"
Progress rows:
- "Admissions pipeline" 78
- "Fee collection"      91
- "NAAC data readiness" 90
- "Payroll cycle"       62  variant=warn
- "Exam preparation"    44  variant=warn
- "Grievances resolved" 87
```

Right — Domain Events (last 1hr):
```
// TODO: GET /api/v1/admin/events/recent
Section title: "Domain Events — Last 1hr"
Timeline items (done=true means event already fired):
- "student.enrolled fired" / "12 new enrollments processed" / done
- "fee.payment_received" / "₹4.2L collected — 23 receipts generated" / done
- "attendance.semester_final" / "CS Batch 2024 eligibility locked" / done
- "exam.hall_ticket_approved" / "Pending CoE confirmation" / not done
- "payroll.cycle_initiated" / "January 2026 — 340 staff" / not done
```

**Compliance Alerts (below two-col):**
```
Section title: "Compliance Alerts"
AlertBar warn:    "UGC fee schedule not yet published for 2026-27 intake"
AlertBar danger:  "NAAC AQAR submission due in 14 days — 10% gap remaining"
AlertBar info:    "AISHE data window opens October — 8 months ahead"
AlertBar success: "DPDP consent coverage: 100% of all enrolled students"
```

---

### 8.2 Registrar Dashboard (`RegistrarDashboard.tsx`)

**Data strategy: WIRE TO REAL API — already has 2 calls. Preserve existing calls, add structure around them.**

Before rebuilding, read the existing `RegistrarDashboard` file carefully. Identify:
1. What API calls already exist (approvals + KPIs per the page audit)
2. What data they return
3. Build the new layout to display that data + fill gaps with mock

**Title:** Registrar Workspace  
**Subtitle:** QUAICU Demo Institution · Admissions · Academics · Compliance  
**Header CTAs:** "Generate Report" | "Issue Letter"

**Metric Cards (4) — wire to existing KPI call:**
```
// TODO: GET /api/v1/registrar/kpis or existing endpoint — check current file
1. Applications      → from API or mock: "1,311" / "47 need decision today" (urgent)
2. Offers Issued     → from API or mock: "214" / "89 payments confirmed — 41.6%"
3. Enrollment Pending→ from API or mock: "23" / "Originals verification outstanding" (urgent)
4. NAAC Readiness    → from API or mock: "90%" / "C1–C7 data current"
```

**Primary Card — Eligibility Decisions Queue:**
```
// Wire to existing approvals call in current RegistrarDashboard
// TODO: GET /api/v1/approvals/pending?module=admissions or equivalent
Section title: "Eligibility Decisions — Awaiting Approval" | Action: "Batch approve"
Items (show approve + reject buttons):
- TAG: APP | Title: "APP-2026-004821 · Preethi Sundaram" | Sub: "AI: ELIGIBLE · CSE B.Tech · JEE Score 187 · Category OBC-NCL" | Meta: "All criteria met · Policy v2.3 · Documents: Complete" | Status: review
- TAG: APP | Title: "APP-2026-004798 · Rahul Menon" | Sub: "AI: BORDERLINE · Civil Engg · 60.1% vs 60.0% cutoff" | Meta: "1 mark above threshold — manual confirm requested" | Status: pending
- TAG: APP | Title: "APP-2026-004755 · Sneha Pillai" | Sub: "AI: INELIGIBLE · MBA · CAT score 54 vs 60 minimum" | Meta: "Shortfall of 6 percentile points · No relaxation applicable" | Status: urgent
- TAG: APP | Title: "APP-2026-004731 · Arjun Das" | Sub: "AI: ELIGIBLE · M.Tech · GATE 712 · Category SC" | Meta: "Relaxation applied correctly · 1 document pending" | Status: review
```

**Two-column secondary:**

Left — Enrollment Queue:
```
// TODO: GET /api/v1/admissions/enrollment/pending
Items (view only):
- TAG: EN | "Divya Krishnan · CS21B412" / "Originals submitted — awaiting Registrar clearance" / "Roll No. pending" | pending
- TAG: EN | "Vikram Iyer · ME21B089" / "Medical certificate missing — reminded 2x WhatsApp" / "SLA: 2 days remaining" | urgent
- TAG: EN | "Pooja Nair · MBA24A031" / "All docs verified · Roll No. ready to assign" / "Awaiting final confirmation" | review
```

Right — Result Publication Queue:
```
// TODO: GET /api/v1/examinations/results/pending-publication
Items (approve only):
- TAG: RES | "Semester 5 — CS Batch 2022" / "SGPA/CGPA computed for 187 students · Grade cards generated" / "Awaiting Registrar signature" | pending
- TAG: RES | "Supplementary Nov 2025" / "27 students · All marks entered and moderated" / "Ready to publish" | review
```

---

### 8.3 Dean Dashboard (`DeanDashboard.tsx`)

**Data strategy: MOCK DATA with TODO comments**

**Title:** Dean — Academic & Student Affairs  
**Subtitle:** Cross-department oversight · QUAICU Demo Institution  
**Header CTAs:** "Convene Committee" | "Issue Directive"

**Metric Cards (4):**
1. Departments — `11` — "All HODs reporting" (neutral)
2. Escalated to Me — `5` — "From HODs and Registrar" (urgent)
3. Scholarship Pending — `3` — "₹3.8L total disbursement" (urgent)
4. Faculty Vacancies — `8` — "Active recruitment: 3" (urgent)

**Primary Card — Escalated Approvals:**
```
// TODO: GET /api/v1/approvals/escalated?escalated_to=DEAN
Section title: "Escalated Approvals — Your Queue" | Action: "View escalation log"
Items (approve + reject):
- TAG: ESC | "Timetable conflict — MBA & CS overlap" / "HOD CS escalated: Room 204 double-booked Wed 10–11 AM" / "Escalated 3hrs ago · SLA: 6hrs remaining" | urgent
- TAG: ESC | "Faculty appointment — Asst. Prof. Electronics" / "Selection committee recommendation ready for Dean sign-off" / "Dr. Raghavan · UGC-NET qualified · PhD IIT Bombay" | review
- TAG: ESC | "Grade moderation appeal — CS3201" / "HOD requests Dean review of faculty-set cutoff" / "3 students borderline · Policy allows ±2 marks" | pending
- TAG: ESC | "Scholarship disbursement — SC/ST Special Fund" / "₹1.2L · 4 students · All endorsed by faculty advisors" / "Finance awaiting Dean approval" | review
- TAG: ESC | "Disciplinary case — Hostel incident 12-Jan" / "Hostel Warden escalated to Dean of Student Affairs" / "Preliminary report attached" | urgent
```

**Two-column secondary:**

Left — Department Performance:
```
// TODO: GET /api/v1/academics/departments/performance
Section title: "Department Performance"
Progress rows:
- "CS — Attendance avg"        82
- "Electronics — Attendance"   78
- "MBA — Attendance avg"       74  warn
- "Civil — Attendance avg"     69  danger
- "Mechanical — Pass %"        88
- "CS — OBE CO attainment"     76  warn
```

Right — Recent Academic Committee Actions:
```
// TODO: GET /api/v1/academics/committee/actions/recent
Section title: "Recent Academic Committee Actions"
Timeline:
- "Curriculum revision — CS B.Tech approved" / "4 courses updated for 2026-27" / done
- "NBA self-assessment initiated — CS program" / "HOD submitted SAR draft" / done
- "Faculty development programme scheduled" / "March 15–17 · 34 faculty registered" / done
- "Progression decision — Detained students" / "8 students detained · Letters issued" / done
- "CO-PO mapping review pending" / "Electronics HOD response awaited" / not done
```

---

### 8.4 HOD Dashboard (`HODDashboard.tsx`)

**Data strategy: WIRE TO REAL API — already has 3 calls. Read existing file, preserve calls.**

**Title:** HOD — Computer Science  
**Subtitle:** 34 faculty · 680 students · Semester 6  
**Header CTAs:** "Export Dept Report" | "Raise Escalation"

**Metric Cards (4) — wire to existing workload/risk call:**
```
// Wire to existing HODDashboard API call — check current file
1. Students at Risk    → from API: "23" / "Below 75% attendance" (urgent)
2. Shortfall Letters   → from API: "21" / "Auto-dispatched today"
3. IA Marks Pending    → from API: "4" / "Faculty SLA: 2 days" (urgent)
4. NAAC Export         → mock: "Ready" / "40-second AQAR export available"
```

**Primary Card — Faculty Approval Queue:**
```
// TODO: GET /api/v1/approvals/pending?module=academics&approver_role=HOD
Section title: "Faculty Approval Queue" | Action: "Approve all low-risk"
Items (approve + reject):
- TAG: FA | "Course Outline — CS3201 Data Structures" / "Submitted by Prof. Ramesh Kumar · Week 1–15 plan" / "Review & approve to unlock student handbook" | pending
- TAG: FA | "IA Question Paper — CS3401 DBMS" / "Dr. Priya Menon · Internal Assessment 2" / "For HOD verification before sending to Exam Cell" | review
- TAG: FA | "Attendance — Rahul Sharma (CS21B112)" / "4 consecutive absences · Counselling referral recommended" / "Medical grounds — special handling flagged" | pending
- TAG: FA | "Substitution request — Dr. Nair" / "Away Jan 16–18 · Dr. Krishnan available for CS3201" / "Timetable conflict check: Clear" | review
```

**Two-column secondary:**

Left — Attendance Shortfall (student-level):
```
// Wire to existing at-risk call in current HODDashboard
// TODO: GET /api/v1/academics/attendance/risk?department=CS
Section title: "Attendance Shortfall — CS Dept"
AlertBar danger: "6 students approaching 75% threshold — advisory sent"
Risk rows (name + roll + attendance % + colour dot):
- Ananya Krishnan · CS21B047 → 68% (red)
- Rohan Desai · CS21B093    → 71% (amber)
- Priya Soman · CS21B017    → 72% (amber)
- Akhil Rao · CS21B134      → 74% (amber)
- Divya Menon · CS21B028    → 74% (amber)
- Karthik S · CS21B061      → 75% (green)
```

Right — CO Attainment:
```
// TODO: GET /api/v1/academics/obe/attainment?department=CS&semester=6
Section title: "CO Attainment — Semester 5"
Progress rows:
- "CS3001 — Algorithms"  81
- "CS3101 — OS"          74  warn
- "CS3201 — DBMS"        88
- "CS3301 — CN"          69  danger
- "CS3401 — AI/ML"       76  warn
Footer note (12px muted): "Target: ≥75% attainment per CO · 2 courses below threshold"
```

---

### 8.5 Faculty Dashboard (`FacultyDashboard.tsx`)

**Data strategy: WIRE TO REAL API — already has 3 calls. Read existing file, preserve calls.**

**Title:** Faculty Workspace  
**Subtitle:** 4 courses · 180 students · Semester 6  
**Header CTAs:** "Download Marksheet" | "Mark Attendance"

**Metric Cards (4) — wire to existing courses/at-risk call:**
```
// Wire to existing FacultyDashboard API calls — check current file
1. Today's Classes    → from API or mock: "3" / "Next: CS3201 at 11:00 AM"
2. Pending Approvals  → from API: "6" / "Assignments + grievances" (urgent)
3. Students Below 75% → from API: "8" / "In your courses combined" (urgent)
4. IA 2 Submission    → mock: "Due in 5 days" / "Marks entry open" (urgent)
```

**Two-column primary:**

Left — Today's Schedule:
```
// TODO: GET /api/v1/academics/faculty/schedule?date=today
Section title: "Today's Schedule"
Timeline items:
- "CS3201 — DBMS · Sec A · Room 204" / "9:00–10:00 AM · 43 students · Attendance marked ✓" / done
- "CS3401 — AI/ML · Sec B · Room 301" / "11:00 AM–12:00 PM · 41 students · Upcoming" / not done
- "Lab — CS3201 · Room L4" / "2:00–4:00 PM · 22 students · Lab session" / not done
```

Right — Approval Queue:
```
// Wire to existing FacultyDashboard approvals call
Section title: "Approval Queue"
Items (approve + reject):
- TAG: GR | "Ananya Krishnan — Mark Re-evaluation" / "CS3201 IA1 · Q4 arithmetic check" / "ALIS verified: 4+4+3+3=14 ✓ · No change required" | review
- TAG: AS | "Assignment 3 — DBMS Schema Design" / "AI-generated rubric ready for approval" / "40 students · Due: 20 Jan 2026" | pending
- TAG: GR | "Rohan Desai — Attendance dispute" / "Claims medical leave for 3 sessions Jan 8–10" / "Certificate not yet uploaded" | pending
```

**Full-width bottom card — IA 2 Marks Entry:**
```
// TODO: GET /api/v1/examinations/ia-marks/status?faculty_id={me}&semester=6
Section title: "IA 2 Marks Entry — CS3201 DBMS" | Action: "Open marks sheet"
AlertBar info: "Marks entry open · HOD approval required after submission · SLA: 19 Jan 2026"
Progress rows:
- "Entered"        67
- "Pending entry"  33  warn
Footer: "43 students total · 67% marks entered · Range: 8–19/20"
```

---

### 8.6 Student Dashboard (`StudentDashboard.tsx`)

**Data strategy: WIRE TO REAL API — already has 2 calls. Read existing file, preserve calls.**

**Title:** My Dashboard  
**Subtitle:** {user.name from auth store} · {user.roll_number} · Semester 6  
**Header CTAs:** "Pay Fees" | "Raise Grievance"

**Metric Cards (4) — wire to existing KPI call:**
```
// Wire to existing StudentDashboard calls — check current file
1. Attendance  → from API: "74.3%" / "1 session below threshold — advisory sent" (urgent)
2. CGPA        → from API: "8.2" / "Sem 5 SGPA: 8.4"
3. Fee Due     → from API: "₹0" / "Paid — receipt corrected ✓"
4. Library     → mock: "2 issued" / "Due: 25 Jan 2026"
```

**Full-width alert (conditional — only show if attendance < 75% in any course):**
```
AlertBar warn: "Your attendance in CS3301 (Computer Networks) is at 68% — below the 75% threshold. A shortfall advisory has been sent. Contact your faculty advisor if medical grounds apply."
```

**Two-column primary:**

Left — Today's Classes:
```
// TODO: GET /api/v1/academics/student/schedule?date=today
Section title: "Today's Classes"
Timeline:
- "CS3201 — DBMS · Room 204 · 9 AM" / "Present ✓ · Prof. Ramesh Kumar" / done
- "CS3401 — AI/ML · Room 301 · 11 AM" / "Upcoming · Prof. Arjun Nair" / not done
- "CS3301 — CN · Room 205 · 2 PM" / "Upcoming · Dr. Priya Devi" / not done
```

Right — Course-wise Attendance:
```
// Wire to existing StudentDashboard attendance call
Section title: "Course-wise Attendance"
Progress rows:
- "CS3201 — DBMS"      84
- "CS3401 — AI/ML"     78
- "CS3001 — Algorithms" 81
- "CS3301 — CN"         68  danger
- "CS3101 — OS"         77
```

**Two-column secondary:**

Left — Pending Actions:
```
// TODO: GET /api/v1/students/me/actions/pending
Section title: "Pending Actions"
Items (view only):
- TAG: SCH | "Scholarship Renewal — AICTE Pragati" / "Documents complete · Deadline: 25 Jan 2026" / "Fee receipt corrected — application ready to submit" | review
- TAG: LIB | "Library Book Due — Clean Code" / "Due: 25 Jan 2026 · Fine: ₹0 if returned on time" / "Renew or return" | pending
```

Right — Open Grievances:
```
// TODO: GET /api/v1/students/me/grievances?status=open
Section title: "Open Grievances"
Items (view only):
- TAG: GR | "CS3201 IA1 — Mark Re-evaluation" / "Q4 arithmetic error claim · Submitted 10 Jan" / "Status: ALIS verified — marks correct · Response sent" | review
```

---

### 8.7 Finance Officer Dashboard (`FinanceDashboard.tsx`)

**Data strategy: WIRE TO REAL API — already has 3 calls. Read existing file, preserve calls.**

**Title:** Finance Dashboard  
**Subtitle:** FM-1 through FM-7 · MFA Active · QUAICU Demo Institution  
**Header CTAs:** "Export Ledger" | "Release Payroll"

**Metric Cards (4) — wire to existing defaulters/trend call:**
```
// Wire to existing FinanceDashboard calls — check current file
1. Collected — Jan  → from API or mock: "₹3.42 Cr" / "vs ₹3.21 Cr last Jan" (positive)
2. Overdue Accounts → from API: "1,847" / "1,591 in auto-follow-up" (urgent)
3. Recon Exceptions → from API: "3" / "2 resolved · 1 investigating" (urgent)
4. Payroll — Jan    → mock: "₹68.4L" / "340 staff · Run on 20 Jan"
```

**Primary Card — Approval Queue:**
```
// TODO: GET /api/v1/approvals/pending?approver_role=FINANCE_OFFICER
Section title: "Approval Queue — Finance" | Action: "Batch process"
Items (approve + reject):
- TAG: FEE | "Fee Correction — CS21B047 Ananya Krishnan" / "₹200 discrepancy · Mid-semester fee structure update" / "Correction approved ✓ · Receipt regenerated · DPDP log updated" | active
- TAG: SCH | "Scholarship Disbursement — PM-YASASVI · 4 students" / "₹1.8L total · Eligibility verified · Dean approved" / "Awaiting Finance Officer release" | pending
- TAG: REF | "Refund — Cancelled admission APP-2026-003421" / "₹45,000 · Within 7-day cooling off · Hostel not allotted" / "Refund policy: 90% applicable" | review
- TAG: VEN | "Vendor Invoice — Scientia Labs ₹2.4L" / "Lab consumables · PO-2026-0089 · GRN matched" / "TDS 2% auto-deducted · Net payable: ₹2.35L" | pending
```

**Two-column secondary:**

Left — Bank Reconciliation:
```
// Wire to existing FinanceDashboard reconciliation call
// TODO: GET /api/v1/finance/reconciliation/today
Section title: "Bank Reconciliation — Today"
AlertBar success: "1,821 transactions auto-matched ✓"
Items (view only):
- TAG: REC | "TXN-2026-018821 · ₹12,400" / "Processing delay — expected tomorrow" / "Bank ref: 88B21" | pending
- TAG: REC | "TXN-2026-018799 · ₹8,200" / "Duplicate transaction — flagged" / "Refund initiated automatically" | urgent
- TAG: REC | "TXN-2026-018712 · ₹3,600" / "Under investigation — source unclear" / "Manual review required" | pending
```

Right — Fee Collection Progress:
```
// TODO: GET /api/v1/finance/fee/collection/progress
Section title: "Fee Collection Progress — Sem 6"
Progress rows:
- "B.Tech 4th year"  91
- "B.Tech 3rd year"  87
- "M.Tech"           94
- "MBA"              78  warn
- "Ph.D Scholars"    82
- "B.Tech 1st year"  95
```

---

### 8.8 CoE Dashboard (`CoEDashboard.tsx`)

**Data strategy: WIRE TO REAL API — already has 3 calls. Read existing file, preserve calls.**

**Title:** Controller of Examinations  
**Subtitle:** Semester 6 End-Sem · 6,412 students  
**Header CTAs:** "Download Schedule" | "Approve Hall Tickets"

**Metric Cards (4) — wire to existing paper dispatch/AI scores call:**
```
// Wire to existing ExamControllerDashboard calls — check current file
1. Hall Tickets     → from API or mock: "Ready" / "6,412 · Pending CoE approval" (urgent)
2. Q-Papers Pending → from API: "3" / "47 of 50 submitted to Vault" (urgent)
3. Exam Schedule    → mock: "Approved" / "Jan 28 – Feb 14 2026"
4. Revaluation      → from API or mock: "12 requests" / "Window open until 20 Jan"
```

**Primary Card — Hall Ticket Batch:**
```
// Wire to existing ExamControllerDashboard call
// TODO: GET /api/v1/examinations/hall-tickets/batch/current
Section title: "Hall Ticket Batch — Approval Required" | Action: "Preview batch"
AlertBar info: "ALIS generated 6,412 hall tickets in 4m 12s · Eligibility (attendance + dues) auto-verified against live data"
Items:
- TAG: HT | "6,189 students — Fully eligible" / "Attendance ≥75% · Dues cleared · All docs verified" / "Ready for CoE batch approval → auto-distribute on approval" | review  [show approve button]
- TAG: HT | "198 students — Dues pending watermark" / "Hall ticket generated · 48hr payment window before lock" / "Tickets locked until dues cleared" | pending  [view only]
- TAG: HT | "25 students — Attendance ineligible" / "Below 75% threshold · Shortfall letters issued" / "Cannot receive hall ticket — Registrar escalation path active" | urgent  [view only]
```

**Two-column secondary:**

Left — Question Paper Vault Status:
```
// Wire to existing call or TODO: GET /api/v1/examinations/papers/vault/status
Section title: "Question Paper Vault Status"
Items (view only):
- TAG: QP | "CS3201 — DBMS · Dr. Priya Menon" / "Submitted · AES-256 encrypted · Vault-stored" / "Receipt confirmed by CoE" | active
- TAG: QP | "CS3401 — AI/ML · Prof. Arjun Nair" / "Submitted · Encrypted" / "Awaiting CoE dispatch confirmation" | review
- TAG: QP | "CS3301 — CN · Dr. Hegde" / "NOT SUBMITTED · Reminder sent 3x" / "SLA breach in 6 hours — escalating" | urgent
- TAG: QP | "CS3101 — OS · Prof. Kumar" / "Uploaded via secure mobile — Vault stored" / "Awaiting CoE receipt confirmation" | pending
```

Right — Revaluation Queue:
```
// TODO: GET /api/v1/examinations/revaluation/pending
Section title: "Revaluation Queue"
Items (approve + reject):
- TAG: REV | "Ravi Shankar · CS21B088" / "CS3001 Algorithms · IA3 · Claims 4 marks" / "Re-evaluator: Dr. Nair (blind assignment)" | pending
- TAG: REV | "Meera Pillai · CS21B029" / "CS3201 DBMS · End-sem · 12 marks claimed" / "Re-evaluator assigned · Script dispatched" | review
- TAG: REV | "Kiran Kumar · ME21B041" / "ME3301 Thermodynamics · 8 marks claimed" / "Awaiting re-evaluator response" | pending
```

---

### 8.9 HR Manager Dashboard (`HRDashboard.tsx`)

**Data strategy: MOCK DATA with TODO comments**

**Title:** HR & Payroll Dashboard  
**Subtitle:** 340 staff · January 2026 Payroll Cycle · MFA Active  
**Header CTAs:** "Download Payslips" | "Initiate Payroll"

**Metric Cards (4):**
1. Payroll Exceptions — `3` — "340 auto-computed · 3 need review" (urgent)
2. Leave Approvals — `8` — "Retroactive: 3 · Normal: 5" (neutral)
3. Open Requisitions — `4` — "2 senior · 2 non-teaching" (urgent)
4. CAS Due — `6 faculty` — "Appraisal window open" (urgent)

**Primary Card — Payroll Exceptions:**
```
// TODO: GET /api/v1/hr/payroll/current/exceptions
Section title: "January Payroll — Exceptions Queue" | Action: "Run payroll"
AlertBar info: "340 staff records auto-processed · Biometric + WiFi attendance consolidated · 3 exceptions require your review"
Items (approve + reject):
- TAG: PAY | "Retroactive Leave — Dr. Krishnamurthy (Physics)" / "Absent Dec 28 · Leave balance: 4 days remaining · LOP: Not required" / "ALIS recommendation: Approve retroactive leave" | pending
- TAG: PAY | "PF Formula Error — Prof. Ramesh Kumar (CS)" / "Deduction formula miscalculated for 3 months" / "Correction: ₹2,400 adjustment · 0 other staff affected" | urgent
- TAG: PAY | "Appraisal Increment — Dr. Meena Iyer (MBA)" / "CAS promotion effective Jan 1 · New pay level: 13A" / "Increment: ₹8,400/month · Finance notified" | review
```

**Two-column secondary:**

Left — Recruitment Pipeline:
```
// TODO: GET /api/v1/hr/recruitment/pipeline
Section title: "Recruitment Pipeline"
Items (view only):
- TAG: REC | "Asst. Professor — Electronics Dept" / "JD approved · Ad live on UGC portal" / "Applications: 23 · Shortlist pending HOD review" | pending
- TAG: REC | "Asst. Professor — CS Dept" / "Dr. Raghavan — selection committee recommended" / "Appointment letter pending VC sign-off" | review
- TAG: REC | "Lab Technician — Chemistry" / "Walk-in interviews Jan 20 · 6 candidates" / "Non-teaching post · HR direct appointment" | pending
- TAG: REC | "Visiting Faculty — MBA Finance" / "UGC Draft 2025: max 6 months · Contract ready" / "Guest Lecture rate: ₹1,500/session" | review
```

Right — Statutory Compliance:
```
// TODO: GET /api/v1/hr/compliance/status
Section title: "Statutory Compliance"
Progress rows:
- "EPF deposits — on schedule"  100  success
- "ESI contributions — Jan"     100  success
- "TDS Form 16 — FY25-26"        67  warn
- "CAS appraisals — due faculty"  0  danger
- "Training hours — faculty"     74  warn
- "UGC returns — data readiness" 88
```

---

## 9. Routing Updates

Update `src/routes/index.tsx`. Preserve every existing route. Only change:
1. The `ALISShell` component used to wrap protected routes — use the new rebuilt one
2. The `/dashboard` route — point to `RoleDashboard` instead of whatever exists

```tsx
// The protected route structure should look like:
<Route element={<ProtectedRoute />}>
  <Route element={<ALISShell />}>              {/* NEW rebuilt shell */}
    <Route path="/dashboard" element={<RoleDashboard />} />   {/* NEW */}
    <Route path="/admissions" element={<AdmissionsModulePage />} />  {/* PRESERVE as-is */}
    <Route path="/academics" element={<AcademicsPage />} />          {/* PRESERVE as-is */}
    {/* ... all 40+ other routes preserved exactly as they are ... */}
  </Route>
</Route>
```

Do NOT change the path strings of any existing route. Do NOT change any existing page component. Only replace the shell wrapper and the `/dashboard` component.

---

## 10. Implementation Order

Follow this order exactly. Do not jump ahead.

```
Step 1:  Read ALL existing files before modifying anything
         - src/hooks/useALISRole.ts     — understand what role returns
         - All 6 existing dashboard files with API calls — note every fetch call
         - Current ALISShell, IconNav structure — understand what exists

Step 2:  Create src/styles/tokens.css
         Create src/config/roleConfig.ts

Step 3:  Build src/components/ui/ — all 7 shared components
         Test each component renders correctly in isolation before proceeding

Step 4:  Build src/components/shell/AgentRail.tsx
         Build src/components/shell/IconNav.tsx
         Build src/components/shell/ALISShell.tsx
         Test the 3-column layout at different viewport sizes

Step 5:  Build src/components/dashboard/RoleDashboard.tsx

Step 6:  Build dashboard pages in this order:
         a. StudentDashboard      (simplest — fewest roles/permissions)
         b. FacultyDashboard
         c. HODDashboard
         d. RegistrarDashboard
         e. FinanceDashboard
         f. CoEDashboard
         g. DeanDashboard
         h. HRDashboard
         i. SuperAdminDashboard

Step 7:  Update src/routes/index.tsx

Step 8:  End-to-end test — log in with each demo account, verify correct dashboard loads
```

---

## 11. Demo Accounts

Use these to test each role. These must work with the existing auth flow:

| Role | Email | Password | Expected Dashboard |
|------|-------|----------|--------------------|
| Super Admin | admin@demo.edu | Admin@1234 | SuperAdminDashboard |
| Registrar | registrar@demo.edu | Registrar@1234 | RegistrarDashboard |
| Dean | dean@demo.edu | Dean@1234 | DeanDashboard |
| HOD | hod.cs@demo.edu | HOD@1234 | HODDashboard |
| Faculty | faculty@demo.edu | Faculty@1234 | FacultyDashboard |
| Student | student@demo.edu | Student@1234 | StudentDashboard |
| Finance Officer | finance@demo.edu | Finance@1234 | FinanceDashboard |
| CoE | coe@demo.edu | CoE@1234 | CoEDashboard |
| HR Manager | hr@demo.edu | HR@1234 | HRDashboard |

---

## 12. Non-Negotiable Rules

1. **Never hardcode hex colours in components.** Use only CSS variables from tokens.css.
2. **Never import from another dashboard file.** Each dashboard is self-contained.
3. **Preserve every existing API call** in the 6 dashboards that already have them.
4. **Add `// TODO: GET /api/v1/...` comments** above every mock data block.
5. **Never modify auth files** — authService, useAuthStore, ProtectedRoute.
6. **All icons from `lucide-react`** — no other icon library.
7. **No external UI libraries** beyond what is already installed (Tailwind, Radix, Zustand, React Router).
8. **AgentRail input stays disabled** — do not build functional AI chat.
9. **TypeScript strict** — no `any` types. All props explicitly typed.
10. **Mobile consideration** — the shell should be usable at 768px min width. IconNav collapses fully below 768px (show a hamburger or hide it).

---

## 13. Verification Checklist

Before marking this task complete, verify every item:

```
□ Login as each of the 9 demo accounts — correct dashboard loads for each
□ IconNav shows only role-specific nav items for each role
□ IconNav expands smoothly on hover — collapses on mouse leave
□ Badges on nav items are visible in both collapsed and expanded state
□ AgentRail shows correct 4 chips for each role
□ AgentRail chip click populates the input field
□ All 4 MetricCard values are present on every dashboard
□ Approval queues show Approve + Reject buttons where specified
□ View-only queue items show only View button
□ No TypeScript errors (run tsc --noEmit)
□ No console errors on any dashboard
□ Existing API calls in 6 dashboards still work (check Network tab)
□ All existing 40+ routes still render (no 404s)
□ No auth flow broken — 401 interceptor still works
□ Page does not scroll as a whole — each column scrolls independently
□ Colour is green + white throughout — no navy or blue as primary
□ Institution name "QUAICU Demo Institution" appears in shell/header
□ All mock data blocks have // TODO: GET /api/v1/... comments
```

---

*ALIS OS Frontend Spec v1.0 — QUAICU Solutions Private Limited*  
*Generated: April 2026 | For Claude Code use only*
