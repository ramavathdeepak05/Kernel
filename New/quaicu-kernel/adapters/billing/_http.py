"""Minimal injectable async HTTP POST for billing checkout creation (WS-C).

The webhook *verification* path stays pure (HMAC + JSON only). Checkout *creation* must call the
provider's REST API, so that one network operation lives behind this tiny seam: a callable the
adapter is constructed with. Tests inject a fake; production uses the stdlib default below — no SDK,
no new third-party dependency. The blocking ``urllib`` call is offloaded to a thread so it does not
stall the event loop.
"""

from __future__ import annotations

import asyncio
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable, Mapping

# (url, body_bytes, headers) -> (status_code, response_text)
HttpPost = Callable[[str, bytes, Mapping[str, str]], Awaitable[tuple[int, str]]]


async def urllib_post(url: str, body: bytes, headers: Mapping[str, str]) -> tuple[int, str]:
    """Default transport: a blocking ``urllib`` POST run in a worker thread.

    Returns ``(status_code, response_text)`` for any HTTP response (including 4xx/5xx — the caller
    decides how to interpret a non-2xx). Network/transport failures propagate as ``URLError``.
    """

    def _do() -> tuple[int, str]:
        req = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — fixed provider hosts
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    return await asyncio.to_thread(_do)
