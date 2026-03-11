"""E13-S04 — Dynamic form renderer.

Returns the form schema for a pending FORM step so the frontend can
render it without any hardcoded knowledge of the field structure.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from server.db_service import execute_query


class FormRenderer:

    @staticmethod
    def get_pending_form(org_id: str, instance_id: str) -> Optional[Dict[str, Any]]:
        """Return form schema for the current pending FORM step, or None."""
        rows = execute_query(
            """
            SELECT pi.current_step, pi.process_id, ps.id as step_id,
                   ps.name, ps.config
              FROM process_instances pi
              JOIN process_steps ps
                ON ps.process_id = pi.process_id
               AND ps.step_order = pi.current_step
               AND ps.org_id = pi.org_id
             WHERE pi.id = %s AND pi.org_id = %s
               AND pi.status = 'RUNNING'
               AND ps.step_type = 'FORM'
            """,
            (instance_id, org_id),
        )
        if not rows:
            return None

        row = rows[0]
        config = row["config"] if isinstance(row["config"], dict) else json.loads(row["config"] or "{}")

        return {
            "step_id": str(row["step_id"]),
            "step_name": row["name"],
            "fields": config.get("fields", []),
        }

    @staticmethod
    def validate_submission(fields: List[Dict[str, Any]], form_data: Dict[str, Any]) -> List[str]:
        """Validate form_data against declared field schema. Returns list of error messages."""
        errors: List[str] = []
        for field in fields:
            name = field.get("name", "")
            required = field.get("required", True)
            value = form_data.get(name)

            if required and (value is None or value == ""):
                errors.append(f"Field '{name}' is required")
                continue

            if value is None:
                continue

            field_type = field.get("type", "text")
            validation = field.get("validation", {})

            if field_type == "number":
                try:
                    num = float(value)
                    if "min" in validation and num < validation["min"]:
                        errors.append(f"Field '{name}' must be >= {validation['min']}")
                    if "max" in validation and num > validation["max"]:
                        errors.append(f"Field '{name}' must be <= {validation['max']}")
                except (TypeError, ValueError):
                    errors.append(f"Field '{name}' must be a number")

            elif field_type == "select":
                options = field.get("options", [])
                if options and str(value) not in [str(o) for o in options]:
                    errors.append(f"Field '{name}' must be one of {options}")

            elif field_type == "text":
                if "min_length" in validation and len(str(value)) < validation["min_length"]:
                    errors.append(f"Field '{name}' must be at least {validation['min_length']} characters")
                if "max_length" in validation and len(str(value)) > validation["max_length"]:
                    errors.append(f"Field '{name}' must be at most {validation['max_length']} characters")
                if "pattern" in validation:
                    import re
                    if not re.match(validation["pattern"], str(value)):
                        errors.append(f"Field '{name}' does not match required pattern")

        return errors
