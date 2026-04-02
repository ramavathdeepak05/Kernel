"""
LMS Sync Celery Tasks — REPLACED BY IN-HOUSE LMS (P40)

Moodle grade sync is no longer needed. ALIS now manages assignments,
submissions, and grades natively via:
  - server.academics.learning_service (AssignmentService, SubmissionService)
  - server.tasks.learning_tasks (close_overdue_assignments beat task)
  - server.api.learning_router

The beat entry "lms-grade-sync" was removed from worker.py in P40.
This module is retained as a tombstone to preserve import stability.
"""
from __future__ import annotations
