"""Company-email enforcement for self-serve signup (ADR-0010).

Self-serve signups must use a company/work email — free and personal mailbox providers are rejected.
This keeps the funnel B2B, reduces throwaway-account abuse, and means a tenant's email domain is a
weak signal of the owning organisation. The list below is the common consumer providers; it is not
exhaustive and is intentionally conservative (a false "company" classification is the safe default,
since the OTP step still proves control of the address).
"""

from __future__ import annotations

from core.errors import EmailDomainNotAllowedError

# Common free / personal mailbox providers. Lowercase, bare registrable domains.
FREE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.in",
        "yahoo.co.uk",
        "ymail.com",
        "rocketmail.com",
        "outlook.com",
        "hotmail.com",
        "hotmail.co.uk",
        "live.com",
        "msn.com",
        "aol.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "proton.me",
        "protonmail.com",
        "pm.me",
        "gmx.com",
        "gmx.net",
        "mail.com",
        "zoho.com",
        "yandex.com",
        "yandex.ru",
        "tutanota.com",
        "tuta.io",
        "rediffmail.com",
        "fastmail.com",
        "hey.com",
        "qq.com",
        "163.com",
        "126.com",
    }
)


def email_domain(email: str) -> str:
    """Return the lowercased domain of ``email`` (``""`` if it has no ``@``)."""
    _, _, domain = email.strip().lower().rpartition("@")
    return domain


def is_company_email(email: str) -> bool:
    """True if ``email`` is well-formed and its domain is not a known free/personal provider."""
    local, sep, domain = email.strip().partition("@")
    if not sep or not local or "." not in domain or " " in email.strip():
        return False
    return domain.lower() not in FREE_EMAIL_DOMAINS


def assert_company_email(email: str) -> None:
    """Raise `EmailDomainNotAllowedError` unless ``email`` is a valid company address."""
    if not is_company_email(email):
        raise EmailDomainNotAllowedError(
            "Please use your company email address — free/personal email providers "
            "(gmail, yahoo, outlook, …) aren't accepted for signup.",
            detail={"email": email, "domain": email_domain(email)},
        )
