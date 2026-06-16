# Security Policy

*[DRAFT — confirm the reporting address, PGP key, and SLAs before publishing.]*

QUAICU Kernel is a fail-closed AI governance control plane; we take security
reports seriously and aim to respond quickly.

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.** Instead, email
**[security@quaicu.example]** with:

- a description of the issue and its impact,
- steps to reproduce (PoC if possible),
- affected version / image digest / commit, and
- any suggested remediation.

Encrypt sensitive reports with our PGP key: **[link/fingerprint TBD]**.

We will acknowledge receipt within **2 business days**, provide an initial
assessment within **5 business days**, and keep you updated through resolution.
We support coordinated disclosure and will credit reporters who wish to be named.

## Scope

In scope: the kernel (`New/quaicu-kernel/` — core, adapters, delivery), the
published container image (`ghcr.io/<owner>/kernel`), and the operator console.

Out of scope: third-party services (GCP/AWS, Stripe/Razorpay, OpenBao), issues
requiring a compromised host or privileged local access, and findings against the
example/demo configuration (e.g. dev tokens in `kernel.dev.toml`).

## Supported versions

Security fixes are provided for the latest released minor version. Older versions
are supported only under an active ENTERPRISE agreement.

## Our security posture (for reviewers)

- **Fail-closed** governance throughout (F-03): unverified/erroring paths deny.
- **Tamper-evident audit:** RFC 6962 Merkle transparency log (K·02), signed tree
  heads via Cloud KMS (FIPS 140-2 L3) or OpenBao. A third-party cryptographic
  review of K·02 (incl. the ECDSA-P256 STH path) is in progress — see
  `docs/CRYPTO_REVIEW_RFQ.md`.
- **Tenant isolation:** per-tenant tables + PostgreSQL Row-Level Security (F-07).
- **Secrets:** API keys stored as HMAC-SHA256 with a server-side pepper; signing
  keys never leave the KMS/HSM. CI runs SBOM generation, Trivy HIGH/CRITICAL
  scanning (fail-closed), and cosign keyless image signing.
- **Reproducible builds:** pinned, hashed `requirements.lock`.
