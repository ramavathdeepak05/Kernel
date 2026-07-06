# CLAUDE.md — Shared Memory (Claude Code ⇄ Gemini CLI)

This file is the shared working memory for two AI assistants collaborating on this
repo: **Claude Code** and **Gemini CLI**. Both tools auto-load this file at the
start of every session, so anything written here is visible to both.

## How to use this file

- **Read** this whole file before starting work — it is the source of shared truth.
- **Append** durable facts, decisions, and handoffs under the sections below.
- **Attribute + date** every entry: `- [YYYY-MM-DD] (claude|gemini) <fact>`.
- Keep entries short and factual. Link to files with paths, not pasted blobs.
- Don't delete another agent's entry; if it's wrong, add a correcting entry below it.

---

## Project facts
<!-- Stable truths about the repo, stack, and conventions. -->
- [2026-06-16] (claude) Repo: QUAICU Kernel (hexagonal ports/adapters, fail-closed governance kernel). Primary dir: C:\alis-antigravity\Kernel.

## Decisions
<!-- Choices made and the reason, so the other agent doesn't re-litigate them. -->
- [2026-06-16] (claude) This CLAUDE.md is the shared context channel between Claude Code and Gemini CLI (Gemini loads it via context.fileName).
- [2026-06-16] (gemini) Fixed Postgres adapters to properly set `app.current_tenant` in transactions to satisfy RLS (migration 004). Bypassed RLS (`SET LOCAL row_security = off`) purely for internal hydration (like `TrustLedger.hydrate`) and test cleanup.

## Gemini model selection (Claude picks per delegated task via `gemini -m <id> -p`)
- `gemini-3.1-pro-preview` — hard reasoning, code review, architecture (quality > speed).
- `gemini-3.5-flash` — default workhorse: fast, cheap, most delegation.
- `gemini-3-flash-preview` — alt flash; use if 3.5-flash is rate-limited.
- `gemini-3.1-flash-lite` — high-volume / trivial bulk tasks.
- `gemini-2.5-pro` — stable fallback pro.
- All Gemini-3.x IDs above confirmed routing via `-m` on 2026-06-16.

## Handoffs / open threads
<!-- Work in progress one agent is passing to the other. -->
- [2026-07-06] (claude) D4-1 shared plane LIVE in prod. `quaicu-kernel` Cloud Run rev **00037-k9m** serving; `quaicu_prod` migrated 013→**017** (staged: additive 014–016 while old rev served, FORCE-RLS 017 only after the GUC-setting D4-1 adapter build was serving — 017 blanks any read that doesn't `set_config('app.current_tenant',…)`); startup `/readyz` + liveness `/health` probes attached; zero downtime (continuity-probed). RLS verified enforcing in prod (unset GUC → 0 rows). Enabled `cloudresourcemanager.googleapis.com` (needed by `run services replace`, not `run deploy`). **OPEN residuals:** (1) deploy was imperative `gcloud`, not `terraform apply` → gcp-saas Terraform state drifts; reconcile before trusting IaC. (2) `k02-review-v2` re-tag (optimistic-seal-linearization frozen-surface delta) still to place on the merged commit. (3) integration conformance suite not re-run this session. Harness+lock fixes on branch `fix/d4-1-load-harness` (PR pending merge to main).
- [2026-07-04] (claude) Phase D3 (proof layer) DONE + merged to main (23ba6059), tag `k02-review-v1`. FREEZE: core/ledger/, core/ports/anchor.py, core/regmap/export.py, adapters/ledger/, delivery/witness_app.py need owner sign-off until the T-1 crypto review lands (spec: New/quaicu-kernel/docs/operations/K02_REVIEW_PACKAGE.md).
- [2026-06-16] (claude) Fixed the 4 code-review findings in New/quaicu-kernel: (1) Critical rate-limit DoS — reordered middleware so ApiKeyAuth runs before RateLimit; counter now keys on verified principal.tenant_id else client IP, never the spoofable X-Tenant-Id (delivery/api/ratelimit.py, app.py). (2) OpenBao verify() raises LedgerSealError on infra errors vs returning the real valid bool (adapters/ledger/openbao.py). (3) Event-bus emit() logs subscriber failures (adapters/events/memory.py). (4) API-key hashing → HMAC-SHA256 + QUAICU_API_KEY_PEPPER (core/account/engine.py). Suite: 885 passed / 10 skipped; ruff clean. Gemini 3.1-pro re-review confirmed all 4.
- [2026-06-16] (claude) OPEN follow-up (deployment hardening, not a code bug): the rate limiter's unauthenticated IP fallback uses request.client.host; behind an LB it collapses to the proxy IP. Needs a trusted forwarded-for handler at the ASGI edge (do NOT trust raw X-Forwarded-For). Authenticated traffic is unaffected.

## Scratch
<!-- Ephemeral notes; safe to prune. -->
