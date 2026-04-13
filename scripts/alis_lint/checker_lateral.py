"""
INV-3: No lateral cross-module imports between Layer-2 domain modules.

Import scanner that checks every `from server.<module_A>... import ...`
statement in files under `server/<module_B>/`. If both module_A and module_B
are Layer-2 domain modules, it's a violation.

Allowed:
  - Imports from core, db_service (infrastructure)
  - Imports from api, tasks, rules, agents, tools, integrations (non-L2)
  - Imports from communication (infrastructure-like)
  - Intra-module imports (server.admissions inside admissions/)
  - Inline suppression: # alis-lint: skip INV-3 <reason>
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List

from .report import LintResult, Rule, Violation

# Layer-2 domain modules — lateral imports between these are violations
LAYER2_MODULES = frozenset({
    "admissions", "academics", "examinations", "finance", "hr",
    "student_services", "alumni", "phd", "convocation", "consent",
})

# Infrastructure / aggregation modules — imports FROM these are always OK
INFRA_MODULES = frozenset({
    "core", "db_service", "api", "tasks", "rules", "agents",
    "tools", "integrations", "communication", "migration",
    "regulatory", "reporting", "process_engine",
})

_SERVER_PATH_RE = re.compile(r'[\\/]server[\\/](\w+)[\\/]')

_SUPPRESS_RE = re.compile(
    r"#\s*alis-lint:\s*skip\s+INV-3\s*(.*)",
    re.IGNORECASE,
)


def check_file(filepath: str, source: str | None = None) -> LintResult:
    """Check a single file for INV-3 lateral import violations."""
    result = LintResult()
    path = Path(filepath)

    # Determine which module this file belongs to
    m = _SERVER_PATH_RE.search(str(path))
    if not m:
        return result  # not inside server/
    source_module = m.group(1)

    # Only check files in Layer-2 modules
    if source_module not in LAYER2_MODULES:
        return result

    if source is None:
        source = path.read_text(encoding="utf-8", errors="ignore")

    source_lines = source.splitlines()

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return result

    for node in ast.walk(tree):
        target_module = None
        import_path = ""

        if isinstance(node, ast.ImportFrom) and node.module:
            # from server.finance.invoice import InvoiceService
            parts = node.module.split(".")
            if len(parts) >= 2 and parts[0] == "server":
                target_module = parts[1]
                import_path = node.module

        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if len(parts) >= 2 and parts[0] == "server":
                    target_module = parts[1]
                    import_path = alias.name
                    break

        if not target_module:
            continue

        # Same module = OK
        if target_module == source_module:
            continue

        # Infrastructure = OK
        if target_module in INFRA_MODULES or target_module not in LAYER2_MODULES:
            continue

        # This is a lateral L2→L2 import — violation
        suppression = _check_suppression(source_lines, node.lineno)

        v = Violation(
            file=str(path),
            line=node.lineno,
            col=node.col_offset,
            rule=Rule.INV3_LATERAL_IMPORT,
            message=f"Lateral import: {source_module} → {target_module} (from {import_path})",
            fix_hint=f"Use DomainEventBus.publish() or execute_query() on shared tables instead of importing from server.{target_module}",
            suppressed=suppression is not None,
            suppression_reason=suppression,
        )
        result.add(v)

    return result


def _check_suppression(source_lines: list[str], line_no: int) -> str | None:
    """Check if the given line or the line above has a suppression comment."""
    for offset in (0, -1):
        idx = line_no - 1 + offset
        if 0 <= idx < len(source_lines):
            m = _SUPPRESS_RE.search(source_lines[idx])
            if m:
                return m.group(1).strip() or "no reason given"
    return None
