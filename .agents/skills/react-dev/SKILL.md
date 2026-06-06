---
name: react-dev
version: 1.0.0
description: This skill should be used when building React components with TypeScript, typing hooks, handling events, or when React TypeScript, React 19, Server Components are mentioned. Covers type-safe patterns for React 18-19 including generic components, proper event typing, and routing integration (TanStack Router, React Router). QUAICU kernel — admin console components that render kernel state and submit requests, never deciding policy or verifying proofs client-side — ActionTrailTable, HITLApprovalQueue, PolicyAuthoringForm, ImpactReportViewer, LedgerVerifyPanel; exhaustive ActionState with unknown rendered as blocked. Triggers — QUAICU, ActionState badge, ActionTrailTable, HITLApprovalQueue, LedgerVerifyPanel, ImpactReportViewer.
---

# React TypeScript

## ⚡ QUAICU Decision Contract — READ THIS FIRST (when used for the QUAICU kernel)

> Makes the QUAICU-specific component choices mechanical so a small/low-token model matches a top model at max effort.
> **For QUAICU work, this block overrides the general guidance below.**

### Invariants — never violated
- Components RENDER kernel state and SUBMIT requests; they never decide policy, compute proofs, or alter an outcome client-side. Trust the server response.
- Render every `ActionState` exhaustively (discriminated union + exhaustive switch). An unknown state renders as neutral/blocked, never as "allowed".
- The ledger verification UI displays the server's signed verification result; it does NOT re-implement Merkle verification in the browser as the source of truth.
- All server data is Zod-validated at the boundary; loading/error/empty states are always handled (no optimistic "success").
- Never render unmasked PII or raw prompts; show the kernel-provided (masked) values.

### Core components (build to the kernel's contracts)
| Component | Responsibility |
|---|---|
| `ActionTrailTable` | list actions + states (read-only) |
| `HITLApprovalQueue` | approve/reject; reflect returned state |
| `PolicyAuthoringForm` | author CEL/envelope; server validates + simulates before activate |
| `ImpactReportViewer` | render backtest report; cannot activate without it |
| `LedgerVerifyPanel` | show the server verification bundle |

### Tie-break rules
- Optimistically mark an action approved on click? → no; wait for and reflect the kernel's returned state.
- Verify the ledger in-browser as truth? → no; the server's signed verification is authoritative.

### Self-check
- [ ] No governance/proof logic as source of truth in the client.
- [ ] ActionState exhaustive; unknown → blocked, not allowed.
- [ ] Server data Zod-validated; loading/error/empty handled.
- [ ] No unmasked PII/prompts rendered.

---

Type-safe React = compile-time guarantees = confident refactoring.

<when_to_use>

- Building typed React components
- Implementing generic components
- Typing event handlers, forms, refs
- Using React 19 features (Actions, Server Components, use())
- Router integration (TanStack Router, React Router)
- Custom hooks with proper typing

NOT for: non-React TypeScript, vanilla JS React

</when_to_use>

<react_19_changes>

React 19 breaking changes require migration. Key patterns:

**ref as prop** - forwardRef deprecated:

```typescript
// React 19 - ref as regular prop
type ButtonProps = {
  ref?: React.Ref<HTMLButtonElement>;
} & React.ComponentPropsWithoutRef<'button'>;

function Button({ ref, children, ...props }: ButtonProps) {
  return <button ref={ref} {...props}>{children}</button>;
}
```

**useActionState** - replaces useFormState:

```typescript
import { useActionState } from 'react';

type FormState = { errors?: string[]; success?: boolean };

function Form() {
  const [state, formAction, isPending] = useActionState(submitAction, {});
  return <form action={formAction}>...</form>;
}
```

**use()** - unwraps promises/context:

```typescript
function UserProfile({ userPromise }: { userPromise: Promise<User> }) {
  const user = use(userPromise); // Suspends until resolved
  return <div>{user.name}</div>;
}
```

See [react-19-patterns.md](references/react-19-patterns.md) for useOptimistic, useTransition, migration checklist.

