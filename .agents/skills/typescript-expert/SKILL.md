---
name: typescript-expert
description: TypeScript and JavaScript expert with deep knowledge of type-level programming, performance optimization, monorepo management, migration strategies, and modern tooling. QUAICU kernel — the React 19 admin console; a view plus approval surface only (no governance logic client-side), Zod-validated API I/O (no as-casts), exhaustive ActionState rendering, TenantProvider scoping. Triggers — QUAICU, admin console, ActionState, Zod, TenantProvider, HITL queue, discriminated union.
category: framework
risk: critical
source: community
date_added: '2026-02-27'
---

# TypeScript Expert

## ⚡ QUAICU Decision Contract — READ THIS FIRST (when used for the QUAICU kernel)

> Makes the QUAICU-specific admin-console choices mechanical so a small/low-token model matches a top model at max effort.
> **For QUAICU work, this block overrides the general guidance below.**

### Invariants — never violated
- The console is a VIEW + an approval surface. It NEVER makes or re-implements a governance decision — it renders kernel state and submits requests. Authorization is enforced server-side; hiding a button is not security.
- Validate every API payload at the boundary with Zod; types are derived from the schema (`z.infer`). NEVER cast API JSON with `as`.
- The full `ActionState` union is a discriminated type; rendering handles EVERY state (no default rendering of an unknown state as allowed).
- Tenant context flows through a `TenantProvider`; the displayed tenant comes from the authenticated session, never user input.
- Never display raw PII / unmasked prompts; render what the kernel returns (already masked).

### Decision table
| Need | Do exactly this |
|---|---|
| Parse API response | Zod schema → `z.infer`; reject on parse failure |
| Render an action | exhaustive switch over ActionState (compile error if a case is missing) |
| Approve/reject (HITL) | submit to the kernel; reflect returned state; never assume success |
| Tenant scoping | from TenantProvider/session, never user input |

### Tie-break rules
- Cast vs validate an API value? → validate (Zod). Casting hides drift.
- Enforce a permission in the UI only? → no; server-side is the boundary, UI is convenience.

### Self-check
- [ ] No governance logic in the client; server-side enforced.
- [ ] All API I/O Zod-validated; no `as` casts on API data.
- [ ] ActionState handled exhaustively.
- [ ] Tenant from session; no PII/unmasked prompts rendered.

---

You are an advanced TypeScript expert with deep, practical knowledge of type-level programming, performance optimization, and real-world problem solving based on current best practices.

### When invoked:

0. If the issue requires ultra-specific expertise, recommend switching and stop:
   - Deep webpack/vite/rollup bundler internals → typescript-build-expert
   - Complex ESM/CJS migration or circular dependency analysis → typescript-module-expert
   - Type performance profiling or compiler internals → typescript-type-expert

   Example to output:
   "This requires deep bundler expertise. Please invoke: 'Use the typescript-build-expert subagent.' Stopping here."

1. Analyze project setup comprehensively:
   
   **Use internal tools first (Read, Grep, Glob) for better performance. Shell commands are fallbacks.**
   
   ```bash
   # Core versions and configuration
   npx tsc --version
   node -v
   # Detect tooling ecosystem (prefer parsing package.json)
   node -e "const p=require('./package.json');console.log(Object.keys({...p.devDependencies,...p.dependencies}||{}).join('\n'))" 2>/dev/null | grep -E 'biome|eslint|prettier|vitest|jest|turborepo|nx' || echo "No tooling detected"
   # Check for monorepo (fixed precedence)
   (test -f pnpm-workspace.yaml || test -f lerna.json || test -f nx.json || test -f turbo.json) && echo "Monorepo detected"
   ```
   
   **After detection, adapt approach:**
   - Match import style (absolute vs relative)
   - Respect existing baseUrl/paths configuration
   - Prefer existing project scripts over raw tools
   - In monorepos, consider project references before broad tsconfig changes

2. Identify the specific problem category and complexity level

3. Apply the appropriate solution strategy from my expertise

4. Validate thoroughly:
   ```bash
   # Fast fail approach (avoid long-lived processes)
   npm run -s typecheck || npx tsc --noEmit
   npm test -s || npx vitest run --reporter=basic --no-watch
   # Only if needed and build affects outputs/config
   npm run -s build
   ```
   
   **Safety note:** Avoid watch/serve processes in validation. Use one-shot diagnostics only.

## Advanced Type System Expertise

### Type-Level Programming Patterns

**Branded Types for Domain Modeling**
```typescript
// Create nominal types to prevent primitive obsession
type Brand<K, T> = K & { __brand: T };
type UserId = Brand<string, 'UserId'>;
type OrderId = Brand<string, 'OrderId'>;

// Prevents accidental mixing of domain primitives
function processOrder(orderId: OrderId, userId: UserId) { }
```
- Use for: Critical domain primitives, API boundaries, currency/units
- Resource: https://egghead.io/blog/using-branded-types-in-typescript

**Advanced Conditional Types**
```typescript
// Recursive type manipulation
type DeepReadonly<T> = T extends (...args: any[]) => any 
  ? T 
  : T extends object 
    ? { readonly [K in keyof T]: DeepReadonly<T[K]> }
    : T;

// Template literal type magic
type PropEventSource<Type> = {
  on<Key extends string & keyof Type>
    (eventName: `${Key}Changed`, callback: (newValue: Type[Key]) => void): void;
};
```
- Use for: Library APIs, type-safe event systems, compile-time validation
- Watch for: Type instantiation depth errors (limit recursion to 10 levels)

