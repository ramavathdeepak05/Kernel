import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import unittest
from datetime import datetime, timedelta
from ALIS.server.core.models import TaskStatus, TaskPriority
from ALIS.server.core.schema import TaskCreate, TaskUpdate
from ALIS.server.core.tasks import TaskService
from ALIS.server.core.rbac import Role
from ALIS.server.core.notifications.service import get_dispatcher, NotificationStatus
# Mock Dispatcher for testing
class MockDispatcher:
    def __init__(self):
        self.sent_messages = []
        
    def send(self, template_id, recipient_id, recipient_address, context, channels=None, org_id=None):
        self.sent_messages.append({
            "template_id": template_id,
            "recipient_id": recipient_id,
            "context": context
        })
        return [] # Return empty list of logs

# Patch the dispatcher
import ALIS.server.core.tasks
import ALIS.server.core.notifications.service
ALIS.server.core.notifications.service._dispatcher = MockDispatcher()


class TestTaskEngine(unittest.TestCase):
    
    def setUp(self):
        self.service = TaskService
        # Clear in-memory storage
        self.service._tasks = {}
        # Reset mock dispatcher
        ALIS.server.core.notifications.service._dispatcher = MockDispatcher()
        self.mock_dispatcher = ALIS.server.core.notifications.service._dispatcher

    def test_lifecycle(self):
        """Test basic task lifecycle: Create -> Complete"""
        # Create
        task_in = TaskCreate(
            title="Test Task",
            description="Do this now",
            priority=TaskPriority.HIGH,
            assignee_id="user-123"
        )
        task = self.service.create_task(task_in, created_by="admin")
        
        self.assertEqual(task.status, TaskStatus.PENDING)
        self.assertEqual(task.title, "Test Task")
        self.assertEqual(task.assignee_id, "user-123")
        
        # Verify notification sent on creation
        self.assertEqual(len(self.mock_dispatcher.sent_messages), 1)
        self.assertEqual(self.mock_dispatcher.sent_messages[0]['template_id'], "task_assigned")
        
        # Complete
        completed_task = self.service.complete_task(task.id, user_id="user-123")
        self.assertEqual(completed_task.status, TaskStatus.COMPLETED)
        self.assertIsNotNone(completed_task.completed_at)
        
        # Verify state in service
        fetched_task = self.service.get_task(task.id)
        self.assertEqual(fetched_task.status, TaskStatus.COMPLETED)

    def test_role_assignment(self):
        """Test assignment to a Role (Shared Worklist)"""
        task_in = TaskCreate(
            title="Faculty Task",
            assignee_role=Role.FACULTY.value
        )
        task = self.service.create_task(task_in, created_by="system")
        
        self.assertEqual(task.assignee_role, Role.FACULTY.value)
        self.assertIsNone(task.assignee_id)
        
        # Check visibility
        # 1. Faculty user should see it
        tasks_faculty = self.service.get_tasks_for_user("fac-1", Role.FACULTY)
        self.assertIn(task, tasks_faculty)
        
        # 2. Student user should NOT see it
        tasks_student = self.service.get_tasks_for_user("stu-1", Role.STUDENT)
        self.assertNotIn(task, tasks_student)

    def test_reminders(self):
        """Test reminder generation for due tasks"""
        # Create task due in 2 hours
        due_soon = datetime.utcnow() + timedelta(hours=2)
        task_in = TaskCreate(
            title="Urgent Task",
            assignee_id="user-123",
            due_date=due_soon
        )
        task = self.service.create_task(task_in, created_by="system")
        
        # Clear creation notification
        self.mock_dispatcher.sent_messages = []
        
        # Process reminders
        count = self.service.process_reminders()
        
        self.assertEqual(count, 1)
        self.assertTrue(task.reminder_sent)
        
        # Verify reminder notification
        self.assertEqual(len(self.mock_dispatcher.sent_messages), 1)
        self.assertEqual(self.mock_dispatcher.sent_messages[0]['template_id'], "task_due_soon")
        
        # Run again - should not send duplicate
        count_retry = self.service.process_reminders()
        self.assertEqual(count_retry, 0)
        self.assertEqual(len(self.mock_dispatcher.sent_messages), 1)

    def test_validation(self):
        """Test validation rules"""
        # Fail if no assignee
        with self.assertRaises(ValueError):
            self.service.create_task(
                TaskCreate(title="Bad Task"), 
                created_by="system"
            )
            
        # Fail if invalid role
        with self.assertRaises(ValueError):
            self.service.create_task(
                TaskCreate(title="Bad Role", assignee_role="invalid_role"), 
                created_by="system"
            )

    def test_permission_complete(self):
        """Test that only assigned user can complete"""
        task_in = TaskCreate(
            title="My Task",
            assignee_id="user-A"
        )
        task = self.service.create_task(task_in, created_by="system")
        
        # User B tries to complete
        with self.assertRaises(ValueError):
            self.service.complete_task(task.id, user_id="user-B")
            
        # User A succeeds
        self.service.complete_task(task.id, user_id="user-A")


if __name__ == "__main__":
    unittest.main()