</react_19_changes>

<component_patterns>

**Props** - extend native elements:

```typescript
type ButtonProps = {
  variant: 'primary' | 'secondary';
} & React.ComponentPropsWithoutRef<'button'>;

function Button({ variant, children, ...props }: ButtonProps) {
  return <button className={variant} {...props}>{children}</button>;
}
```

**Children typing**:

```typescript
type Props = {
  children: React.ReactNode;          // Anything renderable
  icon: React.ReactElement;           // Single element
  render: (data: T) => React.ReactNode;  // Render prop
};
```

**Discriminated unions** for variant props:

```typescript
type ButtonProps =
  | { variant: 'link'; href: string }
  | { variant: 'button'; onClick: () => void };

function Button(props: ButtonProps) {
  if (props.variant === 'link') {
    return <a href={props.href}>Link</a>;
  }
  return <button onClick={props.onClick}>Button</button>;
}
```

</component_patterns>

<event_handlers>

Use specific event types for accurate target typing:

```typescript
// Mouse
function handleClick(e: React.MouseEvent<HTMLButtonElement>) {
  e.currentTarget.disabled = true;
}

// Form
function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
  e.preventDefault();
  const formData = new FormData(e.currentTarget);
}

// Input
function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
  console.log(e.target.value);
}

// Keyboard
function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
  if (e.key === 'Enter') e.currentTarget.blur();
}
```

See [event-handlers.md](references/event-handlers.md) for focus, drag, clipboard, touch, wheel events.

</event_handlers>

<hooks_typing>

**useState** - explicit for unions/null:

```typescript
const [user, setUser] = useState<User | null>(null);
const [status, setStatus] = useState<'idle' | 'loading'>('idle');
```

**useRef** - null for DOM, value for mutable:

```typescript
const inputRef = useRef<HTMLInputElement>(null);  // DOM - use ?.
const countRef = useRef<number>(0);               // Mutable - direct access
```

**useReducer** - discriminated unions for actions:

```typescript
type Action =
  | { type: 'increment' }
  | { type: 'set'; payload: number };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'set': return { ...state, count: action.payload };
    default: return state;
  }
}
```

**Custom hooks** - tuple returns with as const:

```typescript
function useToggle(initial = false) {
  const [value, setValue] = useState(initial);
  const toggle = () => setValue(v => !v);
  return [value, toggle] as const;
}
```

**useContext** - null guard pattern:

```typescript
const UserContext = createContext<User | null>(null);

function useUser() {
  const user = useContext(UserContext);
  if (!user) throw new Error('useUser outside UserProvider');
  return user;
}
```

See [hooks.md](references/hooks.md) for useCallback, useMemo, useImperativeHandle, useSyncExternalStore.

</hooks_typing>

<generic_components>

Generic components infer types from props - no manual annotations at call site.

**Pattern** - keyof T for column keys, render props for custom rendering:

```typescript
type Column<T> = {
  key: keyof T;
  header: string;
  render?: (value: T[keyof T], item: T) => React.ReactNode;
};

type TableProps<T> = {
  data: T[];
  columns: Column<T>[];
  keyExtractor: (item: T) => string | number;
};

function Table<T>({ data, columns, keyExtractor }: TableProps<T>) {
  return (
    <table>
      <thead>
        <tr>{columns.map(col => <th key={String(col.key)}>{col.header}</th>)}</tr>
      </thead>
      <tbody>
        {data.map(item => (
          <tr key={keyExtractor(item)}>
            {columns.map(col => (
              <td key={String(col.key)}>
                {col.render ? col.render(item[col.key], item) : String(item[col.key])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

**Constrained generics** for required properties:

```typescript
type HasId = { id: string | number };

