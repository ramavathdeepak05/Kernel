"""Config-driven AI policy-authoring assistant wiring (K·01 helper).

Builds a `PolicyAuthoringAssistant` from a ``[policy_assistant]`` section, backed by any registered
InferencePort adapter — so the model is the deployment's choice (Vertex/OpenAI-compat/Ollama). Absent
the section, returns None and the ``/v1/policies/assist`` route 503s (feature off). The assistant uses
a *vendor*-configured model (not the tenant's gateway), so it is available even to free-tier tenants
who have no inference entitlement.

Config shape::

    [policy_assistant]
    adapter = "openai_compat"        # or "vertex_inference" — any InferencePort in the registry
    model   = "gpt-4o-mini"          # default model id passed as ModelRef.id
    [policy_assistant.inference]     # adapter constructor kwargs (secrets via ${ENV_VAR})
    base_url = "https://api.openai.com/v1"
    api_key  = "${OPENAI_API_KEY}"
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from core.policy.authoring import PolicyAuthoringAssistant
from core.types import ModelRef


def _expand(node: Any) -> Any:
    if isinstance(node, str):
        return os.path.expandvars(node)
    if isinstance(node, Mapping):
        return {k: _expand(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_expand(v) for v in node]
    return node


def build_policy_assistant(config: Mapping[str, Any]) -> PolicyAuthoringAssistant | None:
    """Construct the assistant from ``[policy_assistant]``; None when not configured (feature off)."""
    section = config.get("policy_assistant")
    if not section or not section.get("adapter"):
        return None
    from delivery.sdk.kernel import _load_adapter

    inference = _load_adapter(str(section["adapter"]), **_expand(section.get("inference", {})))
    return PolicyAuthoringAssistant(
        inference,
        model_ref=ModelRef(
            id=str(section.get("model", "")),
            version=str(section.get("model_version", "1")),
        ),
    )
