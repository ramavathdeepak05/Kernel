# HITLPort adapters — webhook, email, slack, inapp
from adapters.hitl.email import EmailHITLAdapter
from adapters.hitl.teams import MicrosoftTeamsHITLAdapter
from adapters.hitl.webhook import WebhookHITLAdapter

__all__ = ["EmailHITLAdapter", "MicrosoftTeamsHITLAdapter", "WebhookHITLAdapter"]
