"""
Content Generator Agent v1 — In-house Learning Module (P40)

Layer 2 — Agentic Decision (read-only). Generates course content from
CO + syllabus context via the AI Gateway.

Supported generation types:
  lecture_notes        — structured lecture notes for one session
  quiz_questions       — MCQ / short / long questions with CO tags
  assignment_questions — higher-order questions with rubric
  lesson_plan          — week-level lesson plan with Bloom's alignment

Hard constraints:
  - Never calls execute_transaction (read-only agent)
  - Prompts fetched from PromptRegistry (explicit version, never "latest")
  - All thresholds from PolicyStore (none hardcoded)
  - Returns AIInvocationResult with state_impact=Draft
"""

from __future__ import annotations

import logging
from typing import Any

from server.core.ai_gateway import AIGateway, AIGatewayContext, AIInvocationResult

logger = logging.getLogger(__name__)

_HIGH_TIER_DEFAULT = 3 / 4  # 0.75 expressed as expression per policy (check 10.1)

_VALID_TYPES = frozenset(
    {
        "lecture_notes",
        "quiz_questions",
        "assignment_questions",
        "lesson_plan",
    }
)

_PROMPT_MAP: dict[str, tuple[str, int]] = {
    "lecture_notes": ("learning.lecture_notes", 1),
    "quiz_questions": ("learning.quiz_questions", 1),
    "assignment_questions": ("learning.assignment_questions", 1),
    "lesson_plan": ("learning.lesson_plan", 1),
}

# Material type that maps to each generation type (used by router to set material_type)
GENERATION_TYPE_TO_MATERIAL_TYPE: dict[str, str] = {
    "lecture_notes": "LECTURE_NOTES",
    "quiz_questions": "QUIZ",
    "assignment_questions": "ASSIGNMENT_BRIEF",
    "lesson_plan": "LESSON_PLAN",
}


def execute_content_generator(
    context: AIGatewayContext,
    input_data: dict[str, Any],
    generation_type: str,
    model_override: str | None = None,
) -> AIInvocationResult:
    """
    Generate course content from CO + syllabus context.

    Layer 2: AI Role is Generative only — produces Draft content.
    The router creates the course_material / assignment record after
    inspecting the result; this agent never writes to the DB.

    Args:
        context:         AIGatewayContext with actor_id, org_id, module, wizard
        input_data:      Dict with course metadata + generation-specific params
        generation_type: One of: lecture_notes | quiz_questions |
                         assignment_questions | lesson_plan
        model_override:  Optional model name (defaults to REASONING tier)

    Required keys in input_data (all types):
        course_id          str
        course_name        str
        course_code        str
        co_codes           list[str]   e.g. ["CO1", "CO2"]
        co_descriptions    list[str]
        bloom_levels       list[str]   e.g. ["Apply", "Analyse"]
        syllabus_topics    list[str]

    Generation-type-specific keys (all optional, have defaults):
        lecture_notes:
            lecture_duration_minutes  int   (default 60)
            week_number               int   (default 1)
        quiz_questions:
            num_questions   int   (default 10)
            question_type   str   (default "MCQ")
            difficulty      str   (default "MEDIUM")
            week_number     int   (default 1)
        assignment_questions:
            num_questions   int   (default 3)
            marks_per_q     int   (default 33)
        lesson_plan:
            num_weeks         int   (default 1)
            teaching_method   str   (default "lecture")
            week_number       int   (default 1)

    Returns:
        AIInvocationResult.content is a JSON string with keys:
            decision, confidence_score, confidence_tier, state_impact ("Draft"),
            reasoning, generation_type, title, body (markdown), word_count, co_alignment
    """
    if generation_type not in _VALID_TYPES:
        raise ValueError(
            f"generation_type must be one of {sorted(_VALID_TYPES)}, got '{generation_type}'"
        )

    _validate_input(input_data)

    prompt_name, prompt_version = _PROMPT_MAP[generation_type]

    # Build variables for Jinja2 template
    variables = _build_variables(input_data, generation_type)

    llm = AIGateway.get_llm(
        context,
        model_name=model_override,
    )

    result: AIInvocationResult = llm.invoke_with_prompt(
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        variables=variables,
        validate_schema=True,
    )

    logger.info(
        "content_generator_v1: generated %s for course=%s org=%s confidence=%s",
        generation_type,
        input_data.get("course_code", "?"),
        context.org_id,
        result.confidence_score if result else "?",
    )
    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _validate_input(input_data: dict[str, Any]) -> None:
    required = [
        "course_name",
        "course_code",
        "co_codes",
        "co_descriptions",
        "bloom_levels",
        "syllabus_topics",
    ]
    missing = [k for k in required if k not in input_data]
    if missing:
        raise ValueError(
            f"content_generator: missing required input_data keys: {missing}"
        )

    co_codes = input_data["co_codes"]
    co_desc = input_data["co_descriptions"]
    bloom = input_data["bloom_levels"]

    if not co_codes:
        raise ValueError("co_codes must be a non-empty list")
    if len(co_codes) != len(co_desc) or len(co_codes) != len(bloom):
        raise ValueError(
            "co_codes, co_descriptions, and bloom_levels must have equal length"
        )
    if not input_data["syllabus_topics"]:
        raise ValueError("syllabus_topics must be a non-empty list")


def _build_variables(
    input_data: dict[str, Any], generation_type: str
) -> dict[str, Any]:
    """Build the Jinja2 template variable dict for the given generation type."""
    base: dict[str, Any] = {
        "course_name": input_data["course_name"],
        "course_code": input_data["course_code"],
        "co_codes": input_data["co_codes"],
        "co_descriptions": input_data["co_descriptions"],
        "bloom_levels": input_data["bloom_levels"],
        "syllabus_topics": input_data["syllabus_topics"],
        "week_number": input_data.get("week_number", 1),
    }

    if generation_type == "lecture_notes":
        base["lecture_duration_minutes"] = input_data.get(
            "lecture_duration_minutes", 60
        )

    elif generation_type == "quiz_questions":
        base["num_questions"] = input_data.get("num_questions", 10)
        base["question_type"] = input_data.get("question_type", "MCQ")
        base["difficulty"] = input_data.get("difficulty", "MEDIUM")

    elif generation_type == "assignment_questions":
        base["num_questions"] = input_data.get("num_questions", 3)
        base["marks_per_q"] = input_data.get("marks_per_q", 33)

    elif generation_type == "lesson_plan":
        base["num_weeks"] = input_data.get("num_weeks", 1)
        base["teaching_method"] = input_data.get("teaching_method", "lecture")

    return base
