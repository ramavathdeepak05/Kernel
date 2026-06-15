"""Unit tests for StripeBillingAdapter — signature verification + event mapping (WS-C)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from adapters.billing import StripeBillingAdapter
from core.billing.model import BillingEventType
from core.entitlements import FeatureTier
from core.errors import BillingEventError, WebhookVerificationError

SECRET = "whsec_test"
PRICE_MAP = {"price_business": FeatureTier.BUSINESS, "price_enterprise": FeatureTier.ENTERPRISE}


def _adapter() -> StripeBillingAdapter:
    return StripeBillingAdapter(webhook_secret=SECRET, price_to_tier=PRICE_MAP)


def _sign(body: bytes, *, ts: int | None = None) -> dict[str, str]:
    ts = ts or int(time.time())
    signed = f"{ts}.".encode() + body
    sig = hmac.new(SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return {"stripe-signature": f"t={ts},v1={sig}"}


def _sub_event(event_type="customer.subscription.updated", *, status="active", price="price_business",
               tenant="acme-co", sub_id="sub_123") -> bytes:
    obj = {
        "id": sub_id,
        "status": status,
        "metadata": {"tenant": tenant} if tenant else {},
        "items": {"data": [{"price": {"id": price}}]},
    }
    return json.dumps({"id": "evt_1", "type": event_type, "data": {"object": obj}}).encode()


# ── Signature verification ──────────────────────────────────────────────────────


def test_valid_signature_parses_active_event():
    body = _sub_event()
    ev = _adapter().verify_and_parse(payload=body, headers=_sign(body))
    assert ev.event_type is BillingEventType.SUBSCRIPTION_ACTIVE
    assert ev.target_tier is FeatureTier.BUSINESS
    assert str(ev.tenant_id) == "acme-co"
    assert ev.external_ref == "sub_123"


def test_missing_signature_rejected():
    body = _sub_event()
    with pytest.raises(WebhookVerificationError):
        _adapter().verify_and_parse(payload=body, headers={})


def test_tampered_body_rejected():
    body = _sub_event()
    headers = _sign(body)
    with pytest.raises(WebhookVerificationError):
        _adapter().verify_and_parse(payload=body + b" ", headers=headers)


def test_wrong_secret_rejected():
    body = _sub_event()
    headers = _sign(body)
    other = StripeBillingAdapter(webhook_secret="whsec_other", price_to_tier=PRICE_MAP)
    with pytest.raises(WebhookVerificationError):
        other.verify_and_parse(payload=body, headers=headers)


def test_stale_timestamp_rejected():
    body = _sub_event()
    headers = _sign(body, ts=int(time.time()) - 10_000)
    with pytest.raises(WebhookVerificationError, match="tolerance"):
        _adapter().verify_and_parse(payload=body, headers=headers)


# ── Event mapping ───────────────────────────────────────────────────────────────


def test_deleted_subscription_maps_to_cancelled():
    body = _sub_event(event_type="customer.subscription.deleted")
    ev = _adapter().verify_and_parse(payload=body, headers=_sign(body))
    assert ev.event_type is BillingEventType.SUBSCRIPTION_CANCELLED


def test_past_due_status_maps_to_payment_failed():
    body = _sub_event(status="past_due")
    ev = _adapter().verify_and_parse(payload=body, headers=_sign(body))
    assert ev.event_type is BillingEventType.PAYMENT_FAILED


def test_unmapped_price_raises():
    body = _sub_event(price="price_unknown")
    with pytest.raises(BillingEventError):
        _adapter().verify_and_parse(payload=body, headers=_sign(body))


def test_irrelevant_event_ignored():
    body = json.dumps({"id": "evt", "type": "charge.refunded", "data": {"object": {}}}).encode()
    ev = _adapter().verify_and_parse(payload=body, headers=_sign(body))
    assert ev.event_type is BillingEventType.IGNORED
