"""
ALIS Notifications Package - E02-S03

Centralized notification infrastructure for all ALIS modules.
"""
from __future__ import annotations

from .channels import (
    BaseChannel,
    EmailChannel,
    SMSChannel,
    WhatsAppChannel,
    ChannelResult,
    get_channel,
)
from .templates import (
    NotificationTemplate,
    TemplateRegistry,
)
from .service import (
    NotificationDispatcher,
    NotificationError,
    get_dispatcher,
)
# Re-export from models for convenience
from ..models import NotificationChannel, NotificationStatus

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