**Type Inference Techniques**
```typescript
// Use 'satisfies' for constraint validation (TS 5.0+)
const config = {
  api: "https://api.example.com",
  timeout: 5000
} satisfies Record<string, string | number>;
// Preserves literal types while ensuring constraints

// Const assertions for maximum inference
const routes = ['/home', '/about', '/contact'] as const;
type Route = typeof routes[number]; // '/home' | '/about' | '/contact'
```

### Performance Optimization Strategies

**Type Checking Performance**
```bash
# Diagnose slow type checking
npx tsc --extendedDiagnostics --incremental false | grep -E "Check time|Files:|Lines:|Nodes:"

# Common fixes for "Type instantiation is excessively deep"
# 1. Replace type intersections with interfaces
# 2. Split large union types (>100 members)
# 3. Avoid circular generic constraints
# 4. Use type aliases to break recursion
```

**Build Performance Patterns**
- Enable `skipLibCheck: true` for library type checking only (often significantly improves performance on large projects, but avoid masking app typing issues)
- Use `incremental: true` with `.tsbuildinfo` cache
- Configure `include`/`exclude` precisely
- For monorepos: Use project references with `composite: true`

## Real-World Problem Resolution

### Complex Error Patterns

**"The inferred type of X cannot be named"**
- Cause: Missing type export or circular dependency
- Fix priority:
  1. Export the required type explicitly
  2. Use `ReturnType<typeof function>` helper
  3. Break circular dependencies with type-only imports
- Resource: https://github.com/microsoft/TypeScript/issues/47663

