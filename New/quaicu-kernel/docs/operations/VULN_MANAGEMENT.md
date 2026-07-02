# Vulnerability Management policy

> How QUAICU finds, prioritizes, and patches vulnerabilities — scanning cadence, patch SLAs, and the
> plan to graduate CI scans from report-only to build-blocking.

_Owner: [security] · Tracks ACTION_TRACKER **W4-9 / D0-3** · Last updated: 2026-07-01_

## 1. Scanning (what runs where)
| Scan | Tool | Where | Mode today |
|------|------|-------|------------|
| **Dependency vulns** | `pip-audit` against `requirements.lock` **+ `requirements-gcp.lock`** | CI (`cloudbuild.yaml`) | **blocking** |
| **Container image vulns** | **Trivy** (HIGH/CRITICAL, fixable) on the built image | CI (`cloudbuild.yaml`) | **blocking** |
| **SBOM** | Trivy CycloneDX → build artifact **+ cosign attestation** | CI (`cloudbuild.yaml`) | generated each build |
| **Image signing** | **cosign** (Cloud KMS HSM, `--tlog-upload=false`) on the pushed digest | CI (`cloudbuild.yaml`) | **every pushed image signed** |
| **Lint + unit tests** | ruff + pytest | CI gate before build | **blocking** |
| **Disclosed vulns** | `security@quaicu.org` intake | `SECURITY.md` | continuous |

> **D0-3 (2026-07-01): the scans are now BLOCKING.** `pip-audit` and Trivy fail the build on a fixable
> finding; the CycloneDX SBOM is produced every build; every pushed image is signed by a Cloud KMS key.
> Documented, time-bounded exceptions: dependency advisories via `pip-audit --ignore-vuln <ID>` in
> `cloudbuild.yaml`; image CVEs via `.trivyignore` — each with an owner + expiry (§2/§5).

## 2. Patch SLAs (by severity)
Triaged from the CVSS rating, adjusted for exploitability + exposure (internet-facing > internal):
| Severity | Remediate within |
|----------|------------------|
| **Critical** | `[7]` days (or mitigate immediately) |
| **High** | `[30]` days |
| **Medium** | `[90]` days |
| **Low** | best-effort / next maintenance |

"Remediate" = patch, upgrade, or document a compensating control + accepted-risk with an owner + expiry.

## 3. Graduation plan: report → blocking  — ✅ COMPLETE (D0-3, 2026-07-01)
1. ~~**Now:** scans report-only; review findings each build; clear the backlog to within SLA.~~ Done.
2. ✅ **pip-audit blocking** (no `|| true`; audits both locks) and **Trivy blocking**. We went
   straight to **HIGH,CRITICAL** (not just CRITICAL) with `--ignore-unfixed`, matching the already-
   shipped `.github/workflows/release.yml` gate.
3. ✅ **Image signing (cosign) + SBOM attestation implemented.** Signing uses **Cloud KMS** (sovereign
   FIPS-140-2 HSM, same pattern as the K·02 ledger signer) with `--tlog-upload=false` so it runs inside
   a zero-egress/VPC-SC perimeter (no public Rekor dependency). Each pushed image digest is signed and
   gets a CycloneDX SBOM attestation.

### One-time KMS setup the cosign step requires
The `cosign-sign` step authenticates as the Cloud Build service account (ADC). Provision a signing key
and grant the SA `signerVerifier`, then set `_COSIGN_KMS_KEY` in `cloudbuild.yaml` (these are mutating
cloud operations — run them deliberately):

```bash
# Reuses the quaicu-ledger keyring; create it first if absent.
gcloud kms keyrings create quaicu-ledger --location us-central1 || true
gcloud kms keys create cosign-signer --keyring quaicu-ledger --location us-central1 \
    --purpose asymmetric-signing --default-algorithm ec-sign-p256-sha256
# Grant the Cloud Build SA (PROJECT_NUMBER@cloudbuild.gserviceaccount.com) signing rights.
gcloud kms keys add-iam-policy-binding cosign-signer --keyring quaicu-ledger \
    --location us-central1 \
    --member "serviceAccount:<PROJECT_NUMBER>@cloudbuild.gserviceaccount.com" \
    --role roles/cloudkms.signerVerifier
```

`_COSIGN_KMS_KEY` =
`projects/ordinal-quarter-499114-s2/locations/us-central1/keyRings/quaicu-ledger/cryptoKeys/cosign-signer/cryptoKeyVersions/1`.
Consumers verify with `cosign verify --key gcpkms://${_COSIGN_KMS_KEY} <image@digest>` and
`cosign verify-attestation --type cyclonedx --key gcpkms://${_COSIGN_KMS_KEY} <image@digest>`.

## 4. Dependency hygiene
- `requirements.lock` is the hash-pinned source of truth (generated from `pyproject.toml`).
- Update cadence: `[monthly]` + immediately for an in-SLA Critical/High advisory.
- Prefer minimal, reviewed bumps; re-run the full test suite on any dependency change.

## 5. Ownership & review
- Security owns triage; eng owns the fix within SLA.
- Review open findings at a `[weekly]` cadence; record exceptions (accepted risks) with expiry dates.
- Surface the current posture (last scan, open Critical/High count) in the trust center (W4-6).
