# Zero-egress topology & validation

> The "prompts never touch the public internet" claim is **specified but not yet proven at scale**
> (W5-3). This is the target topology and the **method to prove it** — turning an architecture
> assertion into evidence an auditor/regulator will accept.

_Owner: [platform/sec] · Tracks ACTION_TRACKER **W5-3** · Last updated: 2026-06-23_

## Target topology
```
        Cloudflare Worker (edge)
                 │  (only public ingress)
                 ▼
   ┌─────────────────────────────────────┐  VPC Service Controls perimeter
   │  Cloud Run (egress → VPC connector)  │  (org/folder-level; data-exfil boundary)
   │        │                             │
   │        ├── Private Google Access ──► Cloud SQL (private IP)
   │        ├── Private Google Access ──► Secret Manager / Logging (restricted.googleapis.com)
   │        └── Private endpoint ───────► Vertex AI (in-region inference)
   └─────────────────────────────────────┘
            egress firewall: DENY all to 0.0.0.0/0 (no public internet route)
```

## Controls (and where IaC supports them)
| Control | Purpose | Where |
|---------|---------|-------|
| Serverless VPC Access connector + `egress = ALL_TRAFFIC` | force Cloud Run egress onto the VPC | `gcp-saas` module, `enable_private_egress=true` |
| Private IP Cloud SQL | DB never on a public IP | `gcp-saas` module (private path under the flag) |
| Private Google Access / `restricted.googleapis.com` routes | reach Google APIs without public internet | VPC config (platform) |
| Egress firewall deny-all to `0.0.0.0/0` | no route off the VPC to the internet | VPC firewall (platform) |
| **VPC Service Controls perimeter** | block data exfiltration even via Google APIs | **org-level** (Access Context Manager) — see below |
| In-region Vertex AI private endpoint | prompts/inference stay in-region & private | platform |

> **Why VPC-SC is not in the project module:** a perimeter is defined at the **org/folder** via
> `google_access_context_manager_access_policy` + `_service_perimeter`, owned by the org admin, and a
> half-applied perimeter can lock you out. The `gcp-saas` module provides the project-scoped pieces
> (VPC egress, private IP) behind `enable_private_egress`; wire the perimeter separately with the
> platform team.

## Validation method (produce evidence)
1. **Config attestation** — confirm: connector attached + `egress=ALL_TRAFFIC`; Cloud SQL has no public
   IP; egress firewall denies `0.0.0.0/0`; VPC-SC perimeter encloses the project with the relevant
   restricted services. Capture `gcloud` describes / Terraform state as artifacts.
2. **Negative test (deny-by-default)** — from inside a plane instance (debug job), attempt egress to a
   known public endpoint → must **fail/timeout**. Attempt the same to a Google API via the private
   route → must succeed. Record both.
3. **VPC-SC dry-run** — run the perimeter in dry-run mode and inspect the audit logs for any blocked
   egress the live config would have denied; promote to enforced once clean.
4. **Flow-log review** — enable VPC flow logs; sample a window of real traffic; assert zero egress to
   public IPs outside the allowed set.
5. **Inference path** — confirm Vertex (or the configured model endpoint) is reached via a private/
   in-region endpoint; assert no prompt leaves the perimeter. (BYO-key AI Gateway passthrough, W6-2, is
   a deliberate exception — document it as out-of-perimeter or proxy it through the private path.)

## Evidence pack (for the trust center / auditors)
- The config attestation (step 1) + negative-test results (step 2) + a flow-log/perimeter-log sample
  (steps 3–4), dated, per region. Link from `SECURITY.md` and the CAIQ/SIG answers.

## Status & gaps
- **IaC:** project-scoped private egress is opt-in in `gcp-saas` (default off). ✅
- **Org-level VPC-SC perimeter:** not yet stood up — platform action. ⏳
- **Proof at scale:** the validation runs above have not been executed — this is the remaining W5-3
  work and the honest gap behind the sovereignty claim.
