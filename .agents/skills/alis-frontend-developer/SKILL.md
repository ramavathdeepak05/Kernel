---
name: alis-frontend-developer
description: |
  ALIS-specific frontend development patterns for the web/ directory. Use when building UI screens,
  components, hooks, or services for the ALIS ERP frontend. Covers React 19, Tailwind v4, Radix UI,
  Zustand auth store, TanStack Query, service layer with apiFetch, module-specific hooks, and ERP
  screen patterns (dashboards, data tables, review queues, approval flows). Trigger keywords: web/,
  React component, Tailwind, Radix, Zustand, useAuthStore, apiFetch, admissions UI, student portal,
  dashboard, frontend screen, ALIS UI, module screen, review queue, approval UI, data table, form.
---

# ALIS Frontend Developer

You are the ALIS Frontend Expert. All UI work lives in `web/` and follows the patterns below.

## Tech Stack

- **Framework**: React 19 (no class components, use hooks)
- **Build**: Vite 7
- **Styling**: Tailwind CSS v4 (no arbitrary values unless necessary)
- **Components**: Radix UI primitives + custom composition
- **State**: Zustand (`useAuthStore` for auth, module-level stores as needed)
- **Server State**: TanStack Query v5 (`@tanstack/react-query`)
- **TypeScript**: Strict — all props, state, and API responses typed

## Project Structure

```
web/src/
    components/       # Reusable UI components
        ui/           # Base primitives (Button, Input, Badge, Table, etc.)
        layout/       # Shell, Sidebar, Header, PageWrapper
        modules/      # Module-specific components
    pages/            # Route-level pages (one per module screen)
    hooks/            # TanStack Query hooks (use-admissions.ts, use-academics.ts, ...)
    services/         # API call functions (admissions.ts, finance.ts, ...)
    store/            # Zustand stores (authStore.ts, uiStore.ts)
    types/            # TypeScript interfaces (admissions.ts, auth.ts, ...)
    lib/              # queryClient.ts, utils.ts
```

## API Service Pattern

Every module has a service file that uses `apiFetch`:

```typescript
// web/src/services/admissions.ts
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const token = localStorage.getItem("token");
    const headers = {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
    };
    const response = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(error.detail || "API request failed");
    }
    return response.json();
}

export const admissionsApi = {
    getApplicants: (params?: { limit?: number }) =>
        apiFetch<Applicant[]>(`/admissions/applicants?limit=${params?.limit ?? 50}`),
    createApplicant: (body: ApplicantCreate) =>
        apiFetch<Applicant>("/admissions/applicants", { method: "POST", body: JSON.stringify(body) }),
};
```

API prefix is `/api/v1/` on the backend. The service strips the `/api` prefix since `API_BASE` already includes it. Always use `/v1/` in endpoint strings: `apiFetch<T>("/v1/admissions/applicants")`.

## TanStack Query Hook Pattern

```typescript
// web/src/hooks/use-admissions.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { admissionsApi } from "../services/admissions";

export function useApplicants(limit = 50) {
    return useQuery({
        queryKey: ["applicants", limit],
        queryFn: () => admissionsApi.getApplicants({ limit }),
    });
}

export function useCreateApplicant() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: admissionsApi.createApplicant,
        onSuccess: () => qc.invalidateQueries({ queryKey: ["applicants"] }),
    });
}
```

## Auth Store

```typescript
import { useAuthStore } from "../store/authStore";

const { user, isAuthenticated, logout } = useAuthStore();
// user.role — check against Role enum values from RBAC
// e.g. user.role === "registrar", "admin", "student", etc.
```

Never redirect without checking `isAuthenticated`. Always handle `isLoading` state.

## ERP Screen Patterns

### Module Dashboard
```
<PageWrapper title="Admissions">
  <StatsRow>           {/* KPI cards: counts, rates */}
  <PipelineSummary>    {/* Stage funnel or Kanban */}
  <RecentActivity>     {/* Latest events/actions */}
  <QuickActions>       {/* Primary CTAs */}
</PageWrapper>
```

