# Changelog

## Development history

The kernel was built in six waves:

| Wave | Scope | Status |
|------|-------|--------|
| D0 | Repo scaffold, hexagonal skeleton, CI | Complete |
| D1 | K·01 Policy Engine (CEL), K·02 TrustLedger (Merkle), K·03 HITL Gate | Complete |
| D2 | K·04 DPDP Consent, K·05 AI Gateway (PII masking), K·06 Process Engine | Complete |
| D3 | K·07 Event Bus, K·08 Model Registry — full governance lifecycle end-to-end | Complete |
| D4 | K·09–K·14 extended layers, multi-tenant SaaS plane, console (React), Razorpay | Complete |
| D5 | Security hardening: rate limiter DoS fix, API key HMAC-pepper, OpenBao verify | Complete |
| D6 | Documentation site (this site), website routing, architecture diagram update | In progress |

## Production deployment

**2026** — ALIS deployed. K·01–K·08 live in production.

## Upcoming

- K·09–K·14 first live deployment (design-partner pilot)
- SOC 2 audit (Wave 2–3)
- K·02 third-party cryptographic review
- Trusted forwarded-for handler for load balancer deployments
