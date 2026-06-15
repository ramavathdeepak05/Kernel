"""Unit tests for RazorpayBillingAdapter — signature verification + event mapping (WS-C)."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from adapters.billing import RazorpayBillingAdapter
from core.billing.model import BillingEventType
from core.entitlements import FeatureTier
from core.errors import BillingEventError, WebhookVerificationError

SECRET = "rzp_whsec"
PLAN_MAP = {"plan_biz": FeatureTier.BUSINESS, "plan_ent": FeatureTier.ENTERPRISE}


def _adapter() -> RazorpayBillingAdapter:
    return RazorpayBillingAdapter(webhook_secret=SECRET, plan_to_tier=PLAN_MAP)


def _sign(body: bytes) -> dict[str, str]:
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {"x-razorpay-signature": sig}


def _event(event="subscription.activated", *, plan="plan_biz", tenant="acme-co", sub_id="sub_rzp") -> bytes:
    entity = {"id": sub_id, "plan_id": plan, "notes": {"tenant": tenant} if tenant else {}}
    return json.dumps({"event": event, "payload": {"subscription": {"entity": entity}}}).encode()


def test_valid_signature_parses_active_event():
    body = _event()
    ev = _adapter().verify_and_parse(payload=body, headers=_sign(body))
    assert ev.event_type is BillingEventType.SUBSCRIPTION_ACTIVE
    assert ev.target_tier is FeatureTier.BUSINESS
    assert str(ev.tenant_id) == "acme-co"
    assert ev.external_ref == "sub_rzp"


def test_missing_signature_rejected():
    body = _event()
    with pytest.raises(WebhookVerificationError):
        _adapter().verify_and_parse(payload=body, headers={})


def test_tampered_body_rejected():
    body = _event()
    headers = _sign(body)
    with pytest.raises(WebhookVerificationError):
        _adapter().verify_and_parse(payload=body + b"x", headers=headers)


def test_halted_maps_to_payment_failed():
    body = _event(event="subscription.halted")
    ev = _adapter().verify_and_parse(payload=body, headers=_sign(body))
    assert ev.event_type is BillingEventType.PAYMENT_FAILED


def test_cancelled_maps_to_cancelled():
    body = _event(event="subscription.cancelled")
    ev = _adapter().verify_and_parse(payload=body, headers=_sign(body))
    assert ev.event_type is BillingEventType.SUBSCRIPTION_CANCELLED


def test_unmapped_plan_raises():
    body = _event(plan="plan_unknown")
    with pytest.raises(BillingEventError):
        _adapter().verify_and_parse(payload=body, headers=_sign(body))


def test_irrelevant_event_ignored():
    body = json.dumps({"event": "payment.captured", "payload": {}}).encode()
    ev = _adapter().verify_and_parse(payload=body, headers=_sign(body))
    assert ev.event_type is BillingEventType.IGNORED
