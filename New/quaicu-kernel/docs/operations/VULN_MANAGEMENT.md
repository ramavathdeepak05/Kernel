# Vulnerability Management policy

> How QUAICU finds, prioritizes, and patches vulnerabilities — scanning cadence, patch SLAs, and the
> plan to graduate CI scans from report-only to build-blocking.

_Owner: [security] · Tracks ACTION_TRACKER **W4-9** · Last updated: 2026-06-23_

## 1. Scanning (what runs where)
| Scan | Tool | Where | Mode today |
|------|------|-------|------------|
| **Dependency vulns** | `pip-audit` against `requirements.lock` | CI (`cloudbuild.yaml`) | **report-only** |
| **Container image vulns** | **Trivy** (HIGH/CRITICAL) on the built image | CI (`cloudbuild.yaml`) | **report-only** |
| **SBOM** | Trivy CycloneDX → build artifact | CI (`cloudbuild.yaml`) | generated each build |
| **Lint + unit tests** | ruff + pytest | CI gate before build | **blocking** |
| **Disclosed vulns** | `security@quaicu.org` intake | `SECURITY.md` | continuous |

> The scan steps run in **report mode** (`--exit-code 0` / `|| true`) so introducing scanning does not
> break the existing deploy pipeline on day one. The lint+test gate **is** blocking.

## 2. Patch SLAs (by severity)
Triaged from the CVSS rating, adjusted for exploitability + exposure (internet-facing > internal):
| Severity | Remediate within |
|----------|------------------|
| **Critical** | `[7]` days (or mitigate immediately) |
| **High** | `[30]` days |
| **Medium** | `[90]` days |
| **Low** | best-effort / next maintenance |

"Remediate" = patch, upgrade, or document a compensating control + accepted-risk with an owner + expiry.

## 3. Graduation plan: report → blocking
1. **Now:** scans report-only; review findings each build; clear the existing backlog to within SLA.
2. **Next:** once the backlog is clean, flip **Trivy** to fail on **CRITICAL** (`--exit-code 1
   --severity CRITICAL`) and **pip-audit** to blocking — edit `cloudbuild.yaml` (remove `|| true` /
   set `--exit-code 1`).
3. **Then:** extend blocking to **HIGH**; add image **signing (cosign)** + SBOM attestation for
   provenance (not yet implemented — tracked here).

## 4. Dependency hygiene
- `requirements.lock` is the hash-pinned source of truth (generated from `pyproject.toml`).
- Update cadence: `[monthly]` + immediately for an in-SLA Critical/High advisory.
- Prefer minimal, reviewed bumps; re-run the full test suite on any dependency change.

## 5. Ownership & review
- Security owns triage; eng owns the fix within SLA.
- Review open findings at a `[weekly]` cadence; record exceptions (accepted risks) with expiry dates.
- Surface the current posture (last scan, open Critical/High count) in the trust center (W4-6).
