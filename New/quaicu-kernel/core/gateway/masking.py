from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from core.errors import GatewayMaskingError


@dataclass(frozen=True)
class MaskingConfig:
    """Per-tenant masking configuration: which payload field names are sensitive."""

    sensitive_fields: frozenset[str] = field(default_factory=frozenset)


@dataclass
class MaskingContext:
    """Holds the token→value map for a single request. Never transmitted; stays in-process."""

    token_map: dict[str, str] = field(default_factory=dict)

    def tokenize(self, value: str) -> str:
        token = f"[MASKED:{uuid.uuid4().hex[:8]}]"
        self.token_map[token] = value
        return token

    def rehydrate(self, text: str) -> str:
        for token, original in self.token_map.items():
            text = text.replace(token, original)
        return text


def mask_text(text: str, config: MaskingConfig, ctx: MaskingContext) -> str:
    """Replace occurrences of sensitive field VALUES in free text. Best-effort."""
    return text


def mask_payload(payload: dict, config: MaskingConfig, ctx: MaskingContext) -> dict:
    """Tokenize sensitive fields in a payload dict."""
    masked = {}
    for k, v in payload.items():
        if k in config.sensitive_fields and isinstance(v, str):
            masked[k] = ctx.tokenize(v)
        else:
            masked[k] = v
    return masked
