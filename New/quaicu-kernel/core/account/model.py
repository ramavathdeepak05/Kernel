"""Account & API-key — data model (ADR-0010).

An `Account` is the customer org that owns a tenant. `ApiKey` is a credential for the kernel's own
management API (the self-serve path that doesn't bring an external IdP token). Secrets are never
stored: only a SHA-256 hash of the secret is kept, alongside a public ``key_id`` prefix used to look
the key up. Immutable, like every other kernel domain model.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from core.account.scopes import OWNER_SCOPES
from core.types import TenantId


class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class Account:
    """A customer organisation, 1:1 with a tenant on signup.

    ``name`` is the organisation / workspace name (also the tenant-id slug source). The professional
    contact fields (collected by the verified-signup form) default to empty for backward compatibility
    with accounts created before they existed.
    """

    account_id: str
    tenant_id: TenantId
    email: str
    name: str
    status: AccountStatus
    created_at: datetime
    full_name: str = ""     # the person who signed up
    job_title: str = ""     # their role (e.g. "Compliance Lead")
    phone: str = ""         # contact number (E.164 or free-form)
    password_hash: str = ""  # scrypt hash for console email+password login (see passwords.py)
    # Onboarding survey answers (use_case, industry, company_size, regulations) — stored as JSON.
    profile: Mapping[str, object] = field(default_factory=dict)
    paid_until: datetime | None = None  # ₹2/yr signup fee — account is paid through this date


@dataclass(frozen=True)
class AIConnection:
    """A tenant's BYO upstream LLM provider — used by the governed AI gateway to forward calls.

    The ``api_key`` is the customer's own provider key. It is encrypted at rest (the account engine
    seals it into the account profile) and only ever materialised here for the outbound call.
    """

    provider: str          # display label, e.g. "openai" | "together" | "azure" | "custom"
    base_url: str          # OpenAI-compatible base, e.g. "https://api.openai.com/v1"
    api_key: str           # the customer's provider key (plaintext in memory only)
    default_model: str = ""  # used when a request omits "model"
    updated_at: datetime | None = None
    mask_pii: bool = False  # opt-in (all tiers): tokenize PII before forwarding to the provider (W6-2)
    api_version: str = ""   # Azure OpenAI api-version query param; empty for non-Azure providers (W6-2)
    project: str = ""       # GCP project id (Vertex); empty otherwise (W6-2)
    location: str = ""      # cloud region: GCP region (Vertex) or AWS region (Bedrock); empty otherwise (W6-2)
    aws_access_key_id: str = ""  # AWS access key id (Bedrock); the secret key lives in api_key (W6-2)


@dataclass(frozen=True)
class SignupDetails:
    """The customer details collected by the verified-signup form (POST /v1/signup/start).

    ``company_name`` becomes the `Account.name` / tenant label. ``email`` must be a company address
    (see `core/account/email_domains`). Carried (encrypted) through the OTP step, then provisioned.
    """

    full_name: str
    email: str
    company_name: str
    password: str            # plaintext only in transit; hashed at provisioning, never stored
    job_title: str = ""
    phone: str = ""
    # Onboarding survey (all required by product): how they'll use the kernel + segmentation.
    use_case: str = ""
    industry: str = ""
    company_size: str = ""
    regulations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ApiKey:
    """A hashed API-key record. The plaintext secret is shown once at issuance and never stored.

    A presented key is ``qk_<key_id>_<secret>``; ``key_id`` locates this record, then ``secret`` is
    hashed and compared to ``hashed_secret`` in constant time.
    """

    key_id: str
    tenant_id: TenantId
    hashed_secret: str          # hex SHA-256 of the secret half
    created_at: datetime
    revoked: bool = False
    # RBAC scopes this key may exercise (see core/account/scopes.py). The signup key gets all.
    scopes: frozenset[str] = field(default_factory=lambda: OWNER_SCOPES)
    # The member this key belongs to (W6-1), if any. Deactivating that member revokes the key.
    # Empty for the legacy bootstrap/tenant key, which is unaffected by member lifecycle.
    member_id: str = ""


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """The resolved caller behind a verified credential — what the auth layer hands to routes.

    Carries what authorization needs: the tenant the credential belongs to, its owning account, the
    key id (for audit/revocation), the scopes it may exercise, and the governance ``roles`` of the
    underlying account/member. The credential (API key or session JWT) is verified by the account
    engine, so a governed-action route may use this principal as the **host-provided governance
    actor** (its `account_id` is the actor id; `roles` drive policy) without re-resolving an IdP
    token — see `delivery/api/deps.resolve_governed_actor`.
    """

    tenant_id: TenantId
    account_id: str
    key_id: str
    scopes: frozenset[str]
    roles: tuple[str, ...] = ()

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


class MemberStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DEACTIVATED = "DEACTIVATED"  # SCIM `active=false` / removed from the IdP → access revoked


@dataclass(frozen=True)
class Member:
    """A user within a tenant (W6-1). Multiple members per tenant, each carrying a `role` (see
    `core.account.roles`). Provisioned via the console Team page or an enterprise IdP over SCIM 2.0;
    `external_id` is the IdP's stable user id (set by SCIM). Deactivating a member revokes their access.
    """

    member_id: str
    tenant_id: TenantId
    email: str
    display_name: str
    role: str  # a core.account.roles.Role wire value (e.g. "ADMIN"); validated at the engine boundary
    status: MemberStatus
    created_at: datetime
    external_id: str = ""  # SCIM IdP user id (empty for console-invited members)
