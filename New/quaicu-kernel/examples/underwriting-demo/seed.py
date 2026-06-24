#!/usr/bin/env python3
"""Seed a RUNNING demo kernel so the operator console shows a populated audit trail + approvals queue.

This is the companion to the docker-compose / console walkthrough (see README). It POSTs a handful of
`credit.approve` drafts to a running kernel's REST API:

  • low-risk drafts (<= INR 10,00,000)  → policy ALLOWS → executed → sealed (visible on the Audit page)
  • a high-risk draft (> INR 10,00,000)  → policy REQUIRES APPROVAL → appears on the Approvals page

Unlike `demo.py` (a self-contained, in-process script — the fully-verified end-to-end story including
approve → re-execute → seal), this seeder talks to a separate server process so the browser console can
render real data. Run it AFTER the stack is up:

    # 1) start the kernel pointed at the demo config (see README), then:
    python examples/underwriting-demo/seed.py                 # defaults to http://localhost:7000
    python examples/underwriting-demo/seed.py --base http://localhost:7000

Stdlib only (urllib) — no extra dependencies. If the kernel has API-key auth enabled, pass --api-key
(or set QUAICU_API_KEY); for the default dev/demo config (auth disabled) no key is needed.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request

_DRAFTS = [
    {"applicant": "A. Sharma", "amount": 250_000, "note": "low-risk → auto-approved + sealed"},
    {"applicant": "R. Iyer", "amount": 480_000, "note": "low-risk → auto-approved + sealed"},
    {"applicant": "K. Rao", "amount": 7_500_000, "note": "high-risk → routed to Approvals queue"},
]


def _propose(base: str, api_key: str | None, draft: dict) -> tuple[int, str]:
    body = json.dumps(
        {
            "type": "credit.approve",
            "payload": {"applicant": draft["applicant"], "amount": draft["amount"]},
            "idempotency_key": f"seed-{draft['applicant'].replace(' ', '-').replace('.', '')}",
            "actor_id": "agent:underwriter",
            "actor_roles": ["role:underwriter"],
        }
    ).encode()
    req = urllib.request.Request(
        f"{base.rstrip('/')}/v1/actions/propose",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()
    except urllib.error.URLError as exc:
        return 0, str(exc)


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed a running demo kernel for the console walkthrough.")
    ap.add_argument("--base", default=os.getenv("QUAICU_BASE", "http://localhost:7000"))
    ap.add_argument("--api-key", default=os.getenv("QUAICU_API_KEY"))
    args = ap.parse_args()

    print(f"Seeding {args.base} with {len(_DRAFTS)} credit drafts…\n")
    failures = 0
    for d in _DRAFTS:
        status, text = _propose(args.base, args.api_key, d)
        ok = 200 <= status < 300
        marker = "✓" if ok else "✗"
        print(f"  {marker} INR {d['amount']:>10,}  {d['applicant']:<12} [{status}]  {d['note']}")
        if not ok:
            failures += 1
            print(f"      ↳ {text[:200]}")
    if failures:
        print(
            f"\n{failures} request(s) failed. Is the kernel running at {args.base} with the demo "
            "config? See README. (A non-2xx on the high-risk draft can be the synchronous "
            "require-approval gate — it still appears on the Approvals page.)"
        )
        return 1
    print("\nDone. Open the console → Audit (sealed drafts) and Approvals (pending high-risk draft).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
