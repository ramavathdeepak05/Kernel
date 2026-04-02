"""
Per-Tenant Celery Task Routing — S5

Every tenant gets its own Celery queue so noisy tenants cannot starve
others. The routing convention is:

    default queue:       default:{tenant_id}
    high_priority queue: high:{tenant_id}
    dead_letter queue:   dead_letter  (shared — DLQ is ops-level)

Workers subscribe to per-tenant queues at startup, or use a wildcard
pattern via Kombu (RabbitMQ) / Redis sorted-set routing (Redis Streams).

For Redis broker (current setup) we use named queues and the Celery
`apply_async(queue=...)` API. Workers are either:

  A) Per-tenant workers (production):
       celery -A server.worker worker -Q "default:{tenant_id},high:{tenant_id}"

  B) Shared workers with ALL queues (dev / small deploy):
       celery -A server.worker worker -Q "default:*" --queues-regex

The TenantTaskRouter is registered in celery_app.conf.task_routes
so all `delay()` / `apply_async()` calls are automatically routed to the
correct queue when `tenant_id` is present in kwargs.

Usage in task code:
    from server.core.tenant_tasks import apply_tenant_task

    apply_tenant_task(
        "server.tasks.ai_tasks.verify_document_async",
        tenant_id=org_id,
        args=[org_id, application_id, document_id],
        priority="default",   # or "high"
    )
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Literal, Optional

logger = logging.getLogger(__name__)

PriorityType = Literal["default", "high"]


# ---------------------------------------------------------------------------
# Queue naming
# ---------------------------------------------------------------------------

def tenant_queue(tenant_id: str, priority: PriorityType = "default") -> str:
    """Return the queue name for a tenant + priority combination."""
    return f"{priority}:{tenant_id}"


def parse_tenant_from_queue(queue_name: str) -> Optional[str]:
    """Extract tenant_id from a queue name, or None if not a tenant queue."""
    parts = queue_name.split(":", 1)
    if len(parts) == 2 and parts[0] in ("default", "high"):
        return parts[1]
    return None


# ---------------------------------------------------------------------------
# Celery router
# ---------------------------------------------------------------------------

class TenantTaskRouter:
    """
    Celery task router.

    Routes tasks to per-tenant queues when `tenant_id` is in kwargs.
    Falls back to the shared `default` / `high_priority` queue for
    system-level tasks (beat tasks, DLQ retries) that have no tenant context.

    Register in celery_app.conf:
        task_routes = (TenantTaskRouter(),)
    """

    # Tasks that should always run on the shared queue (tenant-agnostic)
    SYSTEM_TASKS = frozenset({
        "server.tasks.calendar",
        "server.tasks.shadow_divergence",
        "server.tasks.backup",
        "server.tasks.reporting",
    })

    def route_for_task(
        self,
        task: str,
        args: tuple = (),
        kwargs: Dict[str, Any] = {},
        options: Dict[str, Any] = {},
        **kw: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Return routing dict or None (fall back to task_default_queue).

        Priority is determined by:
          1. Explicit `priority` kwarg on the task call
          2. Task prefix match to HIGH_PRIORITY_PREFIXES
          3. Default: "default"
        """
        # Never route system tasks to tenant queues
        for prefix in self.SYSTEM_TASKS:
            if task.startswith(prefix):
                return None  # use default queue

        # Extract tenant_id from task kwargs (first positional arg is usually org_id)
        tenant_id = kwargs.get("tenant_id") or kwargs.get("org_id")
        if not tenant_id and args:
            # Convention: first positional arg is org_id for most tasks
            tenant_id = args[0] if isinstance(args[0], str) and len(args[0]) == 36 else None

        if not tenant_id:
            return None  # no tenant context → shared queue

        # High-priority tasks get the "high" prefix
        priority: PriorityType = "high" if self._is_high_priority(task) else "default"

        return {"queue": tenant_queue(tenant_id, priority)}

    HIGH_PRIORITY_PREFIXES = frozenset({
        "server.tasks.notifications",   # user-facing notifications → fast delivery
        "server.tasks.admissions.send_offer",
    })

    def _is_high_priority(self, task_name: str) -> bool:
        for prefix in self.HIGH_PRIORITY_PREFIXES:
            if task_name.startswith(prefix):
                return True
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_tenant_task(
    task_name: str,
    tenant_id: str,
    args: Optional[list] = None,
    kwargs: Optional[dict] = None,
    priority: PriorityType = "default",
    countdown: Optional[int] = None,
    eta: Optional[Any] = None,
    retries: int = 3,
) -> Any:
    """
    Enqueue a task on the correct per-tenant queue.

    This is the preferred way to dispatch Celery tasks within the ALIS
    data plane — it ensures tenant isolation at the queue level.

    Args:
        task_name:  Dotted task path, e.g. "server.tasks.ai_tasks.verify_document_async"
        tenant_id:  Tenant UUID string
        args:       Positional task arguments
        kwargs:     Keyword task arguments (tenant_id injected automatically)
        priority:   "default" or "high"
        countdown:  Delay in seconds before execution
        eta:        Absolute datetime for execution
        retries:    Max retry count override

    Returns:
        AsyncResult from celery_app.send_task()
    """
    from server.worker import celery_app

    task_kwargs = dict(kwargs or {})
    task_kwargs.setdefault("tenant_id", tenant_id)

    queue = tenant_queue(tenant_id, priority)

    send_kwargs: Dict[str, Any] = {
        "queue": queue,
        "kwargs": task_kwargs,
        "retries": retries,
    }
    if args:
        send_kwargs["args"] = args
    if countdown is not None:
        send_kwargs["countdown"] = countdown
    if eta is not None:
        send_kwargs["eta"] = eta

    logger.debug(
        "Dispatching task=%s tenant=%s queue=%s", task_name, tenant_id, queue
    )
    return celery_app.send_task(task_name, **send_kwargs)


def ensure_tenant_queues(tenant_id: str) -> list[str]:
    """
    Return the list of queue names for a tenant.

    In production these are pre-declared at worker startup. This helper
    is used by the provisioner to log/register the expected queues.
    """
    return [
        tenant_queue(tenant_id, "default"),
        tenant_queue(tenant_id, "high"),
    ]
