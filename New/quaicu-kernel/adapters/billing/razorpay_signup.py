"""Razorpay Orders gateway for the one-time ₹2 signup fee.

- ``create_order`` → POST /v1/orders (Basic auth, ``payment_capture=1`` so the fee is captured, not
  just authorized). No SDK — a blocking ``urllib`` call offloaded to a thread, like the billing adapter.
- ``verify_payment`` → Razorpay's standard checkout verification: HMAC-SHA256 over
  ``"<order_id>|<payment_id>"`` keyed by the API secret, compared constant-time to the returned
  signature. Pure (no network), so the synchronous provisioning gate is auditable + testable.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable, Mapping

from core.errors import CheckoutError

HttpPost = Callable[[str, bytes, Mapping[str, str]], Awaitable[tuple[int, str]]]


async def _urllib_post(url: str, body: bytes, headers: Mapping[str, str]) -> tuple[int, str]:
    def _do() -> tuple[int, str]:
        req = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 — fixed provider host
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    return await asyncio.to_thread(_do)


class RazorpaySignupGateway:
    """Razorpay one-time order gateway for the signup fee."""

    def __init__(
        self,
        *,
        key_id: str,
        key_secret: str,
        amount_paise: int = 200,
        currency: str = "INR",
        http_post: HttpPost = _urllib_post,
        api_base: str = "https://api.razorpay.com",
    ) -> None:
        if not key_id or not key_secret:
            raise ValueError("RazorpaySignupGateway requires key_id and key_secret.")
        self._key_id = key_id
        self._key_secret = key_secret
        self._amount = int(amount_paise)
        self._currency = currency
        self._http_post = http_post
        self._api_base = api_base.rstrip("/")

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def amount_paise(self) -> int:
        return self._amount

    @property
    def currency(self) -> str:
        return self._currency

    async def create_order(self, *, receipt: str) -> str:
        body = json.dumps(
            {
                "amount": self._amount,
                "currency": self._currency,
                "receipt": receipt[:40],
                "payment_capture": 1,
            }
        ).encode("utf-8")
        auth = base64.b64encode(f"{self._key_id}:{self._key_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "quaicu-kernel/1.0 (+https://quaicu.org)",
        }
        try:
            status, text = await self._http_post(f"{self._api_base}/v1/orders", body, headers)
        except Exception as exc:  # noqa: BLE001 — transport failure → fail-closed
            raise CheckoutError(f"Razorpay order transport error: {exc}") from exc
        if status >= 300:
            raise CheckoutError(f"Razorpay rejected the order (HTTP {status}): {text[:300]}")
        order_id = json.loads(text).get("id")
        if not order_id:
            raise CheckoutError("Razorpay order response had no id.")
        return str(order_id)

    def verify_payment(self, *, order_id: str, payment_id: str, signature: str) -> bool:
        expected = hmac.new(
            self._key_secret.encode("utf-8"),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature or "")
