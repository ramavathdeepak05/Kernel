"""E13 — Dynamic Process Engine API Router.

Endpoints:
  Process Definitions:
    POST   /api/v1/processes/                          create definition
    GET    /api/v1/processes/                          list definitions
    GET    /api/v1/processes/{process_id}              get definition
    PATCH  /api/v1/processes/{process_id}              update definition
    DELETE /api/v1/processes/{process_id}              deactivate definition

  Process Instances:
    POST   /api/v1/processes/{process_id}/launch       launch an instance
    GET    /api/v1/processes/instances                 list instances
    GET    /api/v1/processes/instances/{instance_id}   get instance
    POST   /api/v1/processes/instances/{instance_id}/cancel
    POST   /api/v1/processes/instances/{instance_id}/resume
    POST   /api/v1/processes/instances/{instance_id}/steps/{step_id}/submit  submit form

  Forms:
    GET    /api/v1/processes/instances/{instance_id}/form  get pending form schema

  Admin:
    GET    /api/v1/processes/actions                   list registered AUTO_ACTION names
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from server.core.rbac import require_permission
from server.process_engine.models import (
    ProcessDefinitionCreate,
    ProcessDefinitionUpdate,
    ProcessLaunchRequest,
    FormSubmission,
)

router = APIRouter(prefix="/api/v1/processes", tags=["Process Engine (E13)"])


# ---------------------------------------------------------------------------
# Process Definitions
# ---------------------------------------------------------------------------

@router.post("/", status_code=201)
def create_definition(
    body: ProcessDefinitionCreate,
    ctx=Depends(require_permission("process:manage")),
):
    from server.process_engine.definition import ProcessDefinitionService
    return ProcessDefinitionService.create(
        org_id=ctx["org_id"],
        created_by=ctx["user_id"],
        data=body.model_dump(),
    )


@router.get("/")
def list_definitions(
    active_only: bool = True,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    ctx=Depends(require_permission("process:read")),
):
    from server.process_engine.definition import ProcessDefinitionService
    return ProcessDefinitionService.list(
        org_id=ctx["org_id"],
        active_only=active_only,
        limit=limit,
        offset=offset,
    )


@router.get("/actions")
def list_actions(ctx=Depends(require_permission("process:manage"))):
    from server.process_engine.actions import ActionRegistry
    return {"actions": ActionRegistry.list_actions()}


@router.get("/instances")
def list_instances(
    process_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    ctx=Depends(require_permission("process:read")),
):
    from server.process_engine.instance import ProcessInstanceService
    return ProcessInstanceService.list(
        org_id=ctx["org_id"],
        process_id=process_id,
        entity_type=entity_type,
        entity_id=entity_id,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/instances/{instance_id}")
def get_instance(
    instance_id: str,
    ctx=Depends(require_permission("process:read")),
):
    from server.process_engine.instance import ProcessInstanceService
    instance = ProcessInstanceService.get(ctx["org_id"], instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    return instance


@router.post("/instances/{instance_id}/cancel")
def cancel_instance(
    instance_id: str,
    ctx=Depends(require_permission("process:manage")),
):
    from server.process_engine.instance import ProcessInstanceService
    ProcessInstanceService.cancel(ctx["org_id"], instance_id)
    return {"status": "cancelled", "instance_id": instance_id}


@router.post("/instances/{instance_id}/resume")
def resume_instance(
    instance_id: str,
    ctx=Depends(require_permission("process:manage")),
):
    from server.process_engine.instance import ProcessInstanceService
    return ProcessInstanceService.resume(ctx["org_id"], instance_id)


@router.get("/instances/{instance_id}/form")
def get_pending_form(
    instance_id: str,
    ctx=Depends(require_permission("process:read")),
):
    from server.process_engine.forms import FormRenderer
    form = FormRenderer.get_pending_form(ctx["org_id"], instance_id)
    if not form:
        raise HTTPException(status_code=404, detail="No pending form for this instance")
    return form


@router.post("/instances/{instance_id}/steps/{step_id}/submit")
def submit_form(
    instance_id: str,
    step_id: str,
    body: FormSubmission,
    ctx=Depends(require_permission("process:read")),
):
    from server.process_engine.forms import FormRenderer
    from server.process_engine.instance import ProcessInstanceService
    from server.db_service import execute_query

    # Load step config for validation
    rows = execute_query(
        "SELECT config FROM process_steps WHERE id = %s AND org_id = %s",
        (step_id, ctx["org_id"]),
    )
    if rows:
        import json
        config = rows[0]["config"] if isinstance(rows[0]["config"], dict) else json.loads(rows[0]["config"] or "{}")
        fields = config.get("fields", [])
        errors = FormRenderer.validate_submission(fields, body.form_data)
        if errors:
            raise HTTPException(status_code=422, detail={"validation_errors": errors})

    return ProcessInstanceService.submit_form(
        org_id=ctx["org_id"],
        instance_id=instance_id,
        step_id=step_id,
        submitted_by=ctx["user_id"],
        form_data=body.form_data,
    )


@router.get("/{process_id}")
def get_definition(
    process_id: str,
    ctx=Depends(require_permission("process:read")),
):
    from server.process_engine.definition import ProcessDefinitionService
    defn = ProcessDefinitionService.get(ctx["org_id"], process_id)
    if not defn:
        raise HTTPException(status_code=404, detail="Process definition not found")
    return defn


@router.patch("/{process_id}")
def update_definition(
    process_id: str,
    body: ProcessDefinitionUpdate,
    ctx=Depends(require_permission("process:manage")),
):
    from server.process_engine.definition import ProcessDefinitionService
    return ProcessDefinitionService.update(
        org_id=ctx["org_id"],
        process_id=process_id,
        data=body.model_dump(exclude_none=True),
    )


@router.delete("/{process_id}", status_code=204, response_model=None)
def delete_definition(
    process_id: str,
    ctx=Depends(require_permission("process:manage")),
):
    from server.process_engine.definition import ProcessDefinitionService
    ProcessDefinitionService.delete(ctx["org_id"], process_id)


@router.post("/{process_id}/launch", status_code=201)
def launch_process(
    process_id: str,
    body: ProcessLaunchRequest,
    ctx=Depends(require_permission("process:manage")),
):
    from server.process_engine.instance import ProcessInstanceService
    return ProcessInstanceService.launch(
        org_id=ctx["org_id"],
        process_id=process_id,
        triggered_by=ctx["user_id"],
        context=body.context,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
    )
