#!/usr/bin/env python3
"""Fake AI system → governed credit-underwriting + KYC/AML calls against a LIVE QUAICU kernel.

Drives a realistic, ongoing stream of governed actions so the **console** (Audit / Approvals / Policies)
fills with believable data — as if an internal credit + KYC/AML AI were running in production. Each call
goes to `POST /v1/actions/propose` (the full lifecycle), so:

  • compliant actions        → sealed → appear on the **Audit** page (+ downloadable proof bundle)
  • high-risk / cross-border → routed to a human → appear on the **Approvals** page
  • prohibited / no-consent  → fail-closed **DENY**

The "AI" is two simulated agents whose actions map onto the SHIPPED packs (RBI · DPDP · EU AI Act):

  KYC/AML onboarding agent          Credit-underwriting agent
  ───────────────────────           ─────────────────────────
  personal_data.process (DPDP)      personal_data.process (DPDP, bureau pull)
  data.store          (RBI, docs)   data.store          (RBI, financials)
  data.transfer       (RBI, AML)    ai_system.invoke    (EU, credit scoring)
  access.grant        (RBI, case)

Requires the packs to be **active** in your tenant (import + activate in the console — see README), and
an API key with action-write scope. Stdlib only.

    # PowerShell:  $env:QUAICU_API_KEY="qk_xxx"
    python examples/policy-pack-demo/fake_ai_agent.py --base https://kernel.quaicu.org --applicants 6
    python examples/policy-pack-demo/fake_ai_agent.py --dry-run        # print the call plan, send nothing
    python examples/policy-pack-demo/fake_ai_agent.py --loop --interval 20   # keep the console alive
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

# Applicant archetypes → a believable mix of outcomes across the shipped packs.
# Each step: (agent, action_type, payload, human-readable label).
def _kyc_steps(case: str, *, clean: bool, cross_border: bool) -> list[tuple[str, str, dict, str]]:
    return [
        ("KYC/AML", "personal_data.process",
         {"consent_obtained": clean, "purpose": "kyc", "subject_erased": False},
         f"{case}: identity/KYC screen" + ("" if clean else " (NO consent)")),
        ("KYC/AML", "data.store",
         {"data_class": "kyc", "storage_region": "IN", "encryption_at_rest": True},
         f"{case}: store KYC documents (India, encrypted)"),
        ("KYC/AML", "data.transfer",
         {"destination_country": "US" if cross_border else "IN"},
         f"{case}: AML sanctions screening" + (" (cross-border → review)" if cross_border else "")),
        ("KYC/AML", "access.grant",
         {"access_logged": True},
         f"{case}: grant analyst case access (logged)"),
    ]


def _credit_steps(loan: str, *, oversight: bool, offshore_payment: bool) -> list[tuple[str, str, dict, str]]:
    return [
        ("CREDIT", "personal_data.process",
         {"consent_obtained": True, "purpose": "legal", "subject_erased": False},
         f"{loan}: pull credit-bureau report"),
        ("CREDIT", "data.store",
         {"data_class": "payment" if offshore_payment else "personal",
          "storage_region": "SG" if offshore_payment else "IN", "encryption_at_rest": True},
         f"{loan}: store financials" + (" (payment data OFFSHORE → deny)" if offshore_payment else "")),
        ("CREDIT", "ai_system.invoke",
         {"risk_category": "high", "use_case": "credit_scoring",
          "human_oversight": oversight, "discloses_ai": True},
         f"{loan}: AI credit-scoring decision" + ("" if oversight else " (no oversight → review)")),
    ]


def _plan(n: int) -> list[tuple[str, str, dict, str]]:
    steps: list[tuple[str, str, dict, str]] = []
    for i in range(1, n + 1):
        case = f"KYC-{1000 + i}"
        loan = f"LOAN-{2000 + i}"
        # rotate archetypes for variety
        clean = i % 4 != 0           # every 4th applicant fails consent
        cross_border = i % 3 == 0    # every 3rd triggers cross-border AML review
        oversight = i % 2 == 0       # alternate credit decisions need approval
        offshore = i % 5 == 0        # every 5th stores payment data offshore (deny)
        steps += _kyc_steps(case, clean=clean, cross_border=cross_border)
        steps += _credit_steps(loan, oversight=oversight, offshore_payment=offshore)
    return steps


def _propose(base: str, api_key: str, action_type: str, payload: dict, ikey: str) -> tuple[int, dict | str]:
    body = json.dumps({"type": action_type, "payload": payload, "idempotency_key": ikey}).encode()
    req = urllib.request.Request(f"{base}/v1/actions/propose", data=body, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    # A normal UA — a CDN/WAF (e.g. Cloudflare) in front of the kernel may block the default
    # "Python-urllib/x" agent (HTTP 1010). Identify as a generic client.
    req.add_header("User-Agent", "quaicu-demo-agent/1.0")
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


def _run_once(base: str, api_key: str, applicants: int, dry_run: bool) -> int:
    plan = _plan(applicants)
    print(f"{'DRY-RUN: ' if dry_run else ''}{len(plan)} governed calls for {applicants} applicant(s) "
          f"→ {base}\n")
    failures = 0
    for agent, action_type, payload, label in plan:
        ikey = f"{label.split(':')[0]}-{action_type}-{uuid.uuid4().hex[:8]}"
        if dry_run:
            print(f"  [{agent:<8}] {action_type:<22} {label}")
            continue
        status, body = _propose(base, api_key, action_type, payload, ikey)
        # These status codes are GOVERNANCE OUTCOMES, not transport failures:
        #   202 COMPLETED → executed + sealed · 202 PENDING_APPROVAL → gated, awaiting an approver
        #   (queued to /v1/approvals; seals when approved) · 403 → policy DENY · 422 → HALT.
        if 200 <= status < 300:
            state = body.get("state", "COMPLETED") if isinstance(body, dict) else "COMPLETED"
            if state == "PENDING_APPROVAL":
                marker, outcome = "⏸", "PENDING_APPROVAL (queued; seals on approve)"
            else:
                marker, outcome = "✓", f"{state} (sealed)"
        elif status == 403:
            marker, outcome = "⛔", "DENIED by policy"
        elif status == 422:
            marker, outcome = "⏸", "HALTED (approval gate)"
        else:
            marker, outcome = "✗", f"[{status}] {body}"
            failures += 1
        print(f"  {marker} [{agent:<8}] {action_type:<22} {label[:44]:<44} → {outcome}")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description="Fake credit + KYC/AML AI → governed calls to a live kernel.")
    ap.add_argument("--base", default=os.getenv("QUAICU_BASE", "https://kernel.quaicu.org"))
    ap.add_argument("--api-key", default=os.getenv("QUAICU_API_KEY"))
    ap.add_argument("--applicants", type=int, default=5, help="applicants/loans per pass")
    ap.add_argument("--loop", action="store_true", help="keep firing passes (Ctrl-C to stop)")
    ap.add_argument("--interval", type=float, default=20.0, help="seconds between passes when --loop")
    ap.add_argument("--dry-run", action="store_true", help="print the call plan; send nothing")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    if not args.dry_run and not args.api_key:
        print("No API key. Set QUAICU_API_KEY or pass --api-key (console → API Keys). Or use --dry-run.")
        return 2

    try:
        while True:
            failures = _run_once(base, args.api_key or "", args.applicants, args.dry_run)
            if not args.dry_run and failures:
                print(f"\n{failures} call(s) failed. Common causes: key lacks action-write scope (403); "
                      "packs not activated in this tenant (actions fall through to fail-closed deny). "
                      "See README → Real environment.")
            if not args.loop or args.dry_run:
                break
            print(f"\n…next pass in {args.interval:g}s (Ctrl-C to stop)\n")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped.")
    print("\n✓ = executed + sealed (console → Audit + Download proof bundle).")
    print("⛔ = denied by an active policy (fail-closed).")
    print("⏸ = require-approval: durably queued (console → Approvals). Approving it executes + seals")
    print("     the action (kernel.resume_approved) — note an approver must differ from the proposer")
    print("     (separation of duties). See LIVE_DEMO_RUNBOOK.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
