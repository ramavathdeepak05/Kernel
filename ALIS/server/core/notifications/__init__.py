"""
ALIS Notifications Package - E02-S03

Centralized notification infrastructure for all ALIS modules.
"""

from __future__ import annotations

# Re-export from models for convenience
from ..models import NotificationChannel, NotificationStatus
from .channels import (
    BaseChannel,
    ChannelResult,
    EmailChannel,
    SMSChannel,
    WhatsAppChannel,
    get_channel,
)
from .service import (
    NotificationDispatcher,
    NotificationError,
    get_dispatcher,
)
from .templates import (
    NotificationTemplate,
    TemplateRegistry,
)

__all__ = [
    # Channels
    "BaseChannel",
    "EmailChannel",
    "SMSChannel",
    "WhatsAppChannel",
    "ChannelResult",
    "get_channel",
    # Templates
    "NotificationTemplate",
    "TemplateRegistry",
    # Service
    "NotificationDispatcher",
    "NotificationError",
    "get_dispatcher",
    # Enums (from models)
    "NotificationChannel",
    "NotificationStatus",
]
