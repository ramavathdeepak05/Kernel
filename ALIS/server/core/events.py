"""
ALIS Internal Event Bus - E02-S09

MODULE: Shared Services
LAYER: Cross-cutting (Messaging)
ENTITY: EventBus

This module implements the internal event bus for cross-module signaling.
It provides a Publish/Subscribe mechanism that is:
1. In-process (No external message queue dependency)
2. Auditable (All events are logged to AuditLog)
3. Type-safe (Uses Event schema)

Must Align With:
- "No Cloud" Rule (No RabbitMQ/Redis)
- Event Contract Rule (Cross-module via events only)
- Layer 6 (Resilience - Error isolation)
"""

import logging
import uuid
from typing import Dict, List, Callable, Optional, Any
from datetime import datetime
from functools import wraps

from .schema import Event
from .audit import AuditLog, AuditAction

logger = logging.getLogger(__name__)

# Type definition for Event Handler
EventHandler = Callable[[Event], None]


class EventBus:
    """
    Singleton Internal Event Bus.
    
    Implements Observer pattern for intra-service communication.
    Persists events via AuditLog for durability/audit.
    """
    
    _instance = None
    _subscribers: Dict[str, List[EventHandler]] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EventBus, cls).__new__(cls)
            cls._subscribers = {}
        return cls._instance

    @classmethod
    def subscribe(cls, event_type: str, handler: EventHandler):
        """
        Register a handler for a specific event type.
        
        Args:
            event_type: The dot-notation event type string (e.g., 'm1.admissions.approved')
            handler: Callable that accepts an Event object
        """
        if event_type not in cls._subscribers:
            cls._subscribers[event_type] = []
        
        # Prevent duplicate registration
        if handler not in cls._subscribers[event_type]:
            cls._subscribers[event_type].append(handler)
            handler_name = getattr(handler, "__name__", str(handler))
            logger.info(f"Subscribed {handler_name} to {event_type}")

    @classmethod
    def publish(cls, event: Event, actor_id: str = "system") -> bool:
        """
        Publish an event to the bus.
        
        Process:
        1. Validate Event (Pydantic)
        2. Log to AuditLog (Persistence)
        3. Dispatch to Subscribers
        
        Args:
            event: The Event object
            actor_id: ID of the actor triggering the event (for audit)
            
        Returns:
            bool: True if published successfully
        """
        try:
            # 1. Validation is implicit via Pydantic model usage by caller, 
            # but we ensure it's a valid object here.
            if not isinstance(event, Event):
                logger.error(f"Invalid event object published: {type(event)}")
                return False

            # 2. Persistence / Audit
            # We log the event publication. This serves as our "Event Log".
            AuditLog.log(
                action=AuditAction.EVENT_PUBLISHED,
                actor_id=actor_id,
                actor_type="system", # The bus itself is the mechanism
                entity_type="event",
                entity_id=event.id,
                action_detail=f"Published {event.type}",
                metadata={
                    "event_type": event.type,
                    "source": event.source,
                    "correlation_id": event.correlation_id,
                    "payload_snapshot": str(event.payload)[:500] # Truncate for log safety
                }
            )
            
            # 3. Dispatch
            subscribers = cls._subscribers.get(event.type, [])
            
            # Also support wildcard subscriptions (simple implementation)
            # e.g., "m1.*" - unimplemented for now to keep it simple as per strict requirements,
            # but usually desirable. Sticking to exact match for E02-S09 MVP.
            
            if not subscribers:
                logger.debug(f"No subscribers for {event.type}")
                return True

            for handler in subscribers:
                try:
                    # Sync execution for now. 
                    # In future, this could be offloaded to a thread pool if needed.
                    handler(event)
                except Exception as e:
                    # Layer 6: Resilience - One handler failing must not crash the bus
                    handler_name = getattr(handler, "__name__", str(handler))
                    logger.error(f"Error in handler {handler_name} for {event.type}: {str(e)}")
                    # We continue to next handler
            
            return True

        except Exception as e:
            logger.critical(f"EventBus Critical Failure: {str(e)}")
            return False

    @staticmethod
    def listen(event_type: str):
        """Decorator to register a function as an event listener."""
        def decorator(func: EventHandler):
            EventBus.subscribe(event_type, func)
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
        return decorator

    @classmethod
    def clear_subscribers(cls):
        """Clear all subscribers (mostly for testing)."""
        cls._subscribers = {}
