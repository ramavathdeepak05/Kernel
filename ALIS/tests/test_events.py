"""
Tests for ALIS Internal Event Bus (E02-S09)
"""

import pytest
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

from server.core.events import EventBus
from server.core.schema import Event
from server.core.audit import AuditLog, AuditAction

# Reset Bus before each test
@pytest.fixture(autouse=True)
def reset_bus():
    EventBus.clear_subscribers()
    yield
    EventBus.clear_subscribers()

def test_event_schema_validation():
    """Test that Event model validates correctly."""
    
    # Valid Event
    event = Event(
        id=str(uuid.uuid4()),
        type="test.event",
        source="test_module",
        payload={"key": "value"}
    )
    assert event.type == "test.event"
    
    # Missing required field (id)
    with pytest.raises(ValueError):
        Event(type="test.event", source="test", payload={})

def test_subscribe_and_publish():
    """Test basic pub/sub functionality."""
    handler = MagicMock()
    
    # Subscribe
    EventBus.subscribe("test.event", handler)
    
    # Publish
    event = Event(
        id=str(uuid.uuid4()),
        type="test.event",
        source="test_module",
        payload={"data": 123}
    )
    
    success = EventBus.publish(event)
    
    assert success is True
    handler.assert_called_once_with(event)

def test_audit_integration():
    """Test that publishing an event logs to AuditLog."""
    
    with patch.object(AuditLog, 'log') as mock_log:
        event = Event(
            id=str(uuid.uuid4()),
            type="audit.test",
            source="test",
            payload={}
        )
        
        EventBus.publish(event, actor_id="user_123")
        
        mock_log.assert_called_once()
        args, kwargs = mock_log.call_args
        
        assert kwargs['action'] == AuditAction.EVENT_PUBLISHED
        assert kwargs['entity_id'] == event.id
        assert kwargs['actor_id'] == "user_123"

def test_handler_error_isolation():
    """Test that one failing handler does not stop others."""
    
    bad_handler = MagicMock(side_effect=Exception("Crash!"))
    good_handler = MagicMock()
    
    EventBus.subscribe("test.error", bad_handler)
    EventBus.subscribe("test.error", good_handler)
    
    event = Event(
        id=str(uuid.uuid4()),
        type="test.error",
        source="test",
        payload={}
    )
    
    # Should not raise exception
    success = EventBus.publish(event)
    
    assert success is True
    bad_handler.assert_called_once()
    good_handler.assert_called_once()  # Should still run

def test_decorator_subscription():
    """Test the @listen decorator."""
    
    received_events = []
    
    @EventBus.listen("decorated.event")
    def my_handler(event):
        received_events.append(event)
        
    event = Event(
        id=str(uuid.uuid4()),
        type="decorated.event",
        source="test",
        payload={}
    )
    
    EventBus.publish(event)
    
    assert len(received_events) == 1
    assert received_events[0].id == event.id
