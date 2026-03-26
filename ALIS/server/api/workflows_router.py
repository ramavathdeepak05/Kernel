"""
ALIS Workflows Router - E02-S01: Workflow Engine Monitoring Router

MODULE: Shared Services
LAYER: Orchestration (FastAPI)

Exposes the Workflow Engine's monitoring endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from typing import List, Dict, Any, Optional
import json

from server.db_service import execute_query
from server.core.rbac import require_permission, Permission
from server.core.security import get_current_tenant_id

router = APIRouter(prefix="/api/v1/workflows", tags=["Workflows"])

@router.get("/")
@require_permission(Permission.SYSTEM_READ)
async def list_workflows(
    request: Request,
    workflow_type: Optional[str] = Query(None, description="Filter by workflow type"),
    current_state: Optional[str] = Query(None, description="Filter by state"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
) -> List[Dict[str, Any]]:
    """
    List workflow instances for the current tenant.
    
    Access:
        Requires `system:read` permission.
    """
    tenant_id = get_current_tenant_id()
    
    conditions = ["tenant_id = %s"]
    params = [tenant_id]
    
    if workflow_type:
        conditions.append("workflow_type = %s")
        params.append(workflow_type)
        
    if current_state:
        conditions.append("current_state = %s")
        params.append(current_state)
        
    where = " AND ".join(conditions)
    
    sql = f"""
        SELECT id, tenant_id, workflow_type, current_state,
               context, decision, approver_roles,
               created_at, updated_at, completed_at
        FROM workflow_instances
        WHERE {where}
        ORDER BY updated_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    
    rows = execute_query(sql, tuple(params))
    
    # Process jsonb fields if they come back as strings
    for row in rows:
        for field in ["context", "decision", "approver_roles"]:
            if isinstance(row.get(field), str):
                try:
                    row[field] = json.loads(row[field])
                except Exception:
                    pass
                    
    return rows

@router.get("/{workflow_id}")
@require_permission(Permission.SYSTEM_READ)
async def get_workflow(
    request: Request,
    workflow_id: str
) -> Dict[str, Any]:
    """
    Get workflow instance details including step history.
    
    Access:
        Requires `system:read` permission.
    """
    tenant_id = get_current_tenant_id()
    
    rows = execute_query(
        "SELECT * FROM workflow_instances WHERE id = %s AND tenant_id = %s",
        (workflow_id, tenant_id)
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Workflow not found")
        
    instance = dict(rows[0])
    
    # Process jsonb fields
    for field in ["context", "decision", "approver_roles"]:
        if isinstance(instance.get(field), str):
            try:
                instance[field] = json.loads(instance[field])
            except Exception:
                pass
                
    steps = execute_query(
        "SELECT * FROM workflow_steps WHERE workflow_id = %s AND tenant_id = %s ORDER BY id ASC",
        (workflow_id, tenant_id)
    )
    
    for step in steps:
        if isinstance(step.get("data"), str):
            try:
                step["data"] = json.loads(step["data"])
            except Exception:
                pass
    
    instance["step_history"] = steps
    return instance
