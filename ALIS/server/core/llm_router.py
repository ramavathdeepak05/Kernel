"""
ALIS LLM Task Router — tiered model dispatch

Problem: A single 1.5B model cannot reliably handle the full range of AI tasks
in ALIS.  Structured slot-filling works fine at small scale, but document
drafting, briefing generation, and eligibility reasoning need larger models or
the output quality erodes institutional trust.

Solution: Three task classes, each mapped to an appropriately sized model.
All model names come from Settings (env-configurable), never hardcoded here.

Task classes
────────────
EXTRACTION  — structured data extraction, JSON schema output, slot-filling
              Output is always machine-readable.  Small model (1.5B) is fine
              because the output space is constrained by the schema.

GENERATION  — document drafting, email composition, briefing summaries,
              lecture slide outlines.  Needs 7B+ for coherent long-form output
              and consistent instruction-following.

REASONING   — multi-step decisions: eligibility evaluation, risk scoring,
              scholarship prioritisation, conflict detection in timetables.
              Needs 14B+ (or external API) for reliable chain-of-thought.

EMBEDDING   — semantic search and RAG retrieval.  Always uses nomic-embed-text
              regardless of the tier settings above.

Usage
─────
    from server.core.llm_router import LLMTaskClass, get_model_for_task

    model = get_model_for_task(LLMTaskClass.GENERATION)
    # → "qwen2.5:7b-instruct"  (or whatever is set in env)

    model = get_model_for_task(LLMTaskClass.EMBEDDING)
    # → "nomic-embed-text"  (fixed, never overridden by task class)

Agents should call get_model_for_task() rather than reading
settings.ollama_extraction_model directly, so routing logic stays in one place.
"""

from enum import Enum

from server.core.settings import settings


class LLMTaskClass(str, Enum):
    """Describes the nature of an LLM task — used to select the right model tier."""

    EXTRACTION = "extraction"
    """Structured data extraction, JSON schema output, slot-filling, classification."""

    GENERATION = "generation"
    """Document drafting, email composition, briefing summaries, narrative generation."""

    REASONING = "reasoning"
    """Eligibility decisions, risk scoring, multi-step logic, conflict detection."""

    EMBEDDING = "embedding"
    """Semantic similarity, RAG retrieval — always nomic-embed-text."""


def get_model_for_task(task_class: LLMTaskClass) -> str:
    """
    Return the Ollama model name appropriate for the given task class.

    If an external LLM API is configured (settings.use_external_llm is True),
    returns settings.llm_api_model for all non-embedding tasks — the external
    model is assumed to be capable across all task classes.

    Args:
        task_class: The class of task being performed.

    Returns:
        Model name string suitable for passing to Ollama or the external API.
    """
    if task_class is LLMTaskClass.EMBEDDING:
        return settings.ollama_embed_model

    if settings.use_external_llm:
        return settings.llm_api_model

    _MODEL_MAP = {
        LLMTaskClass.EXTRACTION: settings.ollama_extraction_model,
        LLMTaskClass.GENERATION: settings.ollama_generation_model,
        LLMTaskClass.REASONING:  settings.ollama_reasoning_model,
    }
    return _MODEL_MAP[task_class]


def get_temperature_for_task(task_class: LLMTaskClass) -> float:
    """
    Return a sensible default temperature for the given task class.

    EXTRACTION and REASONING should be deterministic (temperature=0.0).
    GENERATION benefits from slight creativity (temperature=0.3).
    Callers may override this for specific use cases.
    """
    _TEMP_MAP = {
        LLMTaskClass.EXTRACTION: 0.0,
        LLMTaskClass.GENERATION: 0.3,
        LLMTaskClass.REASONING:  0.0,
        LLMTaskClass.EMBEDDING:  0.0,
    }
    return _TEMP_MAP[task_class]