function List<T extends HasId>({ items }: { items: T[] }) {
  return <ul>{items.map(item => <li key={item.id}>...</li>)}</ul>;
}
```

See [generic-components.md](examples/generic-components.md) for Select, List, Modal, FormField patterns.

</generic_components>

<server_components>

React 19 Server Components run on server, can be async.

**Async data fetching**:

```typescript
export default async function UserPage({ params }: { params: { id: string } }) {
  const user = await fetchUser(params.id);
  return <div>{user.name}</div>;
}
```

**Server Actions** - 'use server' for mutations:

```typescript
'use server';

export async function updateUser(userId: string, formData: FormData) {
  await db.user.update({ where: { id: userId }, data: { ... } });
  revalidatePath(`/users/${userId}`);
}
```

**Client + Server Action**:

```typescript
'use client';

import { useActionState } from 'react';
import { updateUser } from '@/actions/user';

function UserForm({ userId }: { userId: string }) {
  const [state, formAction, isPending] = useActionState(
    (prev, formData) => updateUser(userId, formData), {}
  );
  return <form action={formAction}>...</form>;
}
```

**use() for promise handoff**:

```typescript
// Server: pass promise without await
async function Page() {
  const userPromise = fetchUser('123');
  return <UserProfile userPromise={userPromise} />;
}

// Client: unwrap with use()
'use client';
function UserProfile({ userPromise }: { userPromise: Promise<User> }) {
  const user = use(userPromise);
  return <div>{user.name}</div>;
}
```

See [server-components.md](examples/server-components.md) for parallel fetching, streaming, error boundaries.

</server_components>

<routing>

Both TanStack Router and React Router v7 provide type-safe routing solutions.

**TanStack Router** - Compile-time type safety with Zod validation:

```typescript
import { createRoute } from '@tanstack/react-router';
import { z } from 'zod';

const userRoute = createRoute({
  path: '/users/$userId',
  component: UserPage,
  loader: async ({ params }) => ({ user: await fetchUser(params.userId) }),
  validateSearch: z.object({
    tab: z.enum(['profile', 'settings']).optional(),
    page: z.number().int().positive().default(1),
  }),
});

function UserPage() {
  const { user } = useLoaderData({ from: userRoute.id });
  const { tab, page } = useSearch({ from: userRoute.id });
  const { userId } = useParams({ from: userRoute.id });
}
```

**React Router v7** - Automatic type generation with Framework Mode:

```typescript
import type { Route } from "./+types/user";

export async function loader({ params }: Route.LoaderArgs) {
  return { user: await fetchUser(params.userId) };
}

export default function UserPage({ loaderData }: Route.ComponentProps) {
  const { user } = loaderData; // Typed from loader
  return <h1>{user.name}</h1>;
}
```

See [tanstack-router.md](references/tanstack-router.md) for TanStack patterns and [react-router.md](references/react-router.md) for React Router patterns.

</routing>

<rules>

ALWAYS:
- Specific event types (MouseEvent, ChangeEvent, etc)
- Explicit useState for unions/null
- ComponentPropsWithoutRef for native element extension
- Discriminated unions for variant props
- as const for tuple returns
- ref as prop in React 19 (no forwardRef)
- useActionState for form actions
- Type-safe routing patterns (see routing section)

NEVER:
- any for event handlers
- JSX.Element for children (use ReactNode)
- forwardRef in React 19+
- useFormState (deprecated)
- Forget null handling for DOM refs
- Mix Server/Client components in same file
- Await promises when passing to use()

</rules>

<references>

- [hooks.md](references/hooks.md) - useState, useRef, useReducer, useContext, custom hooks
- [event-handlers.md](references/event-handlers.md) - all event types, generic handlers
- [react-19-patterns.md](references/react-19-patterns.md) - useActionState, use(), useOptimistic, migration
- [generic-components.md](examples/generic-components.md) - Table, Select, List, Modal patterns
- [server-components.md](examples/server-components.md) - async components, Server Actions, streaming
- [tanstack-router.md](references/tanstack-router.md) - TanStack Router typed routes, search params, navigation
- [react-router.md](references/react-router.md) - React Router v7 loaders, actions, type generation, forms

</references>

---

## QUAICU-Specific Application

### Admin Console Component Architecture

The QUAICU admin console is a React 19 + TypeScript application that surfaces governance state, HITL queues, policy authoring, and ledger verification. Every component consumes the kernel's REST API (`/kernel/v1/...`) via React Query. All console operations are themselves governed actions — nothing writes kernel state outside the lifecycle.

#### ActionState enum and shared types

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
  | 'SEALED';

export type ActionDecision = 'ALLOWED' | 'DENIED' | 'PENDING' | 'SEALED';

export interface LedgerEntry {
  ledger_seq: number;
  action_id: string;
  action_type: string;
  actor: string;
  tenant_id: string;
  state: ActionState;
  decision: ActionDecision;
  inclusion_proof: string;    // RFC 6962 proof bytes, base64
  sealed_at: string;          // ISO 8601
  payload_hash: string;
}

export interface HITLItem {
  action_id: string;
  action_type: string;
  actor: string;
  tenant_id: string;
  state: 'PENDING_APPROVAL';
  proposed_at: string;
  approvers: string[];
  policy_id: string;
  payload_summary: string;
}

export interface PolicyVersion {
  id: string;
  version: number;
  governs: string;
  condition_cel: string;
  decision: 'allow' | 'deny' | 'require_approval';
  lifecycle: 'DRAFT' | 'REVIEW' | 'ACTIVATED' | 'DEPRECATED';
  regulatory_refs: string[];
  impact_report_id?: string;
}
```

