# Deployment Tiers

The QUAICU Kernel ships as a single Docker image. The deployment tier is determined by `kernel.toml` configuration.

## Comparison

| | Sovereign | Dedicated | SaaS |
|---|---|---|---|
| **Who hosts** | Customer hardware | Customer cloud (VPC) | QUAICU |
| **Network** | Air-gapped / on-premise | Private VPC, no egress | Internet-connected |
| **Inference** | Ollama / vLLM (local) | Vertex / Bedrock (private) | OpenAI / Anthropic / Vertex |
| **Database** | Single DB, single tenant | One DB per tenant | Shared, schema-per-tenant + RLS |
| **Isolation** | Physical | Instance-level | Schema + Row-Level Security |
| **Signing** | OpenBao (Ed25519) | Cloud KMS (ECDSA P-256) | Cloud KMS |
| **Best for** | Banks, defence, highly regulated | Large enterprises with cloud | SaaS products, startups, agencies |

## Sovereign

Customer controls all hardware, all keys, all data. The kernel never makes outbound network calls. Suitable for RBI-regulated banks, defence, and institutions with strict data residency requirements.

→ [Deploy Sovereign →](../how-to/deploy-sovereign.md)

## Dedicated

Kernel runs in a customer-controlled VPC (AWS or GCP). QUAICU deploys via Terraform but the customer holds the cloud account and the KMS keys. Managed inference (Vertex, Bedrock) accessed via private endpoints.

→ [Deploy Dedicated →](../how-to/deploy-dedicated.md)

## SaaS

QUAICU-hosted. Zero operational burden for the customer. Shared infrastructure with schema-per-tenant isolation and Row-Level Security. Appropriate for SaaS builders, startups, and agencies who want to ship governed AI without infrastructure investment.

Contact [hello@quaicu.org](mailto:hello@quaicu.org) for SaaS onboarding.
