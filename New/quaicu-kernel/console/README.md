# QUAICU Operator Console

A plain React + Vite + TypeScript UI for running a deployed kernel: **policy management**,
**governance dashboard**, **audit trail**, and **HITL approvals**. It is a thin client over the
kernel REST API (`/v1/*`) — it stores no state of its own beyond your session token.

## Prerequisites
- Node 18+ and npm.
- A running kernel API (FastAPI/uvicorn) with the CEL policy engine, an IdentityPort (e.g. the JWT
  adapter), and the in-process HITL port. By default the dev server proxies to `http://localhost:8000`.

## Run (development)
```bash
npm install
npm run dev          # serves http://localhost:5173, proxies /v1 → :8000
```
Open http://localhost:5173 and sign in one of three ways:
- **Create a free workspace** (`/signup`) — provisions a STARTER tenant + API key (needs the kernel's
  signup endpoint enabled).
- **Sign in with your IdP** — the OIDC button (when `VITE_OIDC_*` is configured).
- **Developer sign-in** (collapsed in the top-right menu) — paste a **Tenant id** + **Bearer token**
  (a JWT or `qk_…` API key your IdentityPort accepts) for local work. The console never mints tokens;
  it only sends `Authorization: Bearer <token>` + `X-Tenant-Id`.

Point the dev proxy at a different kernel with `KERNEL_API_URL=http://host:port npm run dev`.

## Build
```bash
npm run build        # tsc typecheck + vite production build → dist/
npm run preview      # serve the built app
```
For production, build with `VITE_API_BASE=https://kernel.your-domain.com` so the deployed console
knows where the kernel is, then serve `dist/` behind your web server (ensure the kernel's CORS
`allow_origins` includes the console origin — see `delivery/api/app.create_app(cors_origins=...)`).

## What each page does
| Page | Backing endpoints |
|------|-------------------|
| Signup (`/signup`) | `POST /v1/signup` — self-serve free STARTER workspace; reveals the one-time API key and signs you in |
| Dashboard | `GET /v1/dashboard/{tenant}/{overview,decisions,actions/top,hitl/queue}` |
| Policies | `/v1/policies/*` — register, submit, **simulate** (backtest), activate, deprecate |
| Audit trail | `GET /v1/ledger/{tenant}/trail` |
| Approvals | `GET /v1/approvals`, `POST /v1/approvals/{id}/{approve,reject}` |

## Auth & tenant routing
The console sends `Authorization: Bearer <token>` plus `X-Tenant-Id: <tenant>` on every API call.
The bearer is either an OIDC `id_token` (tenant read from its claim) or a self-serve **API key**
(`qk_…`, from `/signup`). Because an API key is not a JWT, the shared-plane router needs the
`X-Tenant-Id` header to route the request — the console always sends it.

## Notes
- **Auth** has three paths: self-serve **signup** (`/signup` → API key), **OIDC** Authorization
  Code + PKCE login (when `VITE_OIDC_*` is configured), and **Developer sign-in** (collapsed in the
  top-right menu) for pasting a token in local dev. The kernel consumes whichever bearer it's given
  via its IdentityPort / API-key middleware.
- **Approvals**: the queue is the operator surface over the in-process HITL store. Wiring an
  approval to *resume* a suspended action depends on the async K·06 process-engine deployment; the
  synchronous in-process lifecycle times a gate out immediately. See the route docstring.
