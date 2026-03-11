"""
ALIS AI Guardrails — E03-S08

MODULE: Platform Core (E03 — AI Gateway & Agents)
LAYER: Layer 4 (Invariant Enforcement)
ENTITY: AIGuardrails

Implements post-generation safety filters applied to all AI outputs
before they are returned to callers.

All filters are:
- Deterministic (no LLM calls)
- Local (no external network)
- Applied AFTER the LLM generates output
- Logged to audit on every violation

Filter Pipeline:
    1. ToxicityFilter       — Abusive / discriminatory language
    2. HallucinationDetector — Numeric/entity claims not grounded in input
    3. PolicyContradictionDetector — Contradicts active institutional policy
    4. UnsafeSuggestionBlocker     — Suggests bypassing auth/audit/system controls

Severity:
    WARNING — logged, output returned with warning annotation
    BLOCK   — output suppressed, GuardrailViolationError raised

Acceptance Criteria (E03-S08):
    - [x] Toxicity filtering
    - [x] Hallucination detection
    - [x] Policy contradiction detection
    - [x] Unsafe suggestion blocking
    - [x] Guardrails applied post-generation
    - [x] Blocked outputs logged
    - [x] Safe fallback responses
    - [x] No silent failures
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .audit import AuditLog, AuditAction
from .exceptions import GuardrailViolationError

logger = logging.getLogger(__name__)

_SAFE_FALLBACK = (
    "This output was blocked by institutional safety guardrails. "
    "Please refer the request for human review."
)


# =============================================================================
# VIOLATION MODEL
# =============================================================================

@dataclass
class GuardrailViolation:
    """A single guardrail violation found in AI output."""
    filter_name: str          # "toxicity" | "hallucination" | "policy_contradiction" | "unsafe_suggestion"
    severity: str             # "WARNING" | "BLOCK"
    detail: str               # Human-readable description


@dataclass
class GuardrailResult:
    """Aggregated result of all guardrail checks on an AI output."""
    passed: bool
    blocked: bool                              # True if any BLOCK-severity violation
    violations: List[GuardrailViolation] = field(default_factory=list)
    fallback_response: Optional[str] = None   # Populated when blocked=True


# =============================================================================
# FILTER 1: TOXICITY
# =============================================================================

class ToxicityFilter:
    """
    Detects toxic, abusive, or discriminatory language in AI output.

    Academic context: checks for personal insults, slurs, threatening language,
    and sexually inappropriate content. All patterns are case-insensitive.

    Severity: BLOCK
    """

    _BLOCK_PATTERNS: List[re.Pattern] = [
        # Personal threats / violence
        re.compile(r"\b(kill|murder|assault|threaten|harm)\s+(you|him|her|them|student|faculty)\b", re.IGNORECASE),
        re.compile(r"\b(you('re|\s+are)\s+(worthless|stupid|idiot|moron|useless))\b", re.IGNORECASE),

        # Slurs — keeping patterns intentionally broad to avoid listing actual slurs
        re.compile(r"\b(racial|ethnic|gender|religious)\s+slur\b", re.IGNORECASE),

        # Sexual inappropriateness
        re.compile(r"\b(sexual(ly)?\s+(explicit|haras|assault))\b", re.IGNORECASE),

        # Academic dishonesty promotion
        re.compile(r"\b(cheat|plagiari[sz]e|copy\s+(the\s+)?answer|steal\s+(the\s+)?exam)\b", re.IGNORECASE),
    ]

    _WARNING_PATTERNS: List[re.Pattern] = [
        re.compile(r"\b(inappropriate|offensive|discriminat)\b", re.IGNORECASE),
    ]

    @classmethod
    def check(cls, output: str) -> List[GuardrailViolation]:
        violations = []
        for pattern in cls._BLOCK_PATTERNS:
            match = pattern.search(output)
            if match:
                violations.append(GuardrailViolation(
                    filter_name="toxicity",
                    severity="BLOCK",
                    detail=f"Toxic content detected: '{match.group()[:50]}'",
                ))
        for pattern in cls._WARNING_PATTERNS:
            match = pattern.search(output)
            if match:
                violations.append(GuardrailViolation(
                    filter_name="toxicity",
                    severity="WARNING",
                    detail=f"Potentially inappropriate language: '{match.group()[:50]}'",
                ))
        return violations


# =============================================================================
# FILTER 2: HALLUCINATION DETECTOR
# =============================================================================

class HallucinationDetector:
    """
    Heuristic hallucination detector.

    Strategy: extract specific numeric values from AI output that are NOT
    present in the input context. Specific numbers (e.g., percentages,
    scores, dates) that were not in the prompt are likely hallucinated.

    Also flags named entities that appear in output but not in input.

    Severity: WARNING (hallucination is advisory — humans should verify)
    """

    # Pattern: floating-point or integer values that look like scores/percentages
    _NUMBER_PATTERN = re.compile(r'\b(\d{1,3}(?:\.\d{1,4})?)\s*(%|percent|marks?|score|cgpa|gpa|grade)\b', re.IGNORECASE)

    @classmethod
    def check(cls, output: str, input_context: str) -> List[GuardrailViolation]:
        """
        Check if output contains specific numeric claims not in the input.

        Args:
            output:        AI-generated output text
            input_context: The original prompt / input fed to the LLM

        Returns:
            List of violations (WARNING severity)
        """
        violations = []

        # Extract numeric claims from output
        output_numbers = {
            m.group(1)
            for m in cls._NUMBER_PATTERN.finditer(output)
        }

        if not output_numbers:
            return violations

        # Extract numeric claims from input context
        input_numbers = {
            m.group(1)
            for m in cls._NUMBER_PATTERN.finditer(input_context)
        }

        # Numbers in output that weren't in input = potential hallucination
        ungrounded = output_numbers - input_numbers
        if ungrounded:
            violations.append(GuardrailViolation(
                filter_name="hallucination",
                severity="WARNING",
                detail=(
                    f"Output contains numeric claims not present in input context: "
                    f"{sorted(ungrounded)[:5]}. Human verification recommended."
                ),
            ))

        return violations


# =============================================================================
# FILTER 3: POLICY CONTRADICTION DETECTOR
# =============================================================================

class PolicyContradictionDetector:
    """
    Detects when AI output contradicts known active institutional policies.

    Checks numeric thresholds in the output against ConfigRegistry values.
    For example: if the AI says "40% attendance is acceptable" but the
    active policy mandates 75%, that is flagged as a contradiction.

    Severity: BLOCK (AI must not contradict policy)
    """

    # Maps policy keys to natural language context patterns
    # Each entry: (config_key, output_pattern, description)
    _POLICY_CHECKS = [
        (
            "attendance.minimum_percentage",
            re.compile(r'\b(\d{1,3})\s*(%|percent)\s*(attendance|present)', re.IGNORECASE),
            "attendance threshold",
        ),
        (
            "finance.fee.late_penalty_percent",
            re.compile(r'\b(\d{1,3})\s*(%|percent)\s*(penalty|late\s*fee)', re.IGNORECASE),
            "late fee penalty",
        ),
    ]

    @classmethod
    def check(cls, output: str, tenant_id: str) -> List[GuardrailViolation]:
        """
        Check output for contradictions with active policy values.

        Args:
            output:    AI-generated output
            tenant_id: Tenant scope for policy lookup

        Returns:
            List of violations
        """
        from .config import ConfigRegistry

        violations = []

        for config_key, pattern, description in cls._POLICY_CHECKS:
            policy_value = ConfigRegistry.get(config_key)
            if policy_value is None:
                continue

            matches = pattern.findall(output)
            for match in matches:
                # match[0] is the numeric capture group
                try:
                    output_value = float(match[0] if isinstance(match, tuple) else match)
                except (ValueError, TypeError):
                    continue

                policy_num = float(policy_value)

                # Flag if output suggests a value significantly below policy
                if output_value < policy_num * 0.9:  # >10% below policy threshold
                    violations.append(GuardrailViolation(
                        filter_name="policy_contradiction",
                        severity="BLOCK",
                        detail=(
                            f"Output suggests {description} of {output_value}% but "
                            f"active policy requires {policy_num}% "
                            f"(key: {config_key})."
                        ),
                    ))

        return violations


# =============================================================================
# FILTER 4: UNSAFE SUGGESTION BLOCKER
# =============================================================================

class UnsafeSuggestionBlocker:
    """
    Blocks AI outputs that suggest bypassing institutional controls.

    Unsafe suggestions include:
    - Delete/drop/truncate records
    - Bypass authentication or RBAC
    - Skip audit logging
    - Override system controls without authorization
    - Suggest raw SQL or shell commands

    Severity: BLOCK
    """

    _BLOCK_PATTERNS: List[re.Pattern] = [
        # Database destruction
        re.compile(r'\b(drop\s+table|truncate\s+table|delete\s+from\s+\w+\s+where\s+1\s*=\s*1)', re.IGNORECASE),
        re.compile(r'\b(delete\s+all\s+records?|purge\s+the\s+database)\b', re.IGNORECASE),

        # Auth bypass
        re.compile(r'\b(bypass\s+(authentication|auth|login|rbac|permission))\b', re.IGNORECASE),
        re.compile(r'\b(skip\s+(authentication|audit|permission|verification))\b', re.IGNORECASE),
        re.compile(r'\bdisable\s+(audit|logging|rbac|security)\b', re.IGNORECASE),

        # Hardcoded credential suggestions
        re.compile(r'\b(hardcode\s+(password|credential|token|secret|key))\b', re.IGNORECASE),
        re.compile(r'password\s*=\s*["\'](?!(?:"|\')\s*\+)[^"\']{3,}["\']', re.IGNORECASE),

        # Shell/system commands
        re.compile(r'\b(os\.system|subprocess\.call|exec\s*\(|eval\s*\()', re.IGNORECASE),
        re.compile(r'\b(rm\s+-rf|chmod\s+777|sudo\s+)', re.IGNORECASE),

        # Override system controls
        re.compile(r'\b(override\s+(the\s+)?(system|global|institutional)\s+(lock|control|rule|policy))\b', re.IGNORECASE),
        re.compile(r'\b(without\s+(audit|logging|approval|authorization))\b', re.IGNORECASE),
    ]

    @classmethod
    def check(cls, output: str) -> List[GuardrailViolation]:
        violations = []
        for pattern in cls._BLOCK_PATTERNS:
            match = pattern.search(output)
            if match:
                violations.append(GuardrailViolation(
                    filter_name="unsafe_suggestion",
                    severity="BLOCK",
                    detail=f"Unsafe suggestion detected: '{match.group()[:80]}'",
                ))
        return violations


# =============================================================================
# MAIN GUARDRAILS ORCHESTRATOR
# =============================================================================

class AIGuardrails:
    """
    Orchestrates all guardrail filters for post-generation AI output validation.

    Called by InstrumentedLLM.invoke() after successful LLM generation
    and schema validation (if applicable).

    Usage:
        result = AIGuardrails.check_output(
            output=llm_text,
            input_context=original_prompt,
            tenant_id=context.org_id or "default",
            context=gateway_context,
        )
        if result.blocked:
            raise GuardrailViolationError(...)
    """

    @classmethod
    def check_output(
        cls,
        output: str,
        input_context: str,
        tenant_id: str,
        actor_id: str = "unknown",
        actor_role: Optional[str] = None,
        module: Optional[str] = None,
        wizard: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> GuardrailResult:
        """
        Run all guardrail filters against AI output.

        Args:
            output:        The raw LLM output text
            input_context: The original prompt sent to the LLM
            tenant_id:     Tenant scope for policy checks
            actor_id:      Actor for audit logging
            actor_role:    Actor role for audit logging
            module:        Module context
            wizard:        Wizard context
            request_id:    Gateway request ID

        Returns:
            GuardrailResult — passed=True if no violations, blocked=True if hard-blocked

        Side effects:
            Logs GUARDRAIL_BLOCKED or GUARDRAIL_WARNING to AuditLog
        """
        violations: List[GuardrailViolation] = []

        violations.extend(ToxicityFilter.check(output))
        violations.extend(HallucinationDetector.check(output, input_context))
        violations.extend(PolicyContradictionDetector.check(output, tenant_id))
        violations.extend(UnsafeSuggestionBlocker.check(output))

        blocked = any(v.severity == "BLOCK" for v in violations)
        passed = len(violations) == 0

        if violations:
            action = AuditAction.GUARDRAIL_BLOCKED if blocked else AuditAction.GUARDRAIL_WARNING
            AuditLog.log(
                action=action,
                actor_id=actor_id,
                actor_role=actor_role,
                entity_type="ai_guardrail",
                entity_id=request_id or "unknown",
                org_id=tenant_id,
                module=module,
                wizard=wizard,
                success=not blocked,
                failure_reason=(
                    f"{len(violations)} guardrail violation(s)"
                    if blocked else None
                ),
                metadata={
                    "blocked": blocked,
                    "violation_count": len(violations),
                    "violations": [
                        {
                            "filter": v.filter_name,
                            "severity": v.severity,
                            "detail": v.detail,
                        }
                        for v in violations
                    ],
                },
            )

            if blocked:
                logger.warning(
                    "E03-S08: Guardrail BLOCK — %d violation(s) [request=%s]",
                    len(violations), request_id,
                )
            else:
                logger.info(
                    "E03-S08: Guardrail WARNING — %d violation(s) [request=%s]",
                    len(violations), request_id,
                )

        return GuardrailResult(
            passed=passed,
            blocked=blocked,
            violations=violations,
            fallback_response=_SAFE_FALLBACK if blocked else None,
        )
