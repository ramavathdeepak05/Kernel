"""Violation reporting infrastructure for alis-lint."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Rule(str, Enum):
    """Architectural invariant rules."""
    INV1_MUTATION_VIA_QUERY = "INV-1"
    INV2_MISSING_AUDIT      = "INV-2"
    INV3_LATERAL_IMPORT     = "INV-3"


RULE_DESCRIPTIONS = {
    Rule.INV1_MUTATION_VIA_QUERY: "SQL mutation (INSERT/UPDATE/DELETE) must use execute_transaction, not execute_query",
    Rule.INV2_MISSING_AUDIT:      "execute_transaction must be followed by AuditLog.log() in the same function",
    Rule.INV3_LATERAL_IMPORT:     "Layer-2 domain modules must not import directly from each other",
}


@dataclass
class Violation:
    """A single architectural violation."""
    file: str
    line: int
    col: int
    rule: Rule
    message: str
    fix_hint: Optional[str] = None
    suppressed: bool = False
    suppression_reason: Optional[str] = None

    @property
    def code(self) -> str:
        return self.rule.value


@dataclass
class LintResult:
    """Aggregated result from all checkers."""
    violations: List[Violation] = field(default_factory=list)
    suppressions: List[Violation] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.violations) > 0

    def add(self, v: Violation) -> None:
        if v.suppressed:
            self.suppressions.append(v)
        else:
            self.violations.append(v)

    def merge(self, other: LintResult) -> None:
        self.violations.extend(other.violations)
        self.suppressions.extend(other.suppressions)


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def format_console(result: LintResult) -> str:
    """Rich console output grouped by file."""
    if not result.violations and not result.suppressions:
        return "\033[32m✓ No architectural violations found.\033[0m"

    lines: list[str] = []

    if result.violations:
        lines.append(f"\033[31m✗ {len(result.violations)} violation(s) found:\033[0m\n")

        by_file: dict[str, list[Violation]] = {}
        for v in result.violations:
            by_file.setdefault(v.file, []).append(v)

        for fpath in sorted(by_file):
            lines.append(f"  \033[1m{fpath}\033[0m")
            for v in sorted(by_file[fpath], key=lambda x: x.line):
                lines.append(
                    f"    \033[33mL{v.line}\033[0m  [{v.code}] {v.message}"
                )
                if v.fix_hint:
                    lines.append(f"           \033[36m→ {v.fix_hint}\033[0m")
            lines.append("")

    if result.suppressions:
        lines.append(
            f"\033[33m⚠ {len(result.suppressions)} suppression(s):\033[0m"
        )
        for v in result.suppressions:
            lines.append(
                f"  {v.file}:L{v.line} [{v.code}] {v.suppression_reason}"
            )

    return "\n".join(lines)


def format_json(result: LintResult) -> str:
    """Machine-readable JSON output for CI."""
    data = {
        "violations": [
            {
                "file": v.file,
                "line": v.line,
                "col": v.col,
                "rule": v.code,
                "message": v.message,
                "fix_hint": v.fix_hint,
            }
            for v in result.violations
        ],
        "suppressions": [
            {
                "file": v.file,
                "line": v.line,
                "rule": v.code,
                "reason": v.suppression_reason,
            }
            for v in result.suppressions
        ],
        "summary": {
            "violations": len(result.violations),
            "suppressions": len(result.suppressions),
            "passed": not result.has_errors,
        },
    }
    return json.dumps(data, indent=2)