**Missing type declarations**
- Quick fix with ambient declarations:
```typescript
// types/ambient.d.ts
declare module 'some-untyped-package' {
  const value: unknown;
  export default value;
  export = value; // if CJS interop is needed
}
```
- For more details: [Declaration Files Guide](https://www.typescriptlang.org/docs/handbook/declaration-files/introduction.html)

**"Excessive stack depth comparing types"**
- Cause: Circular or deeply recursive types
- Fix priority:
  1. Limit recursion depth with conditional types
  2. Use `interface` extends instead of type intersection
  3. Simplify generic constraints
```typescript
// Bad: Infinite recursion
type InfiniteArray<T> = T extends (...args: any[]) => any ? T : InfiniteArray<T>[];

// Good: Limited recursion
type NestedArray<T, D extends number = 5> = 
  D extends 0 ? T : T | NestedArray<T, [-1, 0, 1, 2, 3, 4][D]>[];
```

**Module Resolution Mysteries**
- "Cannot find module" despite file existing:
  1. Check `moduleResolution` matches your bundler
  2. Verify `baseUrl` and `paths` alignment
  3. For monorepos: Ensure workspace protocol (workspace:*)
  4. Try clearing cache: `rm -rf node_modules/.cache .tsbuildinfo`

**Path Mapping at Runtime**
- TypeScript paths only work at compile time, not runtime
- Node.js runtime solutions:
  - ts-node: Use `ts-node -r tsconfig-paths/register`
  - Node ESM: Use loader alternatives or avoid TS paths at runtime
  - Production: Pre-compile with resolved paths

### Migration Expertise

**JavaScript to TypeScript Migration**
```bash
# Incremental migration strategy
# 1. Enable allowJs and checkJs (merge into existing tsconfig.json):
# Add to existing tsconfig.json:
# {
#   "compilerOptions": {
#     "allowJs": true,
#     "checkJs": true
#   }
# }

# 2. Rename files gradually (.js → .ts)
# 3. Add types file by file using AI assistance
# 4. Enable strict mode features one by one

# Automated helpers (if installed/needed)
command -v ts-migrate >/dev/null 2>&1 && npx ts-migrate migrate . --sources 'src/**/*.js'
command -v typesync >/dev/null 2>&1 && npx typesync  # Install missing @types packages
```

**Tool Migration Decisions**

| From | To | When | Migration Effort |
|------|-----|------|-----------------|
| ESLint + Prettier | Biome | Need much faster speed, okay with fewer rules | Low (1 day) |
| TSC for linting | Type-check only | Have 100+ files, need faster feedback | Medium (2-3 days) |
| Lerna | Nx/Turborepo | Need caching, parallel builds | High (1 week) |
| CJS | ESM | Node 18+, modern tooling | High (varies) |

### Monorepo Management

**Nx vs Turborepo Decision Matrix**
- Choose **Turborepo** if: Simple structure, need speed, <20 packages
- Choose **Nx** if: Complex dependencies, need visualization, plugins required
- Performance: Nx often performs better on large monorepos (>50 packages)

**TypeScript Monorepo Configuration**
```json
// Root tsconfig.json
{
  "references": [
    { "path": "./packages/core" },
    { "path": "./packages/ui" },
    { "path": "./apps/web" }
  ],
  "compilerOptions": {
    "composite": true,
    "declaration": true,
    "declarationMap": true
  }
}
```

## Modern Tooling Expertise

### Biome vs ESLint

**Use Biome when:**
- Speed is critical (often faster than traditional setups)
- Want single tool for lint + format
- TypeScript-first project
- Okay with 64 TS rules vs 100+ in typescript-eslint

**Stay with ESLint when:**
- Need specific rules/plugins
- Have complex custom rules
- Working with Vue/Angular (limited Biome support)
- Need type-aware linting (Biome doesn't have this yet)

### Type Testing Strategies

**Vitest Type Testing (Recommended)**
```typescript
// in avatar.test-d.ts
import { expectTypeOf } from 'vitest'
import type { Avatar } from './avatar'

test('Avatar props are correctly typed', () => {
  expectTypeOf<Avatar>().toHaveProperty('size')
  expectTypeOf<Avatar['size']>().toEqualTypeOf<'sm' | 'md' | 'lg'>()
})
```

**When to Test Types:**
- Publishing libraries
- Complex generic functions
- Type-level utilities
- API contracts

## Debugging Mastery

### CLI Debugging Tools
```bash
# Debug TypeScript files directly (if tools installed)
command -v tsx >/dev/null 2>&1 && npx tsx --inspect src/file.ts
command -v ts-node >/dev/null 2>&1 && npx ts-node --inspect-brk src/file.ts

# Trace module resolution issues
npx tsc --traceResolution > resolution.log 2>&1
grep "Module resolution" resolution.log

# Debug type checking performance (use --incremental false for clean trace)
npx tsc --generateTrace trace --incremental false
# Analyze trace (if installed)
command -v @typescript/analyze-trace >/dev/null 2>&1 && npx @typescript/analyze-trace trace

# Memory usage analysis
node --max-old-space-size=8192 node_modules/typescript/lib/tsc.js
```

### Custom Error Classes
```typescript
// Proper error class with stack preservation
class DomainError extends Error {
  constructor(
    message: string,
    public code: string,
    public statusCode: number
  ) {
    super(message);
    this.name = 'DomainError';
    Error.captureStackTrace(this, this.constructor);
  }
}
```

## Current Best Practices

### Strict by Default
```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "exactOptionalPropertyTypes": true,
    "noPropertyAccessFromIndexSignature": true
  }
}
```

### ESM-First Approach
- Set `"type": "module"` in package.json
- Use `.mts` for TypeScript ESM files if needed
- Configure `"moduleResolution": "bundler"` for modern tools
- Use dynamic imports for CJS: `const pkg = await import('cjs-package')`
  - Note: `await import()` requires async function or top-level await in ESM
  - For CJS packages in ESM: May need `(await import('pkg')).default` depending on the package's export structure and your compiler settings

### AI-Assisted Development
- GitHub Copilot excels at TypeScript generics
- Use AI for boilerplate type definitions
- Validate AI-generated types with type tests
- Document complex types for AI context

## Code Review Checklist

When reviewing TypeScript/JavaScript code, focus on these domain-specific aspects:

### Type Safety
- [ ] No implicit `any` types (use `unknown` or proper types)
- [ ] Strict null checks enabled and properly handled
- [ ] Type assertions (`as`) justified and minimal
- [ ] Generic constraints properly defined
- [ ] Discriminated unions for error handling
- [ ] Return types explicitly declared for public APIs

### TypeScript Best Practices
- [ ] Prefer `interface` over `type` for object shapes (better error messages)
- [ ] Use const assertions for literal types
- [ ] Leverage type guards and predicates
- [ ] Avoid type gymnastics when simpler solution exists
- [ ] Template literal types used appropriately
- [ ] Branded types for domain primitives

### Performance Considerations
- [ ] Type complexity doesn't cause slow compilation
- [ ] No excessive type instantiation depth
- [ ] Avoid complex mapped types in hot paths
- [ ] Use `skipLibCheck: true` in tsconfig
- [ ] Project references configured for monorepos

### Module System
- [ ] Consistent import/export patterns
- [ ] No circular dependencies
- [ ] Proper use of barrel exports (avoid over-bundling)
- [ ] ESM/CJS compatibility handled correctly
- [ ] Dynamic imports for code splitting

### Error Handling Patterns
- [ ] Result types or discriminated unions for errors
- [ ] Custom error classes with proper inheritance
- [ ] Type-safe error boundaries
- [ ] Exhaustive switch cases with `never` type

### Code Organization
- [ ] Types co-located with implementation
- [ ] Shared types in dedicated modules
- [ ] Avoid global type augmentation when possible
- [ ] Proper use of declaration files (.d.ts)

## Quick Decision Trees

### "Which tool should I use?"
```
Type checking only? → tsc
Type checking + linting speed critical? → Biome  
Type checking + comprehensive linting? → ESLint + typescript-eslint
Type testing? → Vitest expectTypeOf
Build tool? → Project size <10 packages? Turborepo. Else? Nx
```

### "How do I fix this performance issue?"
```
Slow type checking? → skipLibCheck, incremental, project references
Slow builds? → Check bundler config, enable caching
Slow tests? → Vitest with threads, avoid type checking in tests
Slow language server? → Exclude node_modules, limit files in tsconfig
```

## Expert Resources

### Performance
- [TypeScript Wiki Performance](https://github.com/microsoft/TypeScript/wiki/Performance)
- [Type instantiation tracking](https://github.com/microsoft/TypeScript/pull/48077)

### Advanced Patterns
- [Type Challenges](https://github.com/type-challenges/type-challenges)
- [Type-Level TypeScript Course](https://type-level-typescript.com)

### Tools
- [Biome](https://biomejs.dev) - Fast linter/formatter
- [TypeStat](https://github.com/JoshuaKGoldberg/TypeStat) - Auto-fix TypeScript types
- [ts-migrate](https://github.com/airbnb/ts-migrate) - Migration toolkit

### Testing
- [Vitest Type Testing](https://vitest.dev/guide/testing-types)
- [tsd](https://github.com/tsdjs/tsd) - Standalone type testing

Always validate changes don't break existing functionality before considering the issue resolved.

## When to Use
This skill is applicable to execute the workflow or actions described in the overview.

## Limitations
- Use this skill only when the task clearly matches the scope described above.
- Do not treat the output as a substitute for environment-specific validation, testing, or expert review.
- Stop and ask for clarification if required inputs, permissions, safety boundaries, or success criteria are missing.

---

## QUAICU-Specific Application

This section extends the TypeScript expert skill with patterns specific to the QUAICU React 19 admin console. The admin console lives in `delivery/api/` (OpenAPI schema source) and a separate `console/` frontend package. It is the operational surface through which governance teams manage policies, review HITL queues, verify ledger integrity, and read impact reports.

### Core Domain Types — Mirror the Kernel Glossary Exactly

The TypeScript type system must use the **exact terms from the QUAICU glossary** (spec Glossary section). Never use synonyms. Types in the console that diverge from kernel terminology become a maintenance liability and confuse reviewers comparing console UI against kernel audit logs.

```typescript
// console/src/types/kernel.ts
// These types are the source-of-truth aliases for kernel domain concepts.
// They are generated from the FastAPI OpenAPI schema (see api-client section below)
// but re-exported here with the canonical names for use throughout the console.

import type { components } from "../generated/api-schema";  // openapi-typescript output

// ── Core lifecycle concepts ───────────────────────────────────────────────
/** A proposed change to institutional state — the atomic unit the kernel governs. */
export type Action = components["schemas"]["ActionResponse"];

/**
 * An action that has NOT yet completed the lifecycle.
 * Distinguished from GovernedAction which has completed evaluate→gate→execute→seal→emit.
 */
export type Proposal = components["schemas"]["ProposalResponse"];

/**
 * An action that has completed the FULL lifecycle.
 * evaluate → gate → execute → seal → emit all passed.
 */
export type GovernedAction = components["schemas"]["GovernedActionResponse"];

/** A rule stored as data — CEL condition + decision envelope. */
export type Policy = components["schemas"]["PolicyResponse"];

/** Result of the Policy Engine evaluating an action. */
export type EvaluationResult = components["schemas"]["EvaluationResultResponse"];

/** HITL checkpoint state. */
export type Gate = components["schemas"]["GateResponse"];

/** A sealed TrustLedger entry with its RFC 6962 inclusion proof. */
export type LedgerEntry = components["schemas"]["LedgerEntryResponse"];

/** RFC 6962 consistency or inclusion proof. */
export type LedgerProof = components["schemas"]["LedgerProofResponse"];

// ── Architecture concepts ─────────────────────────────────────────────────
/**
 * Port — interface in core/ports/ that core depends on.
 * The console does NOT call ports directly; this type is used in config UIs.
 */
export type PortName = "InferencePort" | "HITLPort" | "IdentityPort" | "StoragePort" | "WorkflowPort";

/**
 * Adapter — a concrete implementation of a port, selected by config.
 * Used in the deployment config panel.
 */
export type AdapterRef = components["schemas"]["AdapterRefResponse"];

// ── Action lifecycle state machine ────────────────────────────────────────
export type ActionState =
  | "PROPOSED"
  | "EVALUATING"
  | "PENDING_APPROVAL"   // halted at Gate (K·03), awaiting HITL
  | "APPROVED"
  | "REJECTED"
  | "EXECUTING"
  | "EXECUTED"
  | "SEALED"             // written to TrustLedger
  | "EMITTED"            // event published
  | "DENIED"             // policy denied — never executed
  | "ERROR";             // fail-closed halt

// ── Policy lifecycle ──────────────────────────────────────────────────────
export type PolicyLifecycle = "DRAFT" | "REVIEW" | "ACTIVATED" | "DEPRECATED";
```

### Zod Schemas Mirroring Kernel Action Types

The admin console must validate all user input before sending to the kernel API. Zod schemas must mirror the kernel's action payload shapes exactly — divergence causes silent data corruption in the governance record.

```typescript
// console/src/schemas/action.ts
import { z } from "zod";

// ── Shared primitives ─────────────────────────────────────────────────────
const TenantId = z.string().uuid("tenant_id must be a UUID");
const ActionId = z.string().uuid("action_id must be a UUID");
const IdempotencyKey = z.string().min(1).max(255);

// ── Policy envelope — mirrors spec §3.9 exactly ───────────────────────────
export const PolicyScopeSchema = z.object({
  tenant: z.string().min(1),       // "*" for global, or specific tenant slug
  segment: z.string().optional(),
});

export const PolicyEnvelopeSchema = z.object({
  id: z.string().regex(/^[a-z0-9._-]+$/, "Policy ID must be lowercase dot-separated"),
  version: z.number().int().positive(),
  governs: z.string().min(1),              // action type this policy applies to
  scope: PolicyScopeSchema,
  condition: z.string().min(1),            // CEL expression
  decision: z.enum(["allow", "deny", "require_approval"]),
  approvers: z.array(z.string()).optional(),
  regulatory_refs: z.array(z.string()).optional(),
  lifecycle: z.enum(["DRAFT", "REVIEW", "ACTIVATED", "DEPRECATED"]),
});

export type PolicyEnvelope = z.infer<typeof PolicyEnvelopeSchema>;

// ── Action proposal — mirrors POST /kernel/v1/actions/propose ────────────
export const ProposeActionSchema = z.object({
  type: z.string().regex(/^[a-z0-9._-]+$/,
    "Action type must be a lowercase dot-separated identifier e.g. ciro.ifrs9.stage_transition"),
  payload: z.record(z.unknown()),          // type-specific; validated by kernel
  idempotency_key: IdempotencyKey,
  // NOTE: tenant_id is NEVER in the request body — it is extracted from the JWT claim
  // Any UI that allows users to set tenant_id in the payload is a security bug.
});

export type ProposeAction = z.infer<typeof ProposeActionSchema>;

// ── HITL approval decision ────────────────────────────────────────────────
export const ApprovalDecisionSchema = z.object({
  action_id: ActionId,
  decision: z.enum(["APPROVED", "REJECTED"]),
  rationale: z.string().min(10, "Rationale must be at least 10 characters — this is an audit record"),
  approver_ref: z.string().min(1),
});

export type ApprovalDecision = z.infer<typeof ApprovalDecisionSchema>;
```

### Type-Safe API Client Generated from FastAPI OpenAPI Schema

The FastAPI delivery adapter generates an OpenAPI schema at `/openapi.json`. Use `openapi-typescript` to generate types from it and `openapi-fetch` for the type-safe client. This eliminates hand-written API types and keeps the console in sync with the kernel automatically.

```typescript
// console/scripts/generate-api-types.ts
// Run during build: npx openapi-typescript http://localhost:7000/openapi.json -o src/generated/api-schema.d.ts

// console/src/lib/api-client.ts
import createClient from "openapi-fetch";
import type { paths } from "../generated/api-schema";

// The tenant context is injected by the TenantProvider (see below) —
// never passed manually per-call.
let currentTenantId: string | null = null;

export function setClientTenant(tenantId: string): void {
  currentTenantId = tenantId;
}

export const kernelClient = createClient<paths>({
  baseUrl: import.meta.env.VITE_KERNEL_API_URL ?? "http://localhost:7000",
  headers: {
    "Content-Type": "application/json",
  },
});

// Middleware: attach Authorization header from session on every request
kernelClient.use({
  async onRequest({ request }) {
    const token = sessionStorage.getItem("kernel_jwt");
    if (token) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    // NEVER add X-Tenant-ID from client — tenant is derived from JWT claim server-side.
    // Adding it here would be a bypass attempt that the API rejects.
    return request;
  },
});
```

### TenantProvider — Tenant Context in React

The admin console is multi-tenant. Every component that displays data must be scoped to the active tenant. Use a React context rather than prop drilling, and derive the tenant from the authenticated JWT — never from a URL parameter or user-editable input.

```typescript
// console/src/contexts/TenantContext.tsx
import React, { createContext, useContext, useEffect, useState } from "react";
import { jwtDecode } from "jwt-decode";
import { setClientTenant } from "../lib/api-client";

interface TenantClaims {
  tenant_id: string;
  tenant_slug: string;
  tenant_name: string;
  roles: string[];
}

interface TenantContextValue {
  tenantId: string;
  tenantSlug: string;
  tenantName: string;
  roles: string[];
  isLoading: boolean;
}

const TenantContext = createContext<TenantContextValue | null>(null);

export function TenantProvider({ children }: { children: React.ReactNode }) {
  const [tenant, setTenant] = useState<TenantContextValue>({
    tenantId: "",
    tenantSlug: "",
    tenantName: "",
    roles: [],
    isLoading: true,
  });

  useEffect(() => {
    const token = sessionStorage.getItem("kernel_jwt");
    if (!token) {
      // Fail-closed: no JWT = no tenant context = redirect to login
      window.location.href = "/login";
      return;
    }

    try {
      const claims = jwtDecode<TenantClaims>(token);
      // tenant_id comes from the JWT claim — never from the URL or user input
      setClientTenant(claims.tenant_id);
      setTenant({
        tenantId: claims.tenant_id,
        tenantSlug: claims.tenant_slug,
        tenantName: claims.tenant_name,
        roles: claims.roles,
        isLoading: false,
      });
    } catch {
      // Malformed JWT — fail closed
      sessionStorage.removeItem("kernel_jwt");
      window.location.href = "/login";
    }
  }, []);

  return (
    <TenantContext.Provider value={tenant}>
      {children}
    </TenantContext.Provider>
  );
}

export function useTenant(): TenantContextValue {
  const ctx = useContext(TenantContext);
  if (!ctx) throw new Error("useTenant must be used within TenantProvider");
  return ctx;
}
```

### Action Trail Table

The action trail table renders the audit history for an entity. It must show the full lifecycle state, be sortable by timestamp, and link to the ledger proof for sealed entries. Never render a "loading" state that could be mistaken for an empty trail — distinguish between "loading," "empty," and "error" explicitly.

```typescript
// console/src/components/ActionTrailTable.tsx
import React from "react";
import { useQuery } from "@tanstack/react-query";
import { kernelClient } from "../lib/api-client";
import { useTenant } from "../contexts/TenantContext";
import type { GovernedAction, ActionState } from "../types/kernel";

const STATE_LABELS: Record<ActionState, { label: string; color: string }> = {
  PROPOSED:         { label: "Proposed",         color: "gray" },
  EVALUATING:       { label: "Evaluating",        color: "blue" },
  PENDING_APPROVAL: { label: "Pending Approval",  color: "amber" },
  APPROVED:         { label: "Approved",          color: "green" },
  REJECTED:         { label: "Rejected",          color: "red" },
  EXECUTING:        { label: "Executing",         color: "blue" },
  EXECUTED:         { label: "Executed",          color: "green" },
  SEALED:           { label: "Sealed",            color: "emerald" },
  EMITTED:          { label: "Emitted",           color: "emerald" },
  DENIED:           { label: "Denied",            color: "red" },
  ERROR:            { label: "Error (Halted)",    color: "red" },
};

interface ActionTrailTableProps {
  entityId: string;
  entityType: string;
}

export function ActionTrailTable({ entityId, entityType }: ActionTrailTableProps) {
  const { tenantId } = useTenant();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["action-trail", tenantId, entityType, entityId],
    queryFn: async () => {
      const { data, error } = await kernelClient.GET(
        "/kernel/v1/ledger/{entity_type}/{entity_id}/trail",
        { params: { path: { entity_type: entityType, entity_id: entityId } } }
      );
      if (error) throw new Error("Failed to fetch action trail");
      return data;
    },
    refetchInterval: 5000,  // Poll for new entries — PENDING_APPROVAL may resolve
  });

  if (isLoading) return <div aria-busy="true">Loading action trail...</div>;
  if (isError)   return <div role="alert">Failed to load action trail.</div>;
  if (!data || data.entries.length === 0) return <div>No governed actions recorded yet.</div>;

  return (
    <table aria-label={`Action trail for ${entityType} ${entityId}`}>
      <thead>
        <tr>
          <th>Timestamp</th>
          <th>Action Type</th>
          <th>Actor</th>
          <th>State</th>
          <th>Policy</th>
          <th>Ledger Seq</th>
          <th>Proof</th>
        </tr>
      </thead>
      <tbody>
        {data.entries.map((entry) => {
          const stateInfo = STATE_LABELS[entry.state as ActionState];
          return (
            <tr key={entry.action_id}>
              <td>{new Date(entry.timestamp).toISOString()}</td>
              <td><code>{entry.action_type}</code></td>
              <td>{entry.actor_ref}</td>
              <td>
                <span data-color={stateInfo.color}>{stateInfo.label}</span>
              </td>
              <td>{entry.policy_id}@v{entry.policy_version}</td>
              <td>{entry.ledger_seq ?? "—"}</td>
              <td>
                {entry.ledger_seq && (
                  <a href={`/ledger/verify?seq=${entry.ledger_seq}`}>
                    Verify proof
                  </a>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
```

### HITL Approval Queue — Real-Time Polling for PENDING_APPROVAL

Actions in `PENDING_APPROVAL` are halted at the Gate (K·03) waiting for a human decision. The approval queue must poll frequently, show only actions the current user is authorized to approve (based on their `roles` claim), and submit decisions with a mandatory rationale field (the rationale becomes part of the audit record).

```typescript
// console/src/components/HITLApprovalQueue.tsx
import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { kernelClient } from "../lib/api-client";
import { useTenant } from "../contexts/TenantContext";
import { ApprovalDecisionSchema } from "../schemas/action";

export function HITLApprovalQueue() {
  const { tenantId, roles } = useTenant();
  const queryClient = useQueryClient();
  const [rationale, setRationale] = useState<Record<string, string>>({});

  // Poll every 10 seconds — PENDING_APPROVAL actions need timely human response
  const { data: pendingActions } = useQuery({
    queryKey: ["hitl-queue", tenantId],
    queryFn: async () => {
      const { data, error } = await kernelClient.GET("/kernel/v1/hitl/queue", {
        params: { query: { state: "PENDING_APPROVAL" } },
      });
      if (error) throw error;
      return data;
    },
    refetchInterval: 10_000,
    // Only fetch if the user has at least one approver role
    enabled: roles.some((r) => r.startsWith("role:")),
  });

  const approveMutation = useMutation({
    mutationFn: async ({
      actionId,
      decision,
    }: {
      actionId: string;
      decision: "APPROVED" | "REJECTED";
    }) => {
      const payload = ApprovalDecisionSchema.parse({
        action_id: actionId,
        decision,
        rationale: rationale[actionId] ?? "",
        approver_ref: `jwt:${sessionStorage.getItem("kernel_jwt_sub")}`,
      });

      const { error } = await kernelClient.POST(
        "/kernel/v1/actions/{action_id}/approve",
        {
          params: { path: { action_id: actionId } },
          body: payload,
        }
      );
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["hitl-queue", tenantId] });
    },
  });

  if (!pendingActions?.actions.length) {
    return <p>No actions pending approval.</p>;
  }

  return (
    <ul aria-label="HITL Approval Queue">
      {pendingActions.actions.map((action) => (
        <li key={action.action_id}>
          <strong>{action.action_type}</strong>
          <span>Submitted by {action.actor_ref}</span>
          <span>{new Date(action.proposed_at).toLocaleString()}</span>
          <p>Policy: {action.policy_id} — requires approval from: {action.required_approvers.join(", ")}</p>
          <textarea
            aria-label="Approval rationale (required for audit trail)"
            placeholder="State your rationale — this becomes part of the permanent audit record"
            value={rationale[action.action_id] ?? ""}
            onChange={(e) =>
              setRationale((prev) => ({ ...prev, [action.action_id]: e.target.value }))
            }
            minLength={10}
          />
          <button
            disabled={!rationale[action.action_id] || approveMutation.isPending}
            onClick={() => approveMutation.mutate({ actionId: action.action_id, decision: "APPROVED" })}
          >
            Approve
          </button>
          <button
            disabled={!rationale[action.action_id] || approveMutation.isPending}
            onClick={() => approveMutation.mutate({ actionId: action.action_id, decision: "REJECTED" })}
          >
            Reject
          </button>
        </li>
      ))}
    </ul>
  );
}
```

### Policy Authoring Form

The policy authoring form renders a policy envelope (spec §3.9) and must: validate the CEL condition syntax on blur (via a dry-run API call), enforce the activation gate (a policy cannot be manually set to ACTIVATED in the UI — it must complete the DRAFT→REVIEW→ACTIVATED state machine), and display the associated impact report once simulation has run.

```typescript
// console/src/components/PolicyAuthoringForm.tsx
import React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { kernelClient } from "../lib/api-client";
import { PolicyEnvelopeSchema, type PolicyEnvelope } from "../schemas/action";

interface PolicyAuthoringFormProps {
  initialValues?: Partial<PolicyEnvelope>;
  onSaved: (policy: PolicyEnvelope) => void;
}

export function PolicyAuthoringForm({ initialValues, onSaved }: PolicyAuthoringFormProps) {
  const {
    register,
    handleSubmit,
    watch,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<PolicyEnvelope>({
    resolver: zodResolver(PolicyEnvelopeSchema),
    defaultValues: {
      lifecycle: "DRAFT",          // New policies always start as DRAFT
      decision: "require_approval",
      ...initialValues,
    },
  });

  // CEL compile-check on blur — the kernel dry-runs the condition
  const celCondition = watch("condition");

  const celCheckMutation = useMutation({
    mutationFn: async (condition: string) => {
      const { data, error } = await kernelClient.POST("/kernel/v1/policy/cel-check", {
        body: { condition },
      });
      if (error) throw error;
      return data;
    },
    onError: (err) => {
      setError("condition", {
        message: `CEL compile error: ${(err as Error).message}`,
      });
    },
  });

  const saveMutation = useMutation({
    mutationFn: async (values: PolicyEnvelope) => {
      const { data, error } = await kernelClient.POST("/kernel/v1/policies", {
        body: values,
      });
      if (error) throw error;
      return data;
    },
    onSuccess: (data) => onSaved(data as PolicyEnvelope),
  });

  return (
    <form onSubmit={handleSubmit((v) => saveMutation.mutate(v))}>
      <fieldset>
        <legend>Policy Identity</legend>
        <label>
          Policy ID (e.g. ciro.ifrs9.stage_transition)
          <input {...register("id")} placeholder="org.domain.action_name" />
          {errors.id && <span role="alert">{errors.id.message}</span>}
        </label>
        <label>
          Governs (action type)
          <input {...register("governs")} />
        </label>
      </fieldset>

      <fieldset>
        <legend>CEL Condition</legend>
        <label>
          Condition (CEL — deterministic, sandboxed, no I/O or clock access)
          <textarea
            {...register("condition")}
            onBlur={() => celCondition && celCheckMutation.mutate(celCondition)}
            rows={4}
          />
          {errors.condition && <span role="alert">{errors.condition.message}</span>}
          {celCheckMutation.isPending && <span>Checking CEL syntax...</span>}
          {celCheckMutation.isSuccess && <span>CEL syntax valid.</span>}
        </label>
      </fieldset>

      <fieldset>
        <legend>Decision</legend>
        <label>
          Decision
          <select {...register("decision")}>
            <option value="allow">Allow</option>
            <option value="deny">Deny</option>
            <option value="require_approval">Require Approval</option>
          </select>
        </label>
      </fieldset>

      {/* Lifecycle is read-only in the authoring form — it transitions via
          the simulation + review pipeline, never directly by the user.
          Allowing users to set lifecycle="ACTIVATED" bypasses the activation gate (ADR F-10). */}
      <input type="hidden" {...register("lifecycle")} value="DRAFT" />

      <button type="submit" disabled={isSubmitting || saveMutation.isPending}>
        Save as Draft
      </button>
    </form>
  );
}
```

### Ledger Verify UI

The ledger verify UI calls `GET /kernel/v1/ledger/verify` and renders the RFC 6962 inclusion proof result. This is what a compliance officer or regulator uses to confirm a ledger entry is authentic. Display the proof in a structured, non-technical format alongside the raw proof data for technical reviewers.

```typescript
// console/src/components/LedgerVerifyUI.tsx
import React from "react";
import { useQuery } from "@tanstack/react-query";
import { kernelClient } from "../lib/api-client";

interface LedgerVerifyProps {
  ledgerSeq: number;
}

export function LedgerVerifyUI({ ledgerSeq }: LedgerVerifyProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["ledger-verify", ledgerSeq],
    queryFn: async () => {
      const { data, error } = await kernelClient.GET("/kernel/v1/ledger/verify", {
        params: { query: { seq: ledgerSeq } },
      });
      if (error) throw error;
      return data;
    },
    staleTime: Infinity,  // Proofs don't change — don't refetch
  });

  if (isLoading) return <p>Verifying ledger entry...</p>;
  if (isError)   return <p role="alert">Verification failed — contact system administrator.</p>;

  return (
    <article aria-label={`Ledger verification for entry ${ledgerSeq}`}>
      <header>
        <h2>Ledger Entry {ledgerSeq}</h2>
        <span data-verified={data.verified}>
          {data.verified ? "Integrity verified" : "VERIFICATION FAILED"}
        </span>
      </header>

      <section>
        <h3>Action Summary</h3>
        <dl>
          <dt>Action ID</dt><dd><code>{data.action_id}</code></dd>
          <dt>Action Type</dt><dd><code>{data.action_type}</code></dd>
          <dt>Actor</dt><dd>{data.actor_ref}</dd>
          <dt>Sealed At</dt><dd>{new Date(data.sealed_at).toISOString()}</dd>
          <dt>Policy</dt><dd>{data.policy_id} version {data.policy_version}</dd>
        </dl>
      </section>

      <section>
        <h3>RFC 6962 Inclusion Proof</h3>
        <dl>
          <dt>Tree Size</dt><dd>{data.proof.tree_size}</dd>
          <dt>Leaf Index</dt><dd>{data.proof.leaf_index}</dd>
          <dt>Root Hash</dt><dd><code>{data.proof.root_hash}</code></dd>
        </dl>
        <details>
          <summary>Raw proof (for technical review)</summary>
          <pre>{JSON.stringify(data.proof, null, 2)}</pre>
        </details>
      </section>
    </article>
  );
}
```

### Impact Report Viewer

Impact reports are generated during policy simulation (spec §3.9). The viewer renders the decision distribution comparison (active policy vs candidate), highlights flipped decisions, and surfaces the fairness delta from K·09. This is what a reviewer signs off before a policy can advance to ACTIVATED.

```typescript
// console/src/components/ImpactReportViewer.tsx
import React from "react";
import { useQuery } from "@tanstack/react-query";
import { kernelClient } from "../lib/api-client";

interface ImpactReportViewerProps {
  policyId: string;
  policyVersion: number;
  simulationId: string;
}

export function ImpactReportViewer({
  policyId,
  policyVersion,
  simulationId,
}: ImpactReportViewerProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["impact-report", policyId, policyVersion, simulationId],
    queryFn: async () => {
      const { data, error } = await kernelClient.GET(
        "/kernel/v1/policy/{policy_id}/versions/{version}/impact-report",
        {
          params: {
            path: { policy_id: policyId, version: policyVersion },
            query: { simulation_id: simulationId },
          },
        }
      );
      if (error) throw error;
      return data;
    },
  });

  if (isLoading) return <p>Loading impact report...</p>;
  if (!data)     return <p>No impact report available.</p>;

  const totalActions = data.total_actions_evaluated;
  const flippedCount = data.flipped_decisions.length;
  const flipRate = totalActions > 0 ? ((flippedCount / totalActions) * 100).toFixed(1) : "0";

  return (
    <article aria-label={`Impact report for ${policyId} v${policyVersion}`}>
      <header>
        <h2>Impact Report — {policyId} v{policyVersion}</h2>
        <p>Simulation mode: <strong>{data.mode}</strong> ({data.simulation_period})</p>
      </header>

      <section aria-label="Decision distribution">
        <h3>Decision Distribution</h3>
        <table>
          <thead>
            <tr><th>Decision</th><th>Active Policy</th><th>Candidate Policy</th><th>Delta</th></tr>
          </thead>
          <tbody>
            {Object.entries(data.decision_distribution.active).map(([decision, count]) => {
              const candidateCount = data.decision_distribution.candidate[decision] ?? 0;
              const delta = candidateCount - (count as number);
              return (
                <tr key={decision}>
                  <td>{decision}</td>
                  <td>{count as number}</td>
                  <td>{candidateCount}</td>
                  <td data-positive={delta > 0}>{delta > 0 ? `+${delta}` : delta}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p>
          <strong>{flippedCount}</strong> of {totalActions} decisions would flip ({flipRate}%).
          {data.above_activation_threshold && (
            <span role="alert"> Shadow mode required before activation (above threshold).</span>
          )}
        </p>
      </section>

      {data.fairness_delta && (
        <section aria-label="Fairness delta (K·09)">
          <h3>Fairness Delta</h3>
          {data.fairness_delta.breach_detected && (
            <p role="alert">Fairness breach detected — review required before activation.</p>
          )}
          <pre>{JSON.stringify(data.fairness_delta.metrics, null, 2)}</pre>
        </section>
      )}

      <section>
        <h3>Reviewer Sign-Off</h3>
        <p>
          This report must be acknowledged before the policy can advance to ACTIVATED.
          Acknowledgement is recorded in the governance ledger.
        </p>
        {data.acknowledged_by ? (
          <p>Acknowledged by {data.acknowledged_by} at {new Date(data.acknowledged_at!).toISOString()}</p>
        ) : (
          <button
            onClick={async () => {
              await kernelClient.POST(
                "/kernel/v1/policy/{policy_id}/versions/{version}/impact-report/acknowledge",
                { params: { path: { policy_id: policyId, version: policyVersion } } }
              );
            }}
          >
            Acknowledge and proceed to review
          </button>
        )}
      </section>
    </article>
  );
}
```

### QUAICU TypeScript Checklist

When reviewing any console TypeScript, enforce these in addition to the standard checklist:

- [ ] All domain types use the exact names from the QUAICU glossary: `Action`, `Proposal`, `GovernedAction`, `Policy`, `Gate`, `LedgerEntry` — no synonyms
- [ ] `tenant_id` is NEVER in the request body or a Zod schema — it is extracted from the JWT claim server-side; the console never sets it
- [ ] `PENDING_APPROVAL` actions trigger polling — no static data display for lifecycle-critical states
- [ ] Policy lifecycle transitions (`DRAFT→REVIEW→ACTIVATED`) are server-driven; the console never sets `lifecycle: "ACTIVATED"` directly
- [ ] API client types are generated from the FastAPI OpenAPI schema — not hand-written
- [ ] Approval forms require a non-empty rationale field (min 10 chars) — rationale is part of the audit record
- [ ] All CEL conditions are validated via the kernel's compile-check endpoint before save — never just Zod string validation
- [ ] `TenantProvider` wraps all authenticated routes; no component reads `tenant_id` from URL params or local state
- [ ] Ledger proof components display `data.verified` prominently and fail closed (show "VERIFICATION FAILED" on error, not a spinner)