#### ActionTrailTable

Displays the immutable ledger trail for a governed entity. The `ledger_seq` column is always shown first — it is the authoritative ordering. The `proof` column renders a clickable badge that opens the `LedgerVerifyPanel` inline.

```typescript
// components/ActionTrailTable.tsx
'use client';

import { useQuery } from '@tanstack/react-query';
import { ActionDecisionBadge } from './ActionDecisionBadge';
import { LedgerVerifyPanel } from './LedgerVerifyPanel';
import type { LedgerEntry } from '@/types/quaicu';

type ActionTrailTableProps = {
  entityId: string;
  tenantId: string;
  pageSize?: number;
};

export function ActionTrailTable({
  entityId,
  tenantId,
  pageSize = 50,
}: ActionTrailTableProps) {
  const [expandedProof, setExpandedProof] = useState<number | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['ledger', 'trail', tenantId, entityId],
    queryFn: () =>
      fetch(`/kernel/v1/ledger/${entityId}/trail?tenant=${tenantId}&limit=${pageSize}`)
        .then(r => {
          if (!r.ok) throw new Error(`Ledger fetch failed: ${r.status}`);
          return r.json() as Promise<{ entries: LedgerEntry[] }>;
        }),
    staleTime: 10_000,
    refetchInterval: 30_000,
  });

  if (isLoading) return <TableSkeleton rows={pageSize} cols={5} />;
  if (isError) return <ErrorBanner message="Ledger unavailable" />;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm font-mono">
        <thead className="text-xs uppercase text-governance-muted bg-governance-surface">
          <tr>
            <th className="px-3 py-2 text-right w-24">seq</th>
            <th className="px-3 py-2 text-left">action type</th>
            <th className="px-3 py-2 text-left">actor</th>
            <th className="px-3 py-2 text-left">state</th>
            <th className="px-3 py-2 text-left">decision</th>
            <th className="px-3 py-2 text-left">sealed</th>
            <th className="px-3 py-2 text-center">proof</th>
          </tr>
        </thead>
        <tbody>
          {data?.entries.map(entry => (
            <>
              <tr
                key={entry.ledger_seq}
                className="border-b border-governance-border hover:bg-governance-hover"
              >
                <td className="px-3 py-2 text-right tabular-nums text-governance-muted">
                  {entry.ledger_seq.toLocaleString()}
                </td>
                <td className="px-3 py-2">{entry.action_type}</td>
                <td className="px-3 py-2 truncate max-w-[12rem]">{entry.actor}</td>
                <td className="px-3 py-2">
                  <ActionStateBadge state={entry.state} />
                </td>
                <td className="px-3 py-2">
                  <ActionDecisionBadge decision={entry.decision} />
                </td>
                <td className="px-3 py-2 tabular-nums text-governance-muted">
                  {new Date(entry.sealed_at).toLocaleString()}
                </td>
                <td className="px-3 py-2 text-center">
                  <button
                    onClick={() =>
                      setExpandedProof(p =>
                        p === entry.ledger_seq ? null : entry.ledger_seq
                      )
                    }
                    className="text-xs underline text-governance-link"
                    aria-label={`Verify proof for seq ${entry.ledger_seq}`}
                  >
                    verify
                  </button>
                </td>
              </tr>
              {expandedProof === entry.ledger_seq && (
                <tr key={`proof-${entry.ledger_seq}`}>
                  <td colSpan={7} className="bg-governance-surface-alt px-4 py-3">
                    <LedgerVerifyPanel
                      ledgerSeq={entry.ledger_seq}
                      inclusionProof={entry.inclusion_proof}
                      tenantId={tenantId}
                    />
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

#### PolicyAuthoringForm with CEL syntax highlighting

CEL is the sole policy condition language (ADR F-05). The authoring form compiles the CEL expression client-side (via a lightweight wasm CEL checker) before submission and shows syntax errors inline. The form is a governed action — submitting creates a `policy.version.create` action that enters the lifecycle.

```typescript
// components/PolicyAuthoringForm.tsx
'use client';

