# Operations docs (internal — "run the product")

Operator/runbook material for **you** (ops, SRE, sales engineering) — not end users. End-user docs
("use the product") live one level up in `docs/` (e.g. `HOSTING.md`, `CEL_POLICY_GUIDE.md`).

- **[DEPLOY_CLOUD_RUN.md](DEPLOY_CLOUD_RUN.md)** — stand up the hosted SaaS plane (free STARTER + paid
  BUSINESS) on Cloud Run; the Model A "you host it" runbook.
- **[GO_LIVE_SETUP.md](GO_LIVE_SETUP.md)** — full SaaS launch checklist: API, console, Stripe/Razorpay
  payments, database/migrations, OIDC, DNS/TLS.
- **[DEPLOYMENT_MODELS.md](DEPLOYMENT_MODELS.md)** — Model A (you host) vs Model B (customer hosts);
  sales/solution-architect positioning.

Related (not in this folder): the customer-hosted ENTERPRISE Terraform is a *deliverable* at
`deploy/terraform/gcp-enterprise/`; internal strategy is `docs/strategy/`.
