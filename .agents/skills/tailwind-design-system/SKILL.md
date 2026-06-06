---
name: tailwind-design-system
description: "Build production-ready design systems with Tailwind CSS, including design tokens, component variants, responsive patterns, and accessibility. QUAICU kernel — fixed ActionState color tokens (denied/halted always distinct from allowed/completed, never color-only), state badges with icon plus label, ledger hash cells, WCAG AA in light and dark, 44px approve/reject targets. Triggers — QUAICU, ActionState color token, state badge, ledger hash cell, dark mode, accessibility."
risk: safe
source: community
date_added: "2026-02-27"
---

# Tailwind Design System

## ⚡ QUAICU Decision Contract — READ THIS FIRST (when used for the QUAICU kernel)

> Makes the QUAICU-specific design-token choices mechanical so a small/low-token model matches a top model at max effort.
> **For QUAICU work, this block overrides the general guidance below.**

### Invariants — never violated
- Map each `ActionState` to its fixed semantic token — use these exactly, in light AND dark mode: DENIED=red-600, HALTED=red-900, PENDING_APPROVAL=amber-500, ALLOWED/APPROVED=green-600, COMPLETED=green-700, SEALED=blue-600, CANCELLED=slate-400, PROPOSED/EVALUATING/EXECUTING=neutral in-progress.
- A denied/halted state is ALWAYS visually distinct from allowed/completed (never the same hue). Color is never the ONLY signal — pair with an icon + text label (color-blind safe).
- Meet WCAG AA contrast in both themes; dark mode is first-class (compliance officers run long sessions).
- Approve/reject controls have a ≥44px touch target and an explicit confirm step.

### Decision table
| Element | Rule |
|---|---|
| State badge | semantic token + icon + text label |
| Ledger hash cell | monospace, click-to-copy, truncated with tooltip |
| Destructive / approve action | 44px target, confirm dialog with comment field |
| Print styles | states remain distinguishable in grayscale |

### Tie-break rules
- Reuse one color for two states to simplify the palette? → never; denied vs allowed must be unambiguous.
- Color alone to convey state? → no; always add icon/text.

### Self-check
- [ ] Every ActionState mapped to its fixed token in light + dark.
- [ ] Denied/halted visually distinct; never color-only.
- [ ] WCAG AA contrast both themes; 44px approve/reject targets.
- [ ] Hashes monospace + copyable; grayscale-safe.

---

Build production-ready design systems with Tailwind CSS, including design tokens, component variants, responsive patterns, and accessibility.

## Use this skill when

- Creating a component library with Tailwind
- Implementing design tokens and theming
- Building responsive and accessible components
- Standardizing UI patterns across a codebase
- Migrating to or extending Tailwind CSS
- Setting up dark mode and color schemes

## Do not use this skill when

- The task is unrelated to tailwind design system
- You need a different domain or tool outside this scope

## Instructions

- Clarify goals, constraints, and required inputs.
- Apply relevant best practices and validate outcomes.
- Provide actionable steps and verification.
- If detailed examples are required, open `resources/implementation-playbook.md`.

## Resources

- `resources/implementation-playbook.md` for detailed patterns and examples.

## Limitations
- Use this skill only when the task clearly matches the scope described above.
- Do not treat the output as a substitute for environment-specific validation, testing, or expert review.
- Stop and ask for clarification if required inputs, permissions, safety boundaries, or success criteria are missing.

---

## QUAICU-Specific Application

### Governance Design Token System

The QUAICU admin console serves compliance officers and regulators. The design system must prioritize legibility of dense audit data, unambiguous decision states, WCAG 2.1 AA contrast at minimum (AAA preferred for decision-critical colors), and a dark mode that reduces eye strain for extended audit sessions.

All tokens live in `tailwind.config.ts` under `theme.extend.colors` and `theme.extend.cssVars`. CSS custom properties are used so that dark mode simply reassigns the variables — component class names never change between modes.

#### Color Semantics — ActionState to Visual Token Mapping

The spec defines a finite set of `ActionState` values for the lifecycle (`PROPOSED → EVALUATING → PENDING_APPROVAL → APPROVED → EXECUTING → EXECUTED → DENIED → HALTED → SEALED → CANCELLED → COMPLETED`). Each state maps to exactly one semantic color. These mappings are canonical — any component that displays state must use these tokens, never raw Tailwind palette colors.

