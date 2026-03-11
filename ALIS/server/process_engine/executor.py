"""E13-S02 — Step Executor Engine.

Executes one step at a time for a running process instance.
Each step type has a dedicated handler; the executor advances the
instance's current_step pointer and writes step logs.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Safe expression evaluator (CONDITION steps)
# ---------------------------------------------------------------------------

_SAFE_NAMES: Dict[str, Any] = {
    "True": True, "False": False, "None": None,
    "abs": abs, "min": min, "max": max, "len": len, "round": round,
    "int": int, "float": float, "str": str, "bool": bool,
}


def _safe_eval(expression: str, context: Dict[str, Any]) -> bool:
    """Evaluate a simple boolean expression against a context dict.

    Only dot-access paths like ``context.cgpa >= 7.0`` are supported.
    No builtins other than the whitelist above are exposed.
    """
    # Replace context.x.y.z references with nested dict access
    def _resolve(match: re.Match) -> str:
        path = match.group(1).split(".")
        obj: Any = context
        for key in path:
            if isinstance(obj, dict):
                obj = obj.get(key)
            else:
                obj = None
        return repr(obj)

    expanded = re.sub(r"context\.([a-zA-Z0-9_.]+)", _resolve, expression)
    try:
        result = eval(expanded, {"__builtins__": {}}, _SAFE_NAMES)  # noqa: S307
        return bool(result)
    except Exception as exc:
        logger.warning("CONDITION eval failed (%s): %s", expression, exc)
        return False


# ---------------------------------------------------------------------------
# Step executor
# ---------------------------------------------------------------------------

class StepExecutor:
    """Execute a single step within a process instance."""

    def __init__(self, org_id: str, instance_id: str):
        self.org_id = org_id
        self.instance_id = instance_id

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute_current_step(self) -> Dict[str, Any]:
        """Load the current instance + step, execute, return result dict."""
        instance = self._load_instance()
        if not instance:
            return {"status": "ERROR", "message": "Instance not found"}

        if instance["status"] != "RUNNING":
            return {"status": instance["status"], "message": "Instance is not running"}

        step = self._load_step(instance["process_id"], instance["current_step"])
        if not step:
            # No more steps — process is complete
            self._complete_instance(instance)
            return {"status": "COMPLETED", "message": "All steps executed"}

        return self._dispatch(instance, step)

    # ------------------------------------------------------------------
    # Step dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, instance: Dict, step: Dict) -> Dict[str, Any]:
        step_type = step["step_type"]
        log_id = self._start_step_log(instance, step)

        try:
            handler = {
                "FORM":          self._handle_form,
                "APPROVAL":      self._handle_approval,
                "CONDITION":     self._handle_condition,
                "NOTIFICATION":  self._handle_notification,
                "AI_EVALUATION": self._handle_ai_evaluation,
                "AUTO_ACTION":   self._handle_auto_action,
            }.get(step_type)

            if not handler:
                raise ValueError(f"Unknown step type: {step_type}")

            result = handler(instance, step)
            self._finish_step_log(log_id, result["status"], output=result.get("output", {}))

            if result["status"] == "PASSED":
                self._advance(instance, step, passed=True)
            elif result["status"] == "FAILED":
                if not step["is_required"]:
                    self._advance(instance, step, passed=False)
                else:
                    self._fail_instance(instance, result.get("message", "Step failed"))
            # PENDING means step is waiting for external input (e.g. FORM or APPROVAL)

        except Exception as exc:
            logger.exception("StepExecutor error on instance %s step %s", self.instance_id, step["step_order"])
            self._finish_step_log(log_id, "FAILED", error=str(exc))
            self._fail_instance(instance, str(exc))
            return {"status": "FAILED", "message": str(exc)}

        return result

    # ------------------------------------------------------------------
    # Step handlers
    # ------------------------------------------------------------------

    def _handle_form(self, instance: Dict, step: Dict) -> Dict[str, Any]:
        """FORM steps pause execution and wait for user submission."""
        # Check if form was already submitted (submission stored in process_form_submissions)
        rows = execute_query(
            "SELECT * FROM process_form_submissions WHERE instance_id = %s AND step_id = %s",
            (self.instance_id, step["id"]),
        )
        if rows:
            # Already submitted — merge form_data into context and pass
            submission = rows[0]
            form_data = submission["form_data"] if isinstance(submission["form_data"], dict) else json.loads(submission["form_data"])
            self._merge_context(instance, form_data)
            return {"status": "PASSED", "output": {"form_data": form_data}}

        # Not yet submitted — mark step as PENDING, return form schema
        config = step["config"] if isinstance(step["config"], dict) else json.loads(step["config"])
        return {
            "status": "PENDING",
            "action_required": "FORM_SUBMISSION",
            "form_schema": config.get("fields", []),
            "step_id": str(step["id"]),
        }

    def _handle_approval(self, instance: Dict, step: Dict) -> Dict[str, Any]:
        """APPROVAL steps check the approval_requests table for a quorum decision."""
        from server.approvals.service import ApprovalService  # type: ignore

        config = step["config"] if isinstance(step["config"], dict) else json.loads(step["config"])
        quorum = config.get("quorum", 1)

        # Query approval requests linked to this step via entity_id = instance_id, entity_type = step_id
        rows = execute_query(
            """
            SELECT status FROM approval_requests
            WHERE entity_type = 'process_step'
              AND entity_id = %s
              AND org_id = %s
            """,
            (str(step["id"]) + ":" + self.instance_id, self.org_id),
        )
        approved = sum(1 for r in rows if r["status"] == "APPROVED")
        rejected = sum(1 for r in rows if r["status"] == "REJECTED")

        if approved >= quorum:
            return {"status": "PASSED", "output": {"approvals": approved}}
        if rejected > 0:
            return {"status": "FAILED", "message": "Approval rejected"}

        # Still pending
        return {
            "status": "PENDING",
            "action_required": "APPROVAL",
            "approvals_needed": quorum - approved,
            "step_id": str(step["id"]),
        }

    def _handle_condition(self, instance: Dict, step: Dict) -> Dict[str, Any]:
        """CONDITION steps evaluate an expression against the runtime context."""
        config = step["config"] if isinstance(step["config"], dict) else json.loads(step["config"])
        expression = config.get("expression", "True")
        context = instance["context"] if isinstance(instance["context"], dict) else json.loads(instance["context"])

        passed = _safe_eval(expression, context)
        label = config.get("pass_label" if passed else "fail_label", "")
        return {
            "status": "PASSED" if passed else "FAILED",
            "output": {"result": passed, "label": label, "expression": expression},
        }

    def _handle_notification(self, instance: Dict, step: Dict) -> Dict[str, Any]:
        """NOTIFICATION steps dispatch a notification and continue."""
        config = step["config"] if isinstance(step["config"], dict) else json.loads(step["config"])
        context = instance["context"] if isinstance(instance["context"], dict) else json.loads(instance["context"])

        template_key = config.get("template_key", "")
        recipient_field = config.get("recipient_field", "")
        channel = config.get("channel", "EMAIL")

        # Resolve recipient from context using dot-path
        recipient = context
        for key in recipient_field.replace("context.", "").split("."):
            if isinstance(recipient, dict):
                recipient = recipient.get(key, "")
            else:
                recipient = ""

        try:
            from server.core.notifications.service import NotificationDispatcher
            NotificationDispatcher.dispatch(
                template_key=template_key,
                recipient_id=str(instance.get("triggered_by", "system")),
                recipient_email=str(recipient),
                context=context,
                org_id=self.org_id,
                channel=channel,
            )
        except Exception as exc:
            logger.warning("NOTIFICATION step dispatch failed: %s", exc)

        return {"status": "PASSED", "output": {"template_key": template_key, "recipient": recipient}}

    def _handle_ai_evaluation(self, instance: Dict, step: Dict) -> Dict[str, Any]:
        """AI_EVALUATION steps call the AI Gateway and write result to context."""
        config = step["config"] if isinstance(step["config"], dict) else json.loads(step["config"])
        context = instance["context"] if isinstance(instance["context"], dict) else json.loads(instance["context"])

        prompt_template = config.get("prompt_template", "")
        output_field = config.get("output_field", "ai_result")
        pass_condition = config.get("pass_condition", "")

        # Interpolate context into prompt
        prompt = re.sub(
            r"\$\{context\}",
            json.dumps(context, default=str),
            prompt_template,
        )

        try:
            from server.core.ai_gateway import AIGateway
            from server.core.model_registry import ModelRegistry
            gateway = AIGateway(ModelRegistry())
            response = gateway.generate(
                prompt=prompt,
                system="You are an academic evaluation assistant. Respond with JSON only.",
                org_id=self.org_id,
                purpose="process_engine_ai_evaluation",
            )
            ai_output = response.get("text", "")
            # Try to parse as JSON
            try:
                ai_result = json.loads(ai_output)
            except json.JSONDecodeError:
                ai_result = {"raw": ai_output}

            # Write to context
            context[output_field] = ai_result
            self._merge_context(instance, {output_field: ai_result})

            # Evaluate pass_condition
            passed = _safe_eval(pass_condition, context) if pass_condition else True
            return {
                "status": "PASSED" if passed else "FAILED",
                "output": {output_field: ai_result},
            }
        except Exception as exc:
            logger.exception("AI_EVALUATION step failed: %s", exc)
            return {"status": "FAILED", "message": str(exc)}

    def _handle_auto_action(self, instance: Dict, step: Dict) -> Dict[str, Any]:
        """AUTO_ACTION steps invoke a registered action function."""
        config = step["config"] if isinstance(step["config"], dict) else json.loads(step["config"])
        context = instance["context"] if isinstance(instance["context"], dict) else json.loads(instance["context"])

        action_name = config.get("action", "")
        static_params = config.get("params", {})
        merged_params = {**context, **static_params}

        try:
            from server.process_engine.actions import ActionRegistry
            result = ActionRegistry.execute(action_name, merged_params, self.org_id)
            return {"status": "PASSED", "output": result or {}}
        except Exception as exc:
            logger.exception("AUTO_ACTION '%s' failed: %s", action_name, exc)
            return {"status": "FAILED", "message": str(exc)}

    # ------------------------------------------------------------------
    # Instance / step management helpers
    # ------------------------------------------------------------------

    def _load_instance(self) -> Optional[Dict]:
        rows = execute_query(
            "SELECT * FROM process_instances WHERE id = %s AND org_id = %s",
            (self.instance_id, self.org_id),
        )
        return dict(rows[0]) if rows else None

    def _load_step(self, process_id: str, step_order: int) -> Optional[Dict]:
        rows = execute_query(
            "SELECT * FROM process_steps WHERE process_id = %s AND step_order = %s AND org_id = %s",
            (process_id, step_order, self.org_id),
        )
        return dict(rows[0]) if rows else None

    def _start_step_log(self, instance: Dict, step: Dict) -> str:
        rows = execute_query(
            """
            INSERT INTO process_step_logs
                (org_id, instance_id, step_id, step_order, step_type, status)
            VALUES (%s, %s, %s, %s, %s, 'RUNNING')
            RETURNING id
            """,
            (self.org_id, self.instance_id, step["id"], step["step_order"], step["step_type"]),
        )
        return str(rows[0]["id"])

    def _finish_step_log(
        self, log_id: str, status: str,
        output: Optional[Dict] = None,
        error: Optional[str] = None,
    ) -> None:
        execute_transaction([(
            """
            UPDATE process_step_logs
               SET status = %s,
                   output_data = %s::jsonb,
                   error_message = %s,
                   completed_at = NOW()
             WHERE id = %s
            """,
            (status, json.dumps(output or {}), error, log_id),
        )])

    def _advance(self, instance: Dict, step: Dict, passed: bool) -> None:
        config = step["config"] if isinstance(step["config"], dict) else json.loads(step.get("config", "{}"))
        on_pass = step.get("on_pass_step")
        on_fail = step.get("on_fail_step")

        next_step: Optional[int] = on_pass if passed else on_fail

        if next_step is None:
            # No explicit routing — just increment
            next_step = step["step_order"] + 1

        # Check if next step exists
        rows = execute_query(
            "SELECT id FROM process_steps WHERE process_id = %s AND step_order = %s AND org_id = %s",
            (instance["process_id"], next_step, self.org_id),
        )
        if rows:
            execute_transaction([(
                "UPDATE process_instances SET current_step = %s WHERE id = %s",
                (next_step, self.instance_id),
            )])
        else:
            self._complete_instance(instance)

    def _complete_instance(self, instance: Dict) -> None:
        execute_transaction([(
            """
            UPDATE process_instances
               SET status = 'COMPLETED', completed_at = NOW()
             WHERE id = %s
            """,
            (self.instance_id,),
        )])

    def _fail_instance(self, instance: Dict, message: str) -> None:
        execute_transaction([(
            """
            UPDATE process_instances
               SET status = 'FAILED', error_message = %s, completed_at = NOW()
             WHERE id = %s
            """,
            (message, self.instance_id),
        )])

    def _merge_context(self, instance: Dict, new_data: Dict[str, Any]) -> None:
        current = instance["context"] if isinstance(instance["context"], dict) else json.loads(instance.get("context", "{}"))
        current.update(new_data)
        execute_transaction([(
            "UPDATE process_instances SET context = %s::jsonb WHERE id = %s",
            (json.dumps(current), self.instance_id),
        )])
        instance["context"] = current