import { useActionState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import Editor from '@monaco-editor/react';
import type { PolicyVersion } from '@/types/quaicu';

type PolicyAuthoringFormProps = {
  tenantId: string;
  onSuccess?: (policy: PolicyVersion) => void;
};

export function PolicyAuthoringForm({ tenantId, onSuccess }: PolicyAuthoringFormProps) {
  const qc = useQueryClient();
  const [celError, setCelError] = useState<string | null>(null);

  const saveMutation = useMutation({
    mutationFn: (draft: Omit<PolicyVersion, 'version' | 'lifecycle'>) =>
      fetch('/kernel/v1/policy/versions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Tenant-Id': tenantId },
        body: JSON.stringify(draft),
      }).then(r => {
        if (!r.ok) throw new Error(`Policy save failed: ${r.status}`);
        return r.json() as Promise<PolicyVersion>;
      }),
    onSuccess: policy => {
      qc.invalidateQueries({ queryKey: ['policies', tenantId] });
      onSuccess?.(policy);
    },
  });

  // Monaco editor configured for CEL: syntax ≈ JavaScript with no side-effects
  const celEditorOptions = {
    language: 'javascript',   // closest Monaco grammar; swap for cel if custom grammar loaded
    theme: 'governance-dark',
    minimap: { enabled: false },
    lineNumbers: 'on' as const,
    fontSize: 13,
    fontFamily: 'JetBrains Mono, monospace',
    scrollBeyondLastLine: false,
  };

  return (
    <form
      onSubmit={e => {
        e.preventDefault();
        // form data extraction + CEL pre-compile check omitted for brevity
        saveMutation.mutate({ /* ... */ } as any);
      }}
      className="space-y-4"
    >
      {/* id, governs, decision fields ... */}
      <div>
        <label className="block text-xs font-medium text-governance-label mb-1">
          Condition (CEL)
        </label>
        <div className="border border-governance-border rounded overflow-hidden h-32">
          <Editor
            defaultLanguage="javascript"
            options={celEditorOptions}
            onChange={value => {
              // Wire to lightweight wasm CEL compile check
              validateCEL(value ?? '').then(err => setCelError(err));
            }}
          />
        </div>
        {celError && (
          <p className="mt-1 text-xs text-decision-denied" role="alert">
            {celError}
          </p>
        )}
      </div>
      <p className="text-xs text-governance-muted">
        CEL conditions are deterministic and sandboxed — no I/O, clock, or side effects.
        See ADR F-05.
      </p>
      <button
        type="submit"
        disabled={!!celError || saveMutation.isPending}
        className="btn-governance-primary"
      >
        {saveMutation.isPending ? 'Saving...' : 'Save as Draft'}
      </button>
    </form>
  );
}
```

#### HITLApprovalQueue with real-time polling

The HITL queue must never go stale — a missed approval is a blocked governed action. Poll every 5 seconds. Optimistic updates mark an item as resolved immediately on click so the reviewer sees instant feedback while the kernel processes the decision.

```typescript
// components/HITLApprovalQueue.tsx
'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useOptimistic } from 'react';
import type { HITLItem } from '@/types/quaicu';

