"""Config-driven email-sender wiring (transactional email for verified signup / recovery).

Builds the `EmailSender` `create_app` consumes. With a Resend API key (``[email].resend_api_key`` or
the ``RESEND_API_KEY`` env var) it returns the live `ResendEmailAdapter`; otherwise a
`LogOnlyEmailSender` (the OTP is written to the log so the flow is testable locally). The from-address
comes from ``[email].from`` / ``EMAIL_FROM`` and defaults to Resend's shared ``onboarding@resend.dev``
sender — switch it to ``no-reply@your-domain`` once that domain is verified in Resend.

Config shape::

    [email]
    resend_api_key = "${RESEND_API_KEY}"   # omit → log-only (dev)
    from           = "${EMAIL_FROM}"        # default onboarding@resend.dev
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

_DEFAULT_FROM = "onboarding@resend.dev"


def build_email_sender(config: Mapping[str, Any]) -> Any:
    """Return a Resend sender when an API key is configured, else a log-only sender."""
    section = config.get("email", {}) or {}
    api_key = (os.path.expandvars(str(section.get("resend_api_key", ""))) or os.getenv("RESEND_API_KEY", "")).strip()
    sender = (os.path.expandvars(str(section.get("from", ""))) or os.getenv("EMAIL_FROM", "")).strip() or _DEFAULT_FROM

    if not api_key:
        from adapters.email import LogOnlyEmailSender

        return LogOnlyEmailSender()

    from adapters.email import ResendEmailAdapter

    return ResendEmailAdapter(api_key=api_key, sender=sender)
