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
Open http://localhost:5173. Click **Set token** (top-right) and enter:
- **Tenant id** — must match the kernel instance's tenant (e.g. `ciro-bank`).
- **Bearer token** — a token your kernel's IdentityPort accepts. The console does **not** mint
  tokens; it only sends `Authorization: Bearer <token>`.
- **API base** — leave blank to use the dev proxy; set to e.g. `https://kernel.internal` in prod.

Point the proxy at a different kernel with `KERNEL_API_URL=http://host:port npm run dev`.

## Build
```bash
npm run build        # tsc typecheck + vite production build → dist/
npm run preview      # serve the built app
```
For production, serve `dist/` behind your web server and set the **API base** to the kernel's URL
(ensure the kernel's CORS `allow_origins` includes the console origin — see
`delivery/api/app.create_app(cors_origins=...)`).

## What each page does
| Page | Backing endpoints |
|------|-------------------|
| Dashboard | `GET /v1/dashboard/{tenant}/{overview,decisions,actions/top,hitl/queue}` |
| Policies | `/v1/policies/*` — register, submit, **simulate** (backtest), activate, deprecate |
| Audit trail | `GET /v1/ledger/{tenant}/trail` |
| Approvals | `GET /v1/approvals`, `POST /v1/approvals/{id}/{approve,reject}` |

## Notes
- **Auth** is token-paste for now (the kernel consumes tokens via its IdentityPort). A login/OIDC
  flow is a later iteration.
- **Approvals**: the queue is the operator surface over the in-process HITL store. Wiring an
  approval to *resume* a suspended action depends on the async K·06 process-engine deployment; the
  synchronous in-process lifecycle times a gate out immediately. See the route docstring.