type HITLApprovalQueueProps = {
  tenantId: string;
};

export function HITLApprovalQueue({ tenantId }: HITLApprovalQueueProps) {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['hitl', 'queue', tenantId],
    queryFn: () =>
      fetch(`/kernel/v1/hitl/queue?tenant=${tenantId}`)
        .then(r => r.json() as Promise<{ items: HITLItem[] }>),
    refetchInterval: 5_000,   // real-time feel; kernel is the authoritative source
    staleTime: 0,
  });

  const [optimisticItems, addOptimistic] = useOptimistic(
    data?.items ?? [],
    (current: HITLItem[], resolvedId: string) =>
      current.filter(i => i.action_id !== resolvedId),
  );

  const decisionMutation = useMutation({
    mutationFn: ({
      actionId,
      verdict,
    }: {
      actionId: string;
      verdict: 'approve' | 'reject';
    }) =>
      fetch(`/kernel/v1/actions/${actionId}/${verdict}`, {
        method: 'POST',
        headers: { 'X-Tenant-Id': tenantId },
      }).then(r => {
        if (!r.ok) throw new Error(`HITL decision failed: ${r.status}`);
        return r.json();
      }),
    onSuccess: (_, { actionId }) => {
      // Server confirmed — invalidate so the next poll reflects truth
      qc.invalidateQueries({ queryKey: ['hitl', 'queue', tenantId] });
      qc.invalidateQueries({ queryKey: ['ledger'] });
    },
  });

  if (isLoading) return <QueueSkeleton />;

  return (
    <section aria-label="HITL Approval Queue">
      <header className="flex items-center gap-2 mb-3">
        <h2 className="text-sm font-semibold">Pending Approvals</h2>
        <span className="badge-count">{optimisticItems.length}</span>
      </header>
      {optimisticItems.length === 0 && (
        <p className="text-sm text-governance-muted">No actions awaiting approval.</p>
      )}
      <ul className="space-y-2">
        {optimisticItems.map(item => (
          <li
            key={item.action_id}
            className="p-3 rounded border border-governance-border bg-governance-surface"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-0.5">
                <p className="text-sm font-medium">{item.action_type}</p>
                <p className="text-xs text-governance-muted">
                  Actor: {item.actor} · Policy: {item.policy_id}
                </p>
                <p className="text-xs text-governance-muted line-clamp-2">
                  {item.payload_summary}
                </p>
              </div>
              <div className="flex gap-2 shrink-0">
                <button
                  onClick={() => {
                    addOptimistic(item.action_id);
                    decisionMutation.mutate({ actionId: item.action_id, verdict: 'approve' });
                  }}
                  className="btn-sm btn-allowed"
                >
                  Approve
                </button>
                <button
                  onClick={() => {
                    addOptimistic(item.action_id);
                    decisionMutation.mutate({ actionId: item.action_id, verdict: 'reject' });
                  }}
                  className="btn-sm btn-denied"
                >
                  Reject
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

#### ImpactReportViewer

Displays before/after decision distribution charts for the policy activation gate. A policy version cannot transition from REVIEW to ACTIVATED unless an impact report exists and a reviewer acknowledges it (ADR F-10).

```typescript
// components/ImpactReportViewer.tsx
'use client';

import { useQuery } from '@tanstack/react-query';
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts';

type ImpactReportViewerProps = {
  policyId: string;
  versionId: number;
  tenantId: string;
  onAcknowledge: () => void;
};

export function ImpactReportViewer({
  policyId,
  versionId,
  tenantId,
  onAcknowledge,
}: ImpactReportViewerProps) {
  const { data, isLoading } = useQuery({
    queryKey: ['policy', 'impact', tenantId, policyId, versionId],
    queryFn: () =>
      fetch(
        `/kernel/v1/policy/${policyId}/versions/${versionId}/impact-report?tenant=${tenantId}`
      ).then(r => r.json()),
  });

  if (isLoading) return <ReportSkeleton />;

  const chartData = [
    {
      label: 'Active Policy',
      ALLOWED: data?.active.allowed_pct,
      DENIED: data?.active.denied_pct,
      PENDING: data?.active.pending_pct,
    },
    {
      label: 'Candidate Policy',
      ALLOWED: data?.candidate.allowed_pct,
      DENIED: data?.candidate.denied_pct,
      PENDING: data?.candidate.pending_pct,
    },
  ];

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold">Decision Distribution — Before vs After</h3>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={chartData} layout="vertical">
          <XAxis type="number" unit="%" domain={[0, 100]} />
          <YAxis type="category" dataKey="label" width={120} />
          <Tooltip formatter={(v: number) => `${v.toFixed(1)}%`} />
          <Legend />
          <Bar dataKey="ALLOWED" fill="var(--color-decision-allowed)" stackId="a" />
          <Bar dataKey="DENIED" fill="var(--color-decision-denied)" stackId="a" />
          <Bar dataKey="PENDING" fill="var(--color-decision-pending)" stackId="a" />
        </BarChart>
      </ResponsiveContainer>
      <p className="text-xs text-governance-muted">
        Flipped decisions: {data?.flipped_count ?? '—'} ·
        Fairness delta: {data?.fairness_delta != null
          ? `${data.fairness_delta > 0 ? '+' : ''}${(data.fairness_delta * 100).toFixed(2)}%`
          : '—'}
      </p>
      <button onClick={onAcknowledge} className="btn-governance-primary w-full">
        Acknowledge &amp; Proceed to Activation
      </button>
    </div>
  );
}
```

#### LedgerVerifyPanel

Shows the RFC 6962 inclusion proof for a sealed entry. Calls the kernel's `/kernel/v1/ledger/verify` endpoint and renders the cryptographic result. Pass/fail is displayed with accessible color and icon.

```typescript
// components/LedgerVerifyPanel.tsx
'use client';

import { useQuery } from '@tanstack/react-query';

type LedgerVerifyPanelProps = {
  ledgerSeq: number;
  inclusionProof: string;   // base64 RFC 6962 proof bytes
  tenantId: string;
};

export function LedgerVerifyPanel({
  ledgerSeq,
  inclusionProof,
  tenantId,
}: LedgerVerifyPanelProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['ledger', 'verify', tenantId, ledgerSeq],
    queryFn: () =>
      fetch(
        `/kernel/v1/ledger/verify?seq=${ledgerSeq}&tenant=${tenantId}`
      ).then(r => r.json() as Promise<{
        valid: boolean;
        tree_size: number;
        root_hash: string;
        verified_at: string;
      }>),
    staleTime: 60_000,
  });

  return (
    <div className="text-xs font-mono space-y-1">
      <p className="font-semibold text-governance-label">Inclusion Proof — seq {ledgerSeq}</p>
      {isLoading && <p className="text-governance-muted">Verifying...</p>}
      {isError && (
        <p className="text-decision-denied" role="alert">
          Verification request failed — ledger may be unreachable.
        </p>
      )}
      {data && (
        <>
          <p
            className={data.valid ? 'text-decision-allowed' : 'text-decision-denied'}
            role="status"
            aria-live="polite"
          >
            {data.valid ? 'PROOF VALID' : 'PROOF INVALID — TAMPER SUSPECTED'}
          </p>
          <p className="text-governance-muted break-all">
            root hash: {data.root_hash}
          </p>
          <p className="text-governance-muted">
            tree size: {data.tree_size.toLocaleString()} · verified: {data.verified_at}
          </p>
        </>
      )}
    </div>
  );
}
```

#### Tenant Switcher

The admin console is multi-tenant. The active tenant is held in a React context and is passed as `X-Tenant-Id` on every kernel API call. Switching tenants invalidates all queries — no cross-tenant data leaks through the query cache (mirrors ADR F-07 / tenant isolation invariant).

```typescript
// context/TenantContext.tsx
'use client';

import { createContext, useContext, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

type TenantContextValue = {
  tenantId: string;
  availableTenants: { id: string; name: string }[];
  switchTenant: (id: string) => void;
};

const TenantContext = createContext<TenantContextValue | null>(null);

export function TenantProvider({
  children,
  initialTenantId,
  availableTenants,
}: {
  children: React.ReactNode;
  initialTenantId: string;
  availableTenants: { id: string; name: string }[];
}) {
  const qc = useQueryClient();
  const [tenantId, setTenantId] = useState(initialTenantId);

  const switchTenant = (id: string) => {
    setTenantId(id);
    // Purge entire query cache on tenant switch — no cross-tenant leakage
    qc.clear();
  };

  return (
    <TenantContext value={{ tenantId, availableTenants, switchTenant }}>
      {children}
    </TenantContext>
  );
}

export function useTenant(): TenantContextValue {
  const ctx = useContext(TenantContext);
  if (!ctx) throw new Error('useTenant must be used inside TenantProvider');
  return ctx;
}

// TenantSwitcher UI component
export function TenantSwitcher() {
  const { tenantId, availableTenants, switchTenant } = useTenant();

  return (
    <select
      value={tenantId}
      onChange={e => switchTenant(e.target.value)}
      className="text-sm border border-governance-border rounded px-2 py-1 bg-governance-surface"
      aria-label="Active tenant"
    >
      {availableTenants.map(t => (
        <option key={t.id} value={t.id}>
          {t.name}
        </option>
      ))}
    </select>
  );
}
```

### React Query patterns for QUAICU API

```typescript
// lib/quaicu-query-client.ts
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Governance data must be fresh — short stale times
      staleTime: 10_000,
      // Retry once; kernel is fail-closed so repeated retries may mask real errors
      retry: 1,
      retryDelay: 1_000,
    },
    mutations: {
      // All mutations are governed actions; let kernel errors surface
      retry: false,
    },
  },
});

// Query key factories — keep consistent across components
export const quaicuKeys = {
  ledger: {
    trail: (tenantId: string, entityId: string) =>
      ['ledger', 'trail', tenantId, entityId] as const,
    verify: (tenantId: string, seq: number) =>
      ['ledger', 'verify', tenantId, seq] as const,
  },
  hitl: {
    queue: (tenantId: string) => ['hitl', 'queue', tenantId] as const,
    item: (tenantId: string, actionId: string) =>
      ['hitl', 'item', tenantId, actionId] as const,
  },
  policy: {
    list: (tenantId: string) => ['policies', tenantId] as const,
    version: (tenantId: string, policyId: string, version: number) =>
      ['policy', tenantId, policyId, version] as const,
    impact: (tenantId: string, policyId: string, version: number) =>
      ['policy', 'impact', tenantId, policyId, version] as const,
  },
} as const;
```

### Invariants for console developers

- Every kernel API call must include `X-Tenant-Id`. A missing header is a kernel error (fail-closed).
- Never render ledger data from a different tenant — the query cache is scoped per `tenantId`; `qc.clear()` on switch.
- HITL approve/reject mutations use `retry: false` — a duplicate submit would double-decide; the kernel's idempotency key guards the server side but the UI must not retry.
- The `LedgerVerifyPanel` result must never be cached for longer than the polling interval of the trail — proofs reflect the live tree head.
- The `PolicyAuthoringForm` must validate CEL client-side before submit, but the kernel's CEL compile-check is the authoritative gate.
