"""Transactional email seam (signup OTP, account recovery).

A single outbound port. Core never imports an email SDK — only `EmailSender` + `EmailMessage`.
Adapters live in `adapters/email/` (Resend REST, plus a log-only dev fallback).
"""

from __future__ import annotations

from core.email.port import EmailMessage, EmailSender

__all__ = ["EmailMessage", "EmailSender"]
