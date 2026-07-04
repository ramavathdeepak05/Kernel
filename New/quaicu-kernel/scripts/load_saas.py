"""Multi-worker load test for the shared SaaS plane (D4-1 DoD: "load test passes multi-worker").

Drives the PRODUCTION entrypoint (`delivery.entrypoint_saas:app` via `build_saas_app`) at
``--workers N`` and verifies, **from the database** (not any single worker's memory), that the
multi-worker correctness invariants held under concurrency:

  1. zero lost seals — per tenant, the number of sealed `/v1/authorize` responses equals the
     durable `quaicu_ledger_entries` count, with DENSE ledger_seq 0..n-1 (the D4-1 optimistic
     seal-linearization regression gate: pre-fix, concurrent workers silently dropped entries);
  2. no fork — the stored STH's tree_size equals the entry count and its root_hash equals the
     RFC 6962 root recomputed from the stored leaf hashes;
  3. zero cross-tenant rows;
  4. zero 5xx, and zero 401 on valid keys (the cross-worker API-key fallback under fire — the
     keys are minted through one worker and immediately used on all);
  5. p99 latency of /v1/authorize under the target (software signer; KMS adds its own latency).

Usage (Windows PowerShell; needs the TEST database — never quaicu_prod — reachable, migrations at
head incl. 017; start the Cloud SQL Auth Proxy on :5433 first):

    $env:LOADTEST_DSN   = "postgresql://quaicu:<pw>@127.0.0.1:5433/quaicu?sslmode=disable"
    $env:KERNEL_JWT_SECRET = "loadtest-secret"
    $env:QUAICU_API_KEY_PEPPER = "loadtest-pepper"
    $env:KERNEL_CONFIG_SAAS = "scripts/kernel.loadtest.saas.toml"
    $env:QUAICU_ENTITLEMENTS_REFRESH = "5"   # fast tier-flip propagation across workers
    # Terminal 1 — the system under test, 4 workers:
    python -m uvicorn delivery.entrypoint_saas:app --port 7100 --workers 4
    # Terminal 2 — the load (same env vars):
    python scripts/load_saas.py --base-url http://127.0.0.1:7100 --clients 50 --seconds 60

Exit code 0 = every invariant held (numbers printed); 1 = a violation (details printed).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field

import httpx

P99_TARGET_MS = 750.0


@dataclass
class TenantStats:
    tenant_id: str = ""
    api_key: str = ""
    sealed_ok: int = 0
    denied: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    unauthorized: int = 0
    server_errors: int = 0
    other_errors: int = 0


async def _provision(client: httpx.AsyncClient, tag: str) -> TenantStats:
    """One-step signup → provisioned tenant + API key (the production self-serve path)."""
    r = await client.post(
        "/v1/signup",
        json={"email": f"load-{tag}-{uuid.uuid4().hex[:8]}@loadtest.quaicu.dev", "name": f"load-{tag}"},
    )
    r.raise_for_status()
    body = r.json()
    stats = TenantStats(tenant_id=body["tenant_id"], api_key=body["api_key"])
    print(f"provisioned tenant {stats.tenant_id}")
    return stats


async def _unthrottle(dsn: str, tenant_id: str) -> None:
    """Lift the fresh tenant's tier rate/day quotas so the load hits the seal path, not the limiter.

    Written straight to the durable plan store (quota_overrides = unbounded); every worker picks it
    up via the D4-1 periodic entitlement re-hydrate (QUAICU_ENTITLEMENTS_REFRESH) — so this step
    also exercises cross-worker tier-flip propagation.
    """
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant_id)
            await conn.execute(
                "UPDATE quaicu_customer_plans SET quota_overrides = "
                "'{\"rate_limit_per_min\": -1, \"max_actions_per_day\": -1}'::jsonb, "
                "updated_at = now() WHERE tenant_id = $1",
                tenant_id,
            )
    finally:
        await conn.close()


async def _fire(client: httpx.AsyncClient, stats: TenantStats, deadline: float) -> None:
    """One virtual client: sealed /v1/authorize decisions until the deadline."""
    headers = {
        "Authorization": f"Bearer {stats.api_key}",
        "X-Tenant-Id": stats.tenant_id,
    }
    n = 0
    while time.monotonic() < deadline:
        n += 1
        payload = {
            "type": "load.decision",
            "payload": {"amount": n},
            "idempotency_key": f"{stats.tenant_id}-{uuid.uuid4().hex}",
            "record": True,  # seal every decision → exercises the multi-worker ledger path
        }
        t0 = time.perf_counter()
        try:
            r = await client.post("/v1/authorize", json=payload, headers=headers)
        except httpx.HTTPError:
            stats.other_errors += 1
            continue
        stats.latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        if r.status_code == 200:
            body = r.json()
            if body.get("sealed"):
                stats.sealed_ok += 1
            elif body.get("allowed") is False:
                stats.denied += 1
            else:
                stats.other_errors += 1  # 200 but unsealed sealed-mode response
        elif r.status_code == 401:
            stats.unauthorized += 1
        elif r.status_code >= 500:
            stats.server_errors += 1
        else:
            stats.other_errors += 1


async def _verify_ledger(dsn: str, stats: TenantStats) -> list[str]:
    """DB-side invariants for one tenant: dense seqs, count == seals, STH == recomputed root."""
    import asyncpg

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.ledger.merkle import compute_root  # after sys.path fix

    errors: list[str] = []
    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)", stats.tenant_id
            )
            rows = await conn.fetch(
                "SELECT ledger_seq, leaf_hash, tenant_id FROM quaicu_ledger_entries "
                "WHERE tenant_id = $1 ORDER BY ledger_seq",
                stats.tenant_id,
            )
            sth = await conn.fetchrow(
                "SELECT tree_size, root_hash FROM quaicu_ledger_sth WHERE tenant_id = $1",
                stats.tenant_id,
            )
    finally:
        await conn.close()

    seqs = [r["ledger_seq"] for r in rows]
    if len(rows) != stats.sealed_ok:
        errors.append(
            f"{stats.tenant_id}: LOST SEALS — {stats.sealed_ok} sealed responses but "
            f"{len(rows)} durable entries"
        )
    if seqs != list(range(len(seqs))):
        errors.append(f"{stats.tenant_id}: ledger_seq not dense 0..n-1")
    if sth is None:
        errors.append(f"{stats.tenant_id}: no stored STH")
    else:
        if sth["tree_size"] != len(rows):
            errors.append(
                f"{stats.tenant_id}: STH tree_size {sth['tree_size']} != entry count {len(rows)}"
            )
        recomputed = compute_root([bytes(r["leaf_hash"]) for r in rows])
        if bytes(sth["root_hash"]) != recomputed:
            errors.append(f"{stats.tenant_id}: STH root does not match recomputed Merkle root (FORK)")
    return errors


async def _verify_no_cross_tenant(dsn: str, tenants: list[str]) -> list[str]:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            # '*' read-only sentinel: see every load-test row across tenants.
            await conn.execute("SELECT set_config('app.current_tenant', '*', true)")
            foreign = await conn.fetchval(
                "SELECT count(*) FROM quaicu_ledger_entries "
                "WHERE action_type = 'load.decision' AND tenant_id <> ALL($1::text[])",
                tenants,
            )
    finally:
        await conn.close()
    return (
        [f"{foreign} load-test ledger rows landed outside the load tenants (cross-tenant leak)"]
        if foreign
        else []
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:7100")
    parser.add_argument("--clients", type=int, default=50, help="concurrent clients per tenant")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--tenants", type=int, default=2)
    args = parser.parse_args()

    dsn = os.environ.get("LOADTEST_DSN", "")
    if not dsn:
        print("LOADTEST_DSN is required (the TEST database the server also points at)")
        return 1
    if "quaicu_prod" in dsn:
        print("refusing to run against quaicu_prod")
        return 1

    limits = httpx.Limits(max_connections=args.clients * args.tenants + 10)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=30.0, limits=limits) as client:
        # Readiness gate — the same signal Cloud Run's startup probe uses.
        r = await client.get("/readyz")
        if r.status_code != 200:
            print(f"/readyz not ready: {r.status_code} {r.text}")
            return 1

        all_stats = [await _provision(client, f"t{i}") for i in range(args.tenants)]

        # Lift the STARTER 60/min rate limit (quota override in the durable plan store) and wait
        # for every worker's periodic entitlement re-hydrate to pick it up.
        for stats in all_stats:
            await _unthrottle(dsn, stats.tenant_id)
        refresh = float(os.environ.get("QUAICU_ENTITLEMENTS_REFRESH", "60"))
        wait = refresh + 2.0
        print(f"quota overrides written; waiting {wait:.0f}s for worker entitlement refresh …")
        await asyncio.sleep(wait)

        # Fire immediately after provisioning: with --workers N the keys were minted by ONE worker,
        # so the very first requests on other workers exercise the D4-1 cross-worker key fallback.
        deadline = time.monotonic() + args.seconds
        tasks = [
            asyncio.create_task(_fire(client, stats, deadline))
            for stats in all_stats
            for _ in range(args.clients)
        ]
        t0 = time.monotonic()
        await asyncio.gather(*tasks)
        elapsed = time.monotonic() - t0

    # ── Report + verdict ──────────────────────────────────────────────────────
    errors: list[str] = []
    total_sealed = 0
    all_latencies: list[float] = []
    for stats in all_stats:
        total_sealed += stats.sealed_ok
        all_latencies.extend(stats.latencies_ms)
        if stats.unauthorized:
            errors.append(f"{stats.tenant_id}: {stats.unauthorized} × 401 on a VALID key")
        if stats.server_errors:
            errors.append(f"{stats.tenant_id}: {stats.server_errors} × 5xx")
        errors.extend(await _verify_ledger(dsn, stats))
    errors.extend(await _verify_no_cross_tenant(dsn, [s.tenant_id for s in all_stats]))

    p50 = statistics.median(all_latencies) if all_latencies else float("nan")
    p99 = (
        statistics.quantiles(all_latencies, n=100)[98]
        if len(all_latencies) >= 100
        else max(all_latencies, default=float("nan"))
    )
    rps = total_sealed / elapsed if elapsed else 0.0
    print(
        f"\n─ load result ─\n"
        f"tenants={len(all_stats)} clients/tenant={args.clients} duration={elapsed:.1f}s\n"
        f"sealed={total_sealed} ({rps:.1f} seals/s)  "
        f"denied={sum(s.denied for s in all_stats)}  "
        f"401={sum(s.unauthorized for s in all_stats)}  "
        f"5xx={sum(s.server_errors for s in all_stats)}  "
        f"other={sum(s.other_errors for s in all_stats)}\n"
        f"latency p50={p50:.0f}ms p99={p99:.0f}ms (target p99 < {P99_TARGET_MS:.0f}ms)"
    )
    if all_latencies and p99 >= P99_TARGET_MS:
        errors.append(f"p99 {p99:.0f}ms exceeds the {P99_TARGET_MS:.0f}ms target")
    if total_sealed == 0:
        errors.append("no successful sealed decisions — the load never exercised the seal path")

    if errors:
        print("\nFAIL:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\nPASS: zero lost seals, dense seqs, STH == recomputed root, no cross-tenant rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