| ActionState | Tailwind token family | Light base color | Dark base color | Rationale |
|-------------|----------------------|-----------------|-----------------|-----------|
| `DENIED` | `decision-denied` | `red-600` (#dc2626) | `red-400` (#f87171) | Danger: action was rejected by policy |
| `ALLOWED` / `APPROVED` | `decision-allowed` | `green-600` (#16a34a) | `green-400` (#4ade80) | Success: action cleared governance |
| `PENDING_APPROVAL` | `decision-pending` | `amber-500` (#f59e0b) | `amber-400` (#fbbf24) | Caution: awaiting human decision |
| `SEALED` | `decision-sealed` | `blue-600` (#2563eb) | `blue-400` (#60a5fa) | Finality: immutably recorded in TrustLedger |
| `HALTED` | `decision-halted` | `red-900` (#7f1d1d) | `red-300` (#fca5a5) | Critical: lifecycle halted, requires intervention |
| `COMPLETED` | `decision-completed` | `green-700` (#15803d) | `green-300` (#86efac) | Terminal success: governed action fully complete |
| `CANCELLED` | `decision-cancelled` | `slate-400` (#94a3b8) | `slate-500` (#64748b) | Neutral: action withdrawn before completion |
| `PROPOSED` | `decision-proposed` | `slate-600` (#475569) | `slate-400` (#94a3b8) | Neutral: submitted, not yet evaluated |
| `EVALUATING` | `decision-evaluating` | `blue-500` (#3b82f6) | `blue-400` (#60a5fa) | In-progress: policy engine running |
| `EXECUTING` | `decision-executing` | `violet-500` (#8b5cf6) | `violet-400` (#a78bfa) | In-progress: state transition running |

**Rule:** never use `red-600` directly for a denied state — use `text-decision-denied-text` / `bg-decision-denied-bg`. Raw palette colors break dark mode, mean nothing to the next developer, and make global contrast audits impossible.

#### Token definitions (`tailwind.config.ts`)

```typescript
import type { Config } from 'tailwindcss';

export default {
  content: ['./src/**/*.{ts,tsx}'],
  darkMode: 'class',   // toggled by adding 'dark' to <html>

  theme: {
    extend: {
      colors: {
        // ── Decision state palette ─────────────────────────────────────────
        // Semantically named; never use raw hex in components.
        // Contrast ratios verified against both light and dark backgrounds.
        decision: {
          // ALLOWED / EXECUTED — green
          // Light: #166534 on #f0fdf4 = 7.1:1 (AAA) · Dark: #4ade80 on #052e16 = 8.0:1
          allowed: {
            DEFAULT: 'var(--color-decision-allowed)',
            bg:      'var(--color-decision-allowed-bg)',
            border:  'var(--color-decision-allowed-border)',
            text:    'var(--color-decision-allowed-text)',
          },
          // DENIED / REJECTED — red
          // Light: #991b1b on #fef2f2 = 6.9:1 (AAA) · Dark: #f87171 on #450a0a = 7.5:1
          denied: {
            DEFAULT: 'var(--color-decision-denied)',
            bg:      'var(--color-decision-denied-bg)',
            border:  'var(--color-decision-denied-border)',
            text:    'var(--color-decision-denied-text)',
          },
          // PENDING / PENDING_APPROVAL — amber
          // Light: #92400e on #fffbeb = 7.0:1 (AAA) · Dark: #fbbf24 on #451a03 = 7.2:1
          pending: {
            DEFAULT: 'var(--color-decision-pending)',
            bg:      'var(--color-decision-pending-bg)',
            border:  'var(--color-decision-pending-border)',
            text:    'var(--color-decision-pending-text)',
          },
          // SEALED / IMMUTABLE LEDGER STATE — blue
          // Light: #1e3a5f on #eff6ff = 9.1:1 (AAA) · Dark: #60a5fa on #0c1a2e = 8.3:1
          sealed: {
            DEFAULT: 'var(--color-decision-sealed)',
            bg:      'var(--color-decision-sealed-bg)',
            border:  'var(--color-decision-sealed-border)',
            text:    'var(--color-decision-sealed-text)',
          },
          // HALTED / ERROR — deep red (distinct from denied red)
          halted: {
            DEFAULT: 'var(--color-decision-halted)',
            bg:      'var(--color-decision-halted-bg)',
            border:  'var(--color-decision-halted-border)',
            text:    'var(--color-decision-halted-text)',
          },
          // COMPLETED — darker green (terminal success, distinct from allowed)
          completed: {
            DEFAULT: 'var(--color-decision-completed)',
            bg:      'var(--color-decision-completed-bg)',
            border:  'var(--color-decision-completed-border)',
            text:    'var(--color-decision-completed-text)',
          },
          // CANCELLED — slate/neutral (withdrawn, not a failure)
          cancelled: {
            DEFAULT: 'var(--color-decision-cancelled)',
            bg:      'var(--color-decision-cancelled-bg)',
            border:  'var(--color-decision-cancelled-border)',
            text:    'var(--color-decision-cancelled-text)',
          },
          // PROPOSED / EVALUATING / EXECUTING — in-progress neutrals/blue/violet
          proposed: {
            DEFAULT: 'var(--color-decision-proposed)',
            bg:      'var(--color-decision-proposed-bg)',
            text:    'var(--color-decision-proposed-text)',
          },
          evaluating: {
            DEFAULT: 'var(--color-decision-evaluating)',
            bg:      'var(--color-decision-evaluating-bg)',
            text:    'var(--color-decision-evaluating-text)',
          },
          executing: {
            DEFAULT: 'var(--color-decision-executing)',
            bg:      'var(--color-decision-executing-bg)',
            text:    'var(--color-decision-executing-text)',
          },
        },

        // ── Governance surface palette ─────────────────────────────────────
        governance: {
          surface:     'var(--color-governance-surface)',
          'surface-alt':'var(--color-governance-surface-alt)',
          border:      'var(--color-governance-border)',
          hover:       'var(--color-governance-hover)',
          muted:       'var(--color-governance-muted)',
          label:       'var(--color-governance-label)',
          link:        'var(--color-governance-link)',
        },
      },

      fontFamily: {
        // Audit tables use a monospaced font for ledger_seq, hashes, and timestamps.
        // Proportional sans for prose and labels.
        sans:  ['Inter', 'system-ui', 'sans-serif'],
        mono:  ['JetBrains Mono', 'ui-monospace', 'monospace'],
        audit: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },

      fontSize: {
        // Dense table sizes — readable without being cramped in 80-column audit layouts
        'audit-xs': ['0.6875rem', { lineHeight: '1rem',   letterSpacing: '0.01em' }],
        'audit-sm': ['0.75rem',   { lineHeight: '1.125rem', letterSpacing: '0.005em' }],
        'audit-base': ['0.8125rem', { lineHeight: '1.25rem' }],
      },
    },
  },
  plugins: [],
} satisfies Config;
```

#### CSS custom properties (`globals.css`)

```css
/* Light mode — default */
:root {
  /* Decision: ALLOWED */
  --color-decision-allowed:        #166534;
  --color-decision-allowed-bg:     #f0fdf4;
  --color-decision-allowed-border: #86efac;
  --color-decision-allowed-text:   #166534;

  /* Decision: DENIED */
  --color-decision-denied:         #991b1b;
  --color-decision-denied-bg:      #fef2f2;
  --color-decision-denied-border:  #fca5a5;
  --color-decision-denied-text:    #991b1b;

  /* Decision: PENDING */
  --color-decision-pending:        #92400e;
  --color-decision-pending-bg:     #fffbeb;
  --color-decision-pending-border: #fcd34d;
  --color-decision-pending-text:   #92400e;

  /* Decision: SEALED */
  --color-decision-sealed:         #1e3a5f;
  --color-decision-sealed-bg:      #eff6ff;
  --color-decision-sealed-border:  #93c5fd;
  --color-decision-sealed-text:    #1e3a5f;

  /* Decision: HALTED (red-900 family — more severe than DENIED) */
  --color-decision-halted:         #7f1d1d;
  --color-decision-halted-bg:      #fef2f2;
  --color-decision-halted-border:  #f87171;
  --color-decision-halted-text:    #7f1d1d;

  /* Decision: COMPLETED (green-700 — terminal, darker than ALLOWED) */
  --color-decision-completed:      #15803d;
  --color-decision-completed-bg:   #f0fdf4;
  --color-decision-completed-border:#86efac;
  --color-decision-completed-text: #15803d;

  /* Decision: CANCELLED (slate-400 — neutral, not a failure) */
  --color-decision-cancelled:      #64748b;
  --color-decision-cancelled-bg:   #f8fafc;
  --color-decision-cancelled-border:#cbd5e1;
  --color-decision-cancelled-text: #64748b;

  /* Decision: PROPOSED / EVALUATING / EXECUTING — in-progress */
  --color-decision-proposed:       #475569;
  --color-decision-proposed-bg:    #f8fafc;
  --color-decision-proposed-text:  #475569;
  --color-decision-evaluating:     #1d4ed8;
  --color-decision-evaluating-bg:  #eff6ff;
  --color-decision-evaluating-text:#1d4ed8;
  --color-decision-executing:      #6d28d9;
  --color-decision-executing-bg:   #f5f3ff;
  --color-decision-executing-text: #6d28d9;

  /* Governance surfaces */
  --color-governance-surface:      #ffffff;
  --color-governance-surface-alt:  #f8fafc;
  --color-governance-border:       #e2e8f0;
  --color-governance-hover:        #f1f5f9;
  --color-governance-muted:        #64748b;
  --color-governance-label:        #334155;
  --color-governance-link:         #2563eb;
}

/* Dark mode — class strategy */
.dark {
  /* Decision: ALLOWED */
  --color-decision-allowed:        #4ade80;
  --color-decision-allowed-bg:     #052e16;
  --color-decision-allowed-border: #166534;
  --color-decision-allowed-text:   #4ade80;

  /* Decision: DENIED */
  --color-decision-denied:         #f87171;
  --color-decision-denied-bg:      #450a0a;
  --color-decision-denied-border:  #991b1b;
  --color-decision-denied-text:    #f87171;

  /* Decision: PENDING */
  --color-decision-pending:        #fbbf24;
  --color-decision-pending-bg:     #451a03;
  --color-decision-pending-border: #92400e;
  --color-decision-pending-text:   #fbbf24;

  /* Decision: SEALED */
  --color-decision-sealed:         #60a5fa;
  --color-decision-sealed-bg:      #0c1a2e;
  --color-decision-sealed-border:  #1e3a5f;
  --color-decision-sealed-text:    #60a5fa;

  /* Decision: HALTED — lighter red on very dark bg for contrast */
  --color-decision-halted:         #fca5a5;
  --color-decision-halted-bg:      #1c0505;
  --color-decision-halted-border:  #7f1d1d;
  --color-decision-halted-text:    #fca5a5;

  /* Decision: COMPLETED */
  --color-decision-completed:      #86efac;
  --color-decision-completed-bg:   #022c22;
  --color-decision-completed-border:#15803d;
  --color-decision-completed-text: #86efac;

  /* Decision: CANCELLED */
  --color-decision-cancelled:      #94a3b8;
  --color-decision-cancelled-bg:   #1e293b;
  --color-decision-cancelled-border:#475569;
  --color-decision-cancelled-text: #94a3b8;

  /* Decision: in-progress */
  --color-decision-proposed:       #94a3b8;
  --color-decision-proposed-bg:    #1e293b;
  --color-decision-proposed-text:  #94a3b8;
  --color-decision-evaluating:     #93c5fd;
  --color-decision-evaluating-bg:  #0c1a2e;
  --color-decision-evaluating-text:#93c5fd;
  --color-decision-executing:      #c4b5fd;
  --color-decision-executing-bg:   #1e1030;
  --color-decision-executing-text: #c4b5fd;

  /* Governance surfaces */
  --color-governance-surface:      #0f172a;
  --color-governance-surface-alt:  #1e293b;
  --color-governance-border:       #334155;
  --color-governance-hover:        #1e293b;
  --color-governance-muted:        #94a3b8;
  --color-governance-label:        #e2e8f0;
  --color-governance-link:         #60a5fa;
}
```

### ActionStateBadge Component (Full Lifecycle)

The `ActionStateBadge` maps every `ActionState` enum value from the kernel spec to a styled pill. It is the canonical component for displaying state anywhere in the admin console — ledger tables, HITL queue cards, dashboard summaries. The `aria-label` provides the full human-readable state name so color is never the sole indicator (WCAG 1.4.1).

```typescript
// types/quaicu.ts
export type ActionState =
  | 'PROPOSED'
  | 'EVALUATING'
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'EXECUTING'
  | 'EXECUTED'
  | 'DENIED'
  | 'HALTED'
  | 'SEALED'
  | 'COMPLETED'
  | 'CANCELLED';
```

```typescript
// components/ActionStateBadge.tsx
import type { ActionState } from '@/types/quaicu';

// Tailwind class strings composed from semantic tokens — never raw palette colors.
// Adding a new ActionState requires: (1) add to this map, (2) add CSS vars,
// (3) update print styles, (4) run contrast audit.
const STATE_CLASSES: Record<ActionState, string> = {
  PROPOSED:
    'bg-decision-proposed-bg text-decision-proposed-text border-governance-border',
  EVALUATING:
    'bg-decision-evaluating-bg text-decision-evaluating-text border-decision-evaluating',
  PENDING_APPROVAL:
    'bg-decision-pending-bg text-decision-pending-text border-decision-pending-border',
  APPROVED:
    'bg-decision-allowed-bg text-decision-allowed-text border-decision-allowed-border',
  EXECUTING:
    'bg-decision-executing-bg text-decision-executing-text border-decision-executing',
  EXECUTED:
    'bg-decision-allowed-bg text-decision-allowed-text border-decision-allowed-border',
  DENIED:
    'bg-decision-denied-bg text-decision-denied-text border-decision-denied-border',
  HALTED:
    'bg-decision-halted-bg text-decision-halted-text border-decision-halted-border',
  SEALED:
    'bg-decision-sealed-bg text-decision-sealed-text border-decision-sealed-border',
  COMPLETED:
    'bg-decision-completed-bg text-decision-completed-text border-decision-completed-border',
  CANCELLED:
    'bg-decision-cancelled-bg text-decision-cancelled-text border-decision-cancelled-border',
};

const STATE_LABEL: Record<ActionState, string> = {
  PROPOSED:         'Proposed',
  EVALUATING:       'Evaluating',
  PENDING_APPROVAL: 'Pending Approval',
  APPROVED:         'Approved',
  EXECUTING:        'Executing',
  EXECUTED:         'Executed',
  DENIED:           'Denied',
  HALTED:           'Halted',
  SEALED:           'Sealed',
  COMPLETED:        'Completed',
  CANCELLED:        'Cancelled',
};

type Props = {
  state: ActionState;
  size?: 'sm' | 'base';
  showLabel?: boolean;   // show human label instead of raw enum string
};

export function ActionStateBadge({ state, size = 'sm', showLabel = false }: Props) {
  const sizeClass = size === 'sm'
    ? 'px-1.5 py-0.5 text-audit-xs'
    : 'px-2 py-1 text-audit-sm';
  const label = showLabel ? STATE_LABEL[state] : state;

  return (
    <span
      className={[
        'inline-flex items-center font-mono font-semibold rounded-sm border',
        'tracking-wide uppercase whitespace-nowrap',
        sizeClass,
        STATE_CLASSES[state],
      ].join(' ')}
      aria-label={`State: ${STATE_LABEL[state]}`}
      role="status"
    >
      {label}
    </span>
  );
}
```

### ActionDecisionBadge Component

The badge maps the `ActionDecision` enum to a styled pill. It is used everywhere a decision state is shown — ledger tables, HITL queue, dashboard cards. The `aria-label` encodes the meaning for screen readers so color alone does not convey state (WCAG 1.4.1).

```typescript
// components/ActionDecisionBadge.tsx
import type { ActionDecision } from '@/types/quaicu';

const BADGE_CLASSES: Record<ActionDecision, string> = {
  ALLOWED: [
    'bg-decision-allowed-bg',
    'text-decision-allowed-text',
    'border border-decision-allowed-border',
    'ring-1 ring-decision-allowed-border/30',
  ].join(' '),
  DENIED: [
    'bg-decision-denied-bg',
    'text-decision-denied-text',
    'border border-decision-denied-border',
    'ring-1 ring-decision-denied-border/30',
  ].join(' '),
  PENDING: [
    'bg-decision-pending-bg',
    'text-decision-pending-text',
    'border border-decision-pending-border',
    'ring-1 ring-decision-pending-border/30',
  ].join(' '),
  SEALED: [
    'bg-decision-sealed-bg',
    'text-decision-sealed-text',
    'border border-decision-sealed-border',
    'ring-1 ring-decision-sealed-border/30',
  ].join(' '),
};

const LABEL: Record<ActionDecision, string> = {
  ALLOWED: 'Allowed',
  DENIED:  'Denied',
  PENDING: 'Pending Approval',
  SEALED:  'Sealed',
};

type Props = {
  decision: ActionDecision;
  size?: 'sm' | 'base';
};

export function ActionDecisionBadge({ decision, size = 'sm' }: Props) {
  const sizeClass = size === 'sm' ? 'px-1.5 py-0.5 text-audit-xs' : 'px-2 py-1 text-audit-sm';
  return (
    <span
      className={`inline-flex items-center font-mono font-semibold rounded-sm tracking-wide uppercase ${sizeClass} ${BADGE_CLASSES[decision]}`}
      aria-label={`Decision: ${LABEL[decision]}`}
    >
      {decision}
    </span>
  );
}
```

### Governance Data Table Patterns

The ledger table is the most data-dense view in the admin console. Every column has specific formatting rules derived from the data type it displays.

**Column-by-column rules:**

| Column | Alignment | Font | Treatment |
|--------|-----------|------|-----------|
| `ledger_seq` | Right-aligned | Monospace, `tabular-nums` | Up to 12 digits; right-align keeps digit positions stable on scroll |
| `action_type` | Left-aligned | Monospace `audit-xs` | Truncated with CSS `truncate max-w-[16rem]`; full value in `title` tooltip |
| `state` | Left-aligned | — | `<ActionStateBadge>` component |
| Timestamps | Left-aligned | Monospace, `tabular-nums` | Relative time (e.g. "3m ago") displayed; absolute ISO 8601 in `title` tooltip on hover |
| `actor` | Left-aligned | Sans, `audit-sm` | Truncate long identity strings; tooltip with full actor ID |
| `inclusion_proof` / hash fields | Left-aligned | Monospace `audit-xs` | First 8 chars + ellipsis; full hash in tooltip; click-to-copy button |

```tsx
// components/LedgerTable.tsx
import { ActionStateBadge } from './ActionStateBadge';
import { RelativeTime } from './RelativeTime';
import type { LedgerEntry } from '@/types/quaicu';

type Props = { entries: LedgerEntry[] };

export function LedgerTable({ entries }: Props) {
  return (
    <div className="overflow-x-auto rounded-md border border-governance-border">
      <table className="audit-table">
        <thead>
          <tr>
            <th className="col-numeric">Seq</th>
            <th>Action Type</th>
            <th>State</th>
            <th>Actor</th>
            <th>Sealed At</th>
            <th className="col-numeric">Proof</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.action_id}>
              {/* ledger_seq: right-aligned monospace — must never wrap */}
              <td className="col-numeric font-mono text-audit-xs tabular-nums whitespace-nowrap">
                {entry.ledger_seq.toLocaleString()}
              </td>

              {/* action_type: truncated with tooltip */}
              <td
                className="font-mono text-audit-xs truncate max-w-[16rem]"
                title={entry.action_type}
              >
                {entry.action_type}
              </td>

              {/* state: badge component — never raw text */}
              <td>
                <ActionStateBadge state={entry.state} />
              </td>

              {/* actor: truncate with tooltip */}
              <td
                className="text-audit-sm text-governance-muted truncate max-w-[12rem]"
                title={entry.actor}
              >
                {entry.actor}
              </td>

              {/* timestamp: relative on display, absolute on hover */}
              <td className="col-timestamp">
                <RelativeTime
                  iso={entry.sealed_at}
                  className="text-governance-muted text-audit-sm"
                />
              </td>

              {/* inclusion proof: abbreviated hash, click-to-copy */}
              <td className="col-hash" title={entry.inclusion_proof_hex}>
                <button
                  onClick={() => navigator.clipboard.writeText(entry.inclusion_proof_hex)}
                  className="font-mono text-audit-xs text-governance-muted hover:text-governance-link focus:outline-2 focus:outline-governance-link"
                  aria-label={`Copy inclusion proof: ${entry.inclusion_proof_hex}`}
                >
                  {entry.inclusion_proof_hex.slice(0, 8)}…
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### Typography for Audit-Dense Views

The QUAICU ledger tables display: ledger sequence numbers (up to 12 digits), truncated SHA-256 hashes, ISO 8601 timestamps, action type dotted paths (e.g. `ciro.ifrs9.stage_transition`), and actor identifiers. All of these benefit from tabular-nums, monospace, and right-alignment for numeric columns.

**Typography hierarchy for governance views:**

- **Key decision fields** (the policy ID that governed an action, the final decision outcome, the approver who resolved HITL): use `text-base font-semibold text-governance-label` — these are the fields a compliance officer reads first.
- **Metadata fields** (timestamps, sequence numbers, tenant ID): use `text-audit-sm text-governance-muted` — important for traceability but secondary to the decision.
- **Hash and proof values**: use `font-mono text-audit-xs text-governance-muted` — must be machine-readable but are rarely read by humans directly.

```css
/* Utility classes for audit tables — add to globals.css or @layer components */
@layer components {
  .audit-table {
    @apply w-full text-audit-sm font-audit border-collapse;
  }

  .audit-table thead th {
    @apply px-3 py-2 text-left text-audit-xs uppercase tracking-widest
           font-semibold text-governance-muted bg-governance-surface-alt
           border-b border-governance-border select-none;
  }

  .audit-table thead th.col-numeric {
    @apply text-right;
  }

  .audit-table tbody tr {
    @apply border-b border-governance-border transition-colors
           hover:bg-governance-hover;
  }

  .audit-table tbody td {
    @apply px-3 py-2 text-governance-label;
  }

  .audit-table tbody td.col-numeric {
    @apply text-right tabular-nums text-governance-muted;
  }

  .audit-table tbody td.col-hash {
    @apply font-mono text-audit-xs text-governance-muted truncate max-w-[10rem];
  }

  .audit-table tbody td.col-timestamp {
    @apply tabular-nums text-governance-muted whitespace-nowrap;
  }

  .audit-table tbody td.col-action-type {
    @apply font-mono text-audit-xs;
  }

  /* Key decision field — larger, bolder, draws the eye */
  .governance-decision-primary {
    @apply text-base font-semibold text-governance-label;
  }

  /* Metadata — smaller, muted, secondary */
  .governance-metadata {
    @apply text-audit-sm text-governance-muted tabular-nums;
  }
}
```

### HITL Approval Queue Layout

The HITL queue displays all actions in `PENDING_APPROVAL` state, one card per action. The card layout is designed for a compliance officer who must quickly understand what is being approved and make a confident decision.

```tsx
// components/HITLQueueCard.tsx
'use client';
import { useState } from 'react';
import { ActionStateBadge } from './ActionStateBadge';
import type { PendingAction } from '@/types/quaicu';

type Props = {
  action: PendingAction;
  onApprove: (actionId: string, comment: string) => Promise<void>;
  onReject: (actionId: string, comment: string) => Promise<void>;
};

export function HITLQueueCard({ action, onApprove, onReject }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [showConfirm, setShowConfirm] = useState<'approve' | 'reject' | null>(null);
  const [comment, setComment] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleDecision(decision: 'approve' | 'reject') {
    setLoading(true);
    try {
      if (decision === 'approve') await onApprove(action.id, comment);
      else await onReject(action.id, comment);
    } finally {
      setLoading(false);
      setShowConfirm(null);
    }
  }

  return (
    <article
      className="rounded-lg border border-governance-border bg-governance-surface p-4 space-y-3"
      aria-label={`Pending approval: ${action.type}`}
    >
      {/* Header: action type + state + time pending */}
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <p className="font-mono text-audit-sm font-semibold text-governance-label truncate" title={action.type}>
            {action.type}
          </p>
          <p className="text-audit-xs text-governance-muted">
            Action ID: <span className="font-mono">{action.id}</span>
          </p>
        </div>
        <ActionStateBadge state="PENDING_APPROVAL" />
      </div>

      {/* Approver info — who is required to approve */}
      <div className="text-audit-xs text-governance-muted">
        Required approvers:{' '}
        {action.required_approvers.map((r) => (
          <span key={r} className="inline-block bg-governance-surface-alt border border-governance-border rounded px-1 py-0.5 font-mono mr-1">
            {r}
          </span>
        ))}
      </div>

      {/* Policy reference — which policy triggered this */}
      <div className="text-audit-xs text-governance-muted">
        Policy: <span className="font-mono text-governance-label">{action.policy_id} v{action.policy_version}</span>
      </div>

      {/* Action payload — expandable */}
      <div>
        <button
          onClick={() => setExpanded(e => !e)}
          className="text-audit-xs text-governance-link hover:underline focus:outline-2 focus:outline-governance-link"
          aria-expanded={expanded}
          aria-controls={`payload-${action.id}`}
        >
          {expanded ? 'Hide' : 'Show'} action payload
        </button>
        {expanded && (
          <pre
            id={`payload-${action.id}`}
            className="mt-2 p-3 bg-governance-surface-alt border border-governance-border rounded text-audit-xs font-mono text-governance-label overflow-x-auto"
          >
            {JSON.stringify(action.payload, null, 2)}
          </pre>
        )}
      </div>

      {/* Approve / Reject buttons */}
      {!showConfirm ? (
        <div className="flex gap-2 pt-1">
          <button
            onClick={() => setShowConfirm('approve')}
            disabled={loading}
            className="px-3 py-1.5 rounded text-audit-sm font-semibold
                       bg-decision-allowed-bg text-decision-allowed-text
                       border border-decision-allowed-border
                       hover:brightness-95 focus:outline-2 focus:outline-governance-link
                       disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Approve
          </button>
          <button
            onClick={() => setShowConfirm('reject')}
            disabled={loading}
            className="px-3 py-1.5 rounded text-audit-sm font-semibold
                       bg-decision-denied-bg text-decision-denied-text
                       border border-decision-denied-border
                       hover:brightness-95 focus:outline-2 focus:outline-governance-link
                       disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Reject
          </button>
        </div>
      ) : (
        /* Confirmation dialog inline — prevents accidental approval */
        <div className="space-y-2 border border-governance-border rounded p-3 bg-governance-surface-alt">
          <p className="text-audit-sm font-semibold text-governance-label">
            Confirm {showConfirm === 'approve' ? 'approval' : 'rejection'} of this action?
          </p>
          <textarea
            className="w-full text-audit-sm font-sans rounded border border-governance-border
                       bg-governance-surface text-governance-label placeholder-governance-muted
                       p-2 focus:outline-2 focus:outline-governance-link resize-none"
            rows={2}
            placeholder="Optional comment (recorded in the ledger)"
            value={comment}
            onChange={e => setComment(e.target.value)}
            aria-label="Decision comment"
          />
          <div className="flex gap-2">
            <button
              onClick={() => handleDecision(showConfirm)}
              disabled={loading}
              className="px-3 py-1.5 text-audit-sm font-semibold rounded
                         bg-governance-label text-governance-surface
                         focus:outline-2 focus:outline-governance-link
                         disabled:opacity-50"
            >
              {loading ? 'Submitting…' : `Confirm ${showConfirm === 'approve' ? 'Approve' : 'Reject'}`}
            </button>
            <button
              onClick={() => setShowConfirm(null)}
              className="px-3 py-1.5 text-audit-sm text-governance-muted
                         hover:text-governance-label focus:outline-2 focus:outline-governance-link"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
```

**HITL queue layout rules:**
- One card per pending action — never paginate with infinite scroll; use discrete pages so the officer knows how many decisions are outstanding.
- Approver role badges above the approve/reject buttons — the officer must know who is authorised before deciding.
- Action payload is collapsed by default — the default view is the decision context, not the raw data. Expand is for verification.
- Confirmation dialog is inline, not a modal — modals steal focus and can obscure the payload the officer just reviewed.
- Comment field is always present in the confirmation step — the comment is sealed to the ledger as part of the HITL decision record.

### Impact Report Visualization (Policy Simulation)

The impact report is generated by the backtest / shadow mode pipeline (spec §3.9). It shows the decision distribution of the active policy vs the candidate policy side-by-side, so a reviewer can sign off before activation.

```tsx
// components/ImpactReportChart.tsx
type PolicyDistribution = {
  label: string;      // "Active Policy" | "Candidate Policy"
  allow: number;      // count
  deny: number;
  require_approval: number;
  total: number;
};

type Props = {
  active: PolicyDistribution;
  candidate: PolicyDistribution;
  flipped_count: number;     // actions whose decision would change
  fairness_delta: number;    // from K·09; > 0.05 is flagged
};

export function ImpactReportChart({ active, candidate, flipped_count, fairness_delta }: Props) {
  const policies = [active, candidate];
  const isFairnessConcern = Math.abs(fairness_delta) > 0.05;

  return (
    <div className="space-y-4">
      {/* Side-by-side distribution bars */}
      <div className="grid grid-cols-2 gap-4">
        {policies.map((pol) => (
          <div key={pol.label} className="space-y-2">
            <p className="text-audit-sm font-semibold text-governance-label">{pol.label}</p>
            <DistributionBar distribution={pol} />
            <dl className="grid grid-cols-3 text-audit-xs text-center gap-1">
              <MetricCell label="Allow"    value={pol.allow}            color="decision-allowed-text" />
              <MetricCell label="Deny"     value={pol.deny}             color="decision-denied-text" />
              <MetricCell label="Approval" value={pol.require_approval} color="decision-pending-text" />
            </dl>
          </div>
        ))}
      </div>

      {/* Impact summary */}
      <div className="border-t border-governance-border pt-3 space-y-1">
        <p className="text-audit-sm text-governance-muted">
          <span className="font-semibold text-governance-label">{flipped_count.toLocaleString()}</span> actions would change decision
        </p>
        <p className={`text-audit-sm ${isFairnessConcern ? 'text-decision-pending-text font-semibold' : 'text-governance-muted'}`}>
          Fairness delta: {(fairness_delta * 100).toFixed(2)}%
          {isFairnessConcern && ' — shadow mode required before activation (spec §3.9)'}
        </p>
      </div>
    </div>
  );
}

function DistributionBar({ distribution }: { distribution: PolicyDistribution }) {
  const { allow, deny, require_approval, total } = distribution;
  if (total === 0) return <div className="h-4 bg-governance-surface-alt rounded" />;
  return (
    <div className="h-4 flex rounded overflow-hidden" role="img" aria-label="Decision distribution bar">
      <div style={{ width: `${(allow / total) * 100}%` }}
           className="bg-decision-allowed transition-all" title={`Allow: ${allow}`} />
      <div style={{ width: `${(deny / total) * 100}%` }}
           className="bg-decision-denied transition-all" title={`Deny: ${deny}`} />
      <div style={{ width: `${(require_approval / total) * 100}%` }}
           className="bg-decision-pending transition-all" title={`Requires approval: ${require_approval}`} />
    </div>
  );
}
```

### Policy Authoring Form Layout

The policy authoring form is used by compliance officers and engineers to author, validate, and submit policy envelopes (spec §3.9). The form must make the activation pipeline visible: YAML edit → CEL compile check → dry-run → review.

```tsx
// components/PolicyAuthoringForm.tsx
// Layout: two-column on desktop (YAML editor left, validation panel right)
// Single column on mobile (editor first, then validation)

export function PolicyAuthoringForm() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4 h-full">
      {/* Left: YAML editor */}
      <div className="flex flex-col space-y-2">
        <label className="text-audit-sm font-semibold text-governance-label">
          Policy Envelope (YAML)
        </label>
        {/* CEL syntax highlighting via a code editor component (e.g. CodeMirror) */}
        <div className="flex-1 min-h-[400px] rounded-md border border-governance-border
                        bg-governance-surface-alt font-mono text-audit-sm overflow-hidden">
          {/* <CodeMirror lang="yaml" celHighlight /> */}
          <PolicyYAMLEditor />
        </div>
      </div>

      {/* Right: validation + activation pipeline status */}
      <div className="flex flex-col space-y-3">
        {/* CEL compile status */}
        <ValidationStep
          label="CEL Condition"
          status="pass"       // 'pass' | 'fail' | 'pending'
          detail="Compiled successfully — deterministic, no I/O"
        />

        {/* JSON schema validation */}
        <ValidationStep
          label="Schema Validation"
          status="pass"
          detail="All required fields present"
        />

        {/* Inline validation errors */}
        <PolicyValidationErrors errors={[]} />

        {/* Dry-run result (single action pre-flight) */}
        <ValidationStep
          label="Dry-run Result"
          status="pending"
          detail="Run a dry-run against a sample action to preview the decision"
        />

        {/* Backtest impact report link */}
        <ValidationStep
          label="Backtest Impact Report"
          status="pending"
          detail="Required before activation (spec §3.9)"
        />

        {/* Activation button — disabled until pipeline steps pass */}
        <button
          disabled
          className="mt-auto px-4 py-2 rounded text-audit-sm font-semibold
                     bg-governance-label text-governance-surface
                     disabled:opacity-40 disabled:cursor-not-allowed
                     focus:outline-2 focus:outline-governance-link"
        >
          Submit for Review
        </button>
      </div>
    </div>
  );
}

function ValidationStep({ label, status, detail }: {
  label: string; status: 'pass' | 'fail' | 'pending'; detail: string;
}) {
  const colorClass = {
    pass:    'text-decision-allowed-text bg-decision-allowed-bg border-decision-allowed-border',
    fail:    'text-decision-denied-text bg-decision-denied-bg border-decision-denied-border',
    pending: 'text-governance-muted bg-governance-surface-alt border-governance-border',
  }[status];

  return (
    <div className={`rounded border p-2 text-audit-xs space-y-0.5 ${colorClass}`}>
      <p className="font-semibold">{label}: {status.toUpperCase()}</p>
      <p className="text-current opacity-80">{detail}</p>
    </div>
  );
}
```

**Inline validation error display:** CEL compile errors must be shown directly below the YAML editor with line/column references, not in a separate toast or sidebar. A compliance officer writing a condition needs the error adjacent to the code.

```tsx
// components/PolicyValidationErrors.tsx
type ValidationError = { line: number; col: number; message: string };

export function PolicyValidationErrors({ errors }: { errors: ValidationError[] }) {
  if (errors.length === 0) return null;
  return (
    <ul className="space-y-1" role="alert" aria-label="Validation errors">
      {errors.map((e, i) => (
        <li key={i} className="flex gap-2 text-audit-xs text-decision-denied-text
                               bg-decision-denied-bg border border-decision-denied-border
                               rounded px-2 py-1">
          <span className="font-mono shrink-0">L{e.line}:{e.col}</span>
          <span>{e.message}</span>
        </li>
      ))}
    </ul>
  );
}
```

### Dark Mode Strategy for Compliance Officer Use

Compliance officers work extended sessions during audits. Dark mode reduces contrast fatigue while keeping decision-state colors unambiguous. Use the `class` strategy (explicit toggle) rather than `media` — auditors may prefer dark in a system-light environment.

```typescript
// hooks/useDarkMode.ts
'use client';

import { useEffect, useState } from 'react';

export function useDarkMode() {
  const [dark, setDark] = useState(() => {
    if (typeof window === 'undefined') return false;
    return localStorage.getItem('quaicu-theme') === 'dark';
  });

  useEffect(() => {
    const root = document.documentElement;
    if (dark) {
      root.classList.add('dark');
      localStorage.setItem('quaicu-theme', 'dark');
    } else {
      root.classList.remove('dark');
      localStorage.setItem('quaicu-theme', 'light');
    }
  }, [dark]);

  return { dark, toggleDark: () => setDark(d => !d) };
}
```

**Dark mode palette rationale for compliance officer use:**
- Surfaces use `slate-900` / `slate-800` — not pure `#000000`. Pure black causes halation against bright badge colors.
- All decision state colors are re-tested at AAA contrast on dark surfaces — the same red and amber that pass on light may fail on dark.
- Muted text uses `slate-400` in dark mode — `slate-500` drops below AA on `slate-900` backgrounds.
- The governance link color shifts from `blue-600` (light) to `blue-400` (dark) — `blue-600` fails contrast on `slate-900`.

### Accessibility Requirements for Regulatory Environments

WCAG 2.1 AA is the floor; AAA is the target for decision-critical colors. The design system enforces this through:

1. **Color is never the sole indicator.** Every `ActionDecisionBadge` includes the text label and an `aria-label`. Icons (checkmark / x / clock / lock) accompany color badges in high-density tables.
2. **Focus rings** use `outline-2 outline-offset-2 outline-governance-link` — visible on both light and dark surfaces.
3. **Keyboard navigation** through the HITL queue and ledger table is fully supported — approve/reject buttons are focusable and respond to Space/Enter.
4. **Reduced motion** — no transitions on badges or tables that could trigger vestibular issues:

```css
@media (prefers-reduced-motion: reduce) {
  .audit-table tbody tr,
  .badge-animated {
    transition: none;
  }
}
```

5. **Print styles** — regulators may print audit reports. Decision badges should print in black-and-white with pattern fills:

```css
@media print {
  .badge-allowed   { border: 2px solid #000; }
  .badge-denied    { border: 2px solid #000; background: repeating-linear-gradient(
    45deg, transparent, transparent 2px, #000 2px, #000 4px); }
  .badge-pending   { border: 2px dashed #000; }
  .badge-sealed    { border: 2px double #000; }
  .badge-halted    { border: 3px solid #000; background: repeating-linear-gradient(
    -45deg, transparent, transparent 2px, #000 2px, #000 4px); }
  .badge-completed { border: 2px solid #000; background: #ccc; }
  .badge-cancelled { border: 1px dashed #666; color: #666; }
}
```

6. **Minimum touch target** for approve/reject buttons in the HITL queue: `min-h-[44px] min-w-[44px]` (WCAG 2.5.5 AAA, strongly recommended for a decision interface where a mis-tap has governance consequences).

7. **Contrast audit cadence:** run `axe-core` in CI against the Storybook stories for all badge and table components. Any new `ActionState` or design token that causes a contrast failure must block merge.

### Token Usage Rules

- **Always** use semantic decision tokens (`text-decision-denied-text`) — never raw colors (`text-red-700`) for governance states. Raw colors break dark mode and mean nothing to future maintainers.
- **Never** introduce a new state color without updating the `ActionStateBadge`, contrast audit, print styles, and the CSS custom properties for both light and dark mode.
- **Always** verify new colors with a contrast checker (axe DevTools, Colour Contrast Analyser) against both light and dark backgrounds before merging.
- **Always** test badge legibility with a grayscale simulation — colorblind users in regulatory environments are not uncommon.
- **Never** use `brightness-*` or `opacity-*` utilities to derive hover states for decision tokens — derive hover colors from the same CSS variable family or use explicit `hover:` variants with verified contrast ratios.
