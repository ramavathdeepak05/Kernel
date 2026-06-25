#!/usr/bin/env python3
"""Drive the SHIPPED policy packs against a LIVE QUAICU kernel (e.g. https://kernel.quaicu.org).

The "real environment" companion to `demo.py`: instead of an in-process kernel, this talks to a running
kernel over HTTPS with **your tenant's API key**, the way a customer integrates. It:

  1. confirms the key works                         GET  /v1/me/entitlements
  2. (optional) imports the regulatory packs        POST /v1/policy-packs/{rbi,dpdp,eu-ai-act}/import
  3. asks the kernel to govern a stream of actions   POST /v1/authorize         (decision + sealed)

> **This writes to YOUR tenant** (imported DRAFT policies; sealed authorize records). Run it against a
> demo/sandbox tenant you own. It is stdlib-only (urllib) — no dependencies.

    # 1) sign up + create an API key in the console first (see README → "Real environment")
    setx QUAICU_API_KEY qk_xxx        # PowerShell: $env:QUAICU_API_KEY="qk_xxx"
    python examples/policy-pack-demo/realenv.py --base https://kernel.quaicu.org --import-packs

Outcomes from step 3 reflect the policies that are **ACTIVE** in your tenant. Importing a pack creates
its policies as **DRAFTs** (never silently enforced) — activate the ones you want in the console
(Policies → backtest → activate) before they shape decisions. Until then, actions fall through to the
deployment's fail-closed default. See README.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

PACKS = ("rbi", "dpdp", "eu-ai-act")

# A representative governed action per pack (payloads honor each pack's documented contract).
_ACTIONS: list[tuple[str, str, dict]] = [
    ("RBI", "data.store", {"data_class": "payment", "storage_region": "SG", "encryption_at_rest": True}),
    ("RBI", "data.transfer", {"destination_country": "SG"}),
    ("DPDP", "personal_data.process", {"consent_obtained": False, "purpose": "kyc", "subject_erased": False}),
    ("EU-AI-Act", "ai_system.invoke",
     {"risk_category": "high", "use_case": "credit_scoring", "human_oversight": False, "discloses_ai": True}),
]


def _call(method: str, url: str, api_key: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {api_key}")
    # A CDN/WAF in front of the kernel (e.g. Cloudflare) may block the default urllib agent (HTTP 1010).
    req.add_header("User-Agent", "quaicu-demo-agent/1.0")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
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
    ap = argparse.ArgumentParser(description="Drive the shipped packs against a live QUAICU kernel.")
    ap.add_argument("--base", default=os.getenv("QUAICU_BASE", "https://kernel.quaicu.org"))
    ap.add_argument("--api-key", default=os.getenv("QUAICU_API_KEY"))
    ap.add_argument("--import-packs", action="store_true",
                    help="POST /v1/policy-packs/{id}/import for each pack (needs a policy-admin key).")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    if not args.api_key:
        print("No API key. Set QUAICU_API_KEY or pass --api-key (create one in the console → API Keys).")
        return 2

    print(f"Target: {base}\n")

    # 1 ─ auth check
    status, body = _call("GET", f"{base}/v1/me/entitlements", args.api_key)
    if status != 200:
        print(f"✗ API key check failed [{status}]: {body}")
        print("  → confirm the key is valid + active (console → API Keys).")
        return 1
    plan = body.get("plan") or body.get("tier") if isinstance(body, dict) else None
    print(f"✓ authenticated [{status}]" + (f" · plan={plan}" if plan else ""))

    # 2 ─ import the regulatory packs (optional; policy-admin)
    if args.import_packs:
        print("\nImporting shipped packs (registers each as DRAFT — activate in the console to enforce):")
        for pid in PACKS:
            status, body = _call("POST", f"{base}/v1/policy-packs/{pid}/import", args.api_key, body={})
            if 200 <= status < 300:
                imported = body.get("imported", body) if isinstance(body, dict) else body
                print(f"  ✓ {pid:<10} [{status}] imported: {imported}")
            elif status in (401, 403):
                print(f"  ✗ {pid:<10} [{status}] needs a policy-admin key — import via the console instead.")
            else:
                print(f"  ✗ {pid:<10} [{status}] {body}")

    # 3 ─ govern a stream of actions (decision-only; each is sealed to the audit trail)
    print("\nGoverning a representative action per pack (POST /v1/authorize — reflects ACTIVE policies):")
    for regime, action_type, payload in _ACTIONS:
        status, body = _call(
            "POST", f"{base}/v1/authorize", args.api_key,
            body={"type": action_type, "payload": payload},
        )
        if status == 200 and isinstance(body, dict):
            print(f"  {regime:<10} {action_type:<22} → decision={body.get('decision', '?').upper()}")
        else:
            print(f"  {regime:<10} {action_type:<22} → [{status}] {body}")

    print("\nNext: open the console → Policies (your imported packs as DRAFTs; activate to enforce) and")
    print("Audit (the sealed decisions above) → Download proof bundle (offline-verifiable). See README.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
