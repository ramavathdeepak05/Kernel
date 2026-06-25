#!/usr/bin/env python3
"""Author + activate a STARTER-cap-sized demo policy set on a live QUAICU tenant.

After the catch-all `starter-allow-baseline` is gone, governed actions whose type matches no active
policy **fail-closed DENY** (empty policy set). And STARTER caps active policies at 5. This script
installs a believable, demo-ready set within that budget — **one catch-all allow + four guardrails** —
so the fake AI (see `fake_ai_agent.py`) produces a realistic mix of allow / deny / require-approval:

  1. demo-allow-baseline           *                      allow                (everything sealed by default)
  2. rbi-payment-data-localization data.store             deny                 (payment data offshore)
  3. rbi-cross-border-transfer     data.transfer          require_approval     (role:compliance)
  4. dpdp-consent-required         personal_data.process  deny                 (no consent)
  5. eu-ai-act-high-risk-oversight ai_system.invoke       require_approval     (role:compliance_officer)

Deny-overrides means the four guardrails carve exceptions out of the catch-all allow. Requires a
**session JWT** with policy-admin (the same credential `fake_ai_agent.py` uses) — a `qk_` API key can't
author policies on the SaaS plane.

    $env:QUAICU_API_KEY = "eyJ...session-jwt..."
    python examples/policy-pack-demo/activate_demo_policies.py --base https://kernel.quaicu.org

Each policy: register (DRAFT) → submit (REVIEW) → activate (F-10 gate, inline acknowledged report).
Re-running is safe-ish: a policy id that already exists is reported and skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

# id, governs, condition, decision, approvers, regulatory_refs
_POLICIES: list[tuple[str, str, str, str, list[str], list[str]]] = [
    ("demo-allow-baseline", "*", "true", "allow", [], []),
    ("rbi-payment-data-localization", "data.store",
     'payload_data_class == "payment" && payload_storage_region != "IN"', "deny", [],
     ["rbi.localization.payment_data"]),
    ("rbi-cross-border-transfer", "data.transfer",
     'payload_destination_country != "IN"', "require_approval", ["role:compliance"],
     ["rbi.transfer.cross_border"]),
    ("dpdp-consent-required", "personal_data.process",
     "payload_consent_obtained == false", "deny", [], ["dpdp.consent.art.6"]),
    ("eu-ai-act-high-risk-oversight", "ai_system.invoke",
     'payload_risk_category == "high" && payload_human_oversight == false', "require_approval",
     ["role:compliance_officer"], ["oversight.art.14"]),
]


def _req(method: str, url: str, key: str, body: dict | None) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", f"Bearer {key}")
    r.add_header("User-Agent", "quaicu-demo-agent/1.0")
    if data is not None:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=25) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw
    except urllib.error.URLError as exc:
        return 0, str(exc)


def main() -> int:
    ap = argparse.ArgumentParser(description="Install a demo policy set on a live QUAICU tenant.")
    ap.add_argument("--base", default=os.getenv("QUAICU_BASE", "https://kernel.quaicu.org"))
    ap.add_argument("--api-key", default=os.getenv("QUAICU_API_KEY"))
    args = ap.parse_args()
    base = args.base.rstrip("/")
    key = args.api_key
    if not key:
        print("No session JWT. Set QUAICU_API_KEY to a policy-admin session JWT (see LIVE_DEMO_RUNBOOK.md).")
        return 2

    report = {
        "reviewed_by": "user:demo-setup",
        "reviewed_at": datetime.now(tz=timezone.utc).isoformat(),
        "decision_distribution": {},
        "flip_count": 0,
        "fairness_delta": 0.0,
        "acknowledged": True,
    }

    ok = 0
    for pid, governs, condition, decision, approvers, refs in _POLICIES:
        print(f"\n• {pid}  ({governs} → {decision})")
        s, b = _req("POST", f"{base}/v1/policies", key, {
            "id": pid, "version": 1, "governs": governs, "scope": {"tenant": "*"},
            "condition": condition, "decision": decision, "approvers": approvers,
            "regulatory_refs": refs,
        })
        if s == 409 or (isinstance(b, dict) and "exists" in json.dumps(b).lower()):
            print(f"    register: already exists [{s}] — skipping")
            continue
        if not (200 <= s < 300):
            print(f"    ✗ register [{s}]: {b}")
            continue
        s, b = _req("POST", f"{base}/v1/policies/{pid}/versions/1/submit", key, None)
        if not (200 <= s < 300):
            print(f"    ✗ submit [{s}]: {b}")
            continue
        s, b = _req("POST", f"{base}/v1/policies/{pid}/versions/1/activate", key,
                    {"impact_report": report})
        if 200 <= s < 300:
            lc = b.get("lifecycle") if isinstance(b, dict) else "?"
            print(f"    ✓ activated [{s}] lifecycle={lc}")
            ok += 1
        else:
            print(f"    ✗ activate [{s}]: {b}")

    # show the resulting active set
    s, b = _req("GET", f"{base}/v1/policies?lifecycle=ACTIVATED", key, None)
    if isinstance(b, dict):
        active = [p["id"] for p in b.get("policies", [])]
        print(f"\nActive policies now ({len(active)}): {active}")
    print(f"\n{ok}/{len(_POLICIES)} activated. Next: run fake_ai_agent.py, then check Audit + Approvals.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