### Data Table (List Screen)
```typescript
// Use TanStack Table or simple <table> with Tailwind
// Always include: loading skeleton, empty state, error state
// Pagination: ?skip=N&limit=50 pattern
// Search/filter as controlled input with debounce
```

### Review Queue Screen
```
// Shows items awaiting human decision
// Each row: entity summary + AI recommendation + confidence + action buttons
// Actions: Approve / Reject / Escalate / Request More Info
// After action: optimistic update + invalidate query
```

### Approval / Detail Screen
```
// Route: /module/resource/:id
// Sections: Entity details | Audit timeline | AI analysis | Action panel
// Action panel: role-gated (hide buttons user can't use)
// Show audit trail as vertical timeline
```

## Role-Gated UI

```typescript
const { user } = useAuthStore();

// Show/hide based on role
const canApprove = ["registrar", "admin", "super_admin"].includes(user?.role ?? "");

{canApprove && <Button onClick={handleApprove}>Approve</Button>}
```

Match role strings to `Role` enum values in `server/core/rbac.py` (lowercase).

## Component Conventions

- All components: named exports, TypeScript props interface
- Forms: controlled inputs, inline validation, disabled submit while pending
- Error states: use `toast` or inline error message, never silent failures
- Loading: skeleton screens (not spinners) for data-heavy pages
- Empty states: descriptive message + primary action CTA
- Monetary values: always display as INR with 2 decimal places (`₹1,23,456.00`)
- Dates: ISO strings from API → format with `Intl.DateTimeFormat` (locale: `en-IN`)
- UUIDs: never display raw — use a truncated display ID or name

## Tailwind v4 Notes

- Use `@apply` sparingly — prefer utility classes inline
- Color tokens: use semantic names (`bg-primary`, `text-muted-foreground`)
- No `purge` config needed — v4 handles it automatically
- Dark mode: use `dark:` prefix variants

## Existing Module File Examples

The Academics module has complete service/hook/page files to use as a reference pattern:

```
web/src/services/academics.ts          # academicsApi — uses apiFetch, typed responses
web/src/hooks/use-academics.ts         # useAcademics*, useMutateAcademics* — TanStack Query
web/src/pages/academics/AcademicsPage.tsx   # Route-level page consuming the hook
```

Follow this 3-layer pattern (service → hook → page) for every new module screen.

## Module-to-Screen Mapping

| Module | Route Prefix | Key Screens |
|---|---|---|
| Auth | `/auth` | Login, Profile |
| Admissions (E04) | `/admissions` | Dashboard, Applicants, Review Queue, Eligibility |
| Academics (E05) | `/academics` | Courses, Enrollment, Marks Entry |
| Examinations (E06) | `/examinations` | Hall Tickets, Results, Seating |
| Finance (E07) | `/finance` | Fee Structure, Payments, Ledger |
| HR (E08) | `/hr` | Staff, Leave, Payroll |
| Student Services (E09) | `/student-services` | Hostel, Transport, Grievances |
| Communication (E10) | `/communication` | Announcements, Notifications, Bulk Messages |
| Reporting (E11) | `/reports` | Report Builder, Exports, Analytics |
| Alumni (E12) | `/alumni` | Profiles, Placement Drives, Job Board |
| Process Engine (E13) | `/processes` | Process Definitions, Instances, Forms |

## Common Mistakes to Avoid

- Calling the API directly in components — always use service + hook layers
- Hardcoding tenant/org IDs — read from `user.org_id` via auth store
- Using `any` type for API responses — define interfaces in `types/`
- Not handling loading and error states in every data-fetching component
- Mutating query cache directly — always use `invalidateQueries` or `setQueryData`
- Displaying raw UUIDs or ISO timestamps without formatting
