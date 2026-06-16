"""Config-driven usage-meter selection.

Returns a shared **Redis** meter when a ``[metering]`` section (or ``REDIS_URL``) is configured —
exact cross-replica counts for a horizontally-scaled SaaS plane — otherwise the in-process
`UsageMeter` (fine for a single worker / dev). Both satisfy the same surface, so `create_app` and the
metering/rate-limit middleware are unchanged.

Config shape::

    [metering]
    redis_url   = "${REDIS_URL}"        # omit → in-process meter
    namespace   = "quaicu:usage"        # optional
    ttl_seconds = 172800                # optional
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from core.metering import UsageMeter


def build_usage_meter(config: Mapping[str, Any]) -> Any:
    """Build the usage meter from a ``[metering]`` section / ``REDIS_URL``; in-process by default."""
    section = config.get("metering", {}) or {}
    url = os.path.expandvars(str(section.get("redis_url", ""))) or os.getenv("REDIS_URL", "")
    if not url:
        return UsageMeter()
    from adapters.metering import RedisUsageMeter

    return RedisUsageMeter(
        url=url,
        namespace=str(section.get("namespace", "quaicu:usage")),
        ttl_seconds=int(section.get("ttl_seconds", 172_800)),
    )
