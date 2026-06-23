# Wave 5 — Data residency / sovereignty tracker

> The residency/sovereignty items from `ACTION_TRACKER.md`. Genuinely code (Terraform) — the IaC +
> region presets + opt-in zero-egress scaffolding landed this pass; applying it and proving zero-egress
> at scale stay human/ops.

_Last updated: 2026-06-23 · Source of truth for status: update here as items move._

## Status
| Item | ID | Type | Status | Next concrete action | Artifact |
|------|----|------|--------|----------------------|----------|
| **Terraform the SaaS plane** | W5-1 | code | **Module authored** (mirrors gcp-enterprise) | `terraform validate` + import the live service (README) | `deploy/terraform/gcp-saas/` |
| **Multi-region deploy** | W5-2 | code | **Region-parameterized + EU/India/Gulf presets** | Apply a non-US zone to a real project; route the edge | `deploy/terraform/gcp-saas/regions/*.tfvars` |
| **Zero-egress (VPC-SC/PrivateLink)** | W5-3 | code | **Opt-in IaC + validation method** (default off) | Stand up org VPC-SC perimeter; run the validation method to produce evidence | `docs/operations/ZERO_EGRESS_VALIDATION.md` |
| **Per-region residency guarantees** | W5-4 | human | **Matrix documented** | Fill per-zone guarantees once a region is deployed | `docs/operations/DATA_RESIDENCY.md` |

## What landed this pass
- New `deploy/terraform/gcp-saas/` module (`main/variables/outputs.tf` + README) codifying the
  hand-deployed `quaicu-kernel` Cloud Run service + Cloud SQL + Secret Manager, region-parameterized.
- `regions/{eu,india,gulf}.tfvars` presets (one stack per residency zone).
- Opt-in `enable_private_egress` (VPC connector + private Cloud SQL), default **off** so a plain apply
  is unchanged.
- `DATA_RESIDENCY.md` (matrix + caveats: Logging/Secret-Manager replication + external processors) and
  `ZERO_EGRESS_VALIDATION.md` (topology + evidence-producing validation method).

## What stays human/ops
- Running `terraform validate`/`apply` (no creds here); importing the existing live service.
- The **org-level VPC-SC perimeter** (Access Context Manager) and **proving zero-egress at scale**
  (the validation runs) — the honest remaining gap behind the sovereignty claim.
- Pinning regional log buckets + Secret Manager replication; confirming Razorpay/Resend regions.
