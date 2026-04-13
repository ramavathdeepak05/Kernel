"""
INV-1: No mutations via execute_query.

AST walker that finds execute_query(...) calls where the first positional
argument is a SQL string containing INSERT, UPDATE, DELETE, or TRUNCATE.

Handles:
  - Literal strings (inline or triple-quoted)
  - f-strings (scans the literal parts)
  - String variables assigned 1-10 lines above the call
  - Inline suppression: # alis-lint: skip INV-1 <reason>
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List

from .report import LintResult, Rule, Violation

# SQL mutation keywords — must appear as whole word (not inside column names)
_MUTATION_RE = re.compile(
    r"\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|TRUNCATE)\b",
    re.IGNORECASE,
)

_SUPPRESS_RE = re.compile(
    r"#\s*alis-lint:\s*skip\s+INV-1\s*(.*)",
    re.IGNORECASE,
)


def check_file(filepath: str, source: str | None = None) -> LintResult:
    """Check a single file for INV-1 violations."""
    result = LintResult()
    path = Path(filepath)

    if source is None:
        source = path.read_text(encoding="utf-8", errors="ignore")

    source_lines = source.splitlines()

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return result  # skip unparseable files

    # Collect string variable assignments for flow-sensitive lookup
    # Maps (line_number) -> {var_name: sql_string}
    str_assignments: dict[int, dict[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                str_assignments.setdefault(node.lineno, {})[target.id] = node.value.value

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # Match execute_query(...) — both bare and attr form
        func = node.func
        is_execute_query = False
        if isinstance(func, ast.Name) and func.id == "execute_query":
            is_execute_query = True
        elif isinstance(func, ast.Attribute) and func.attr == "execute_query":
            is_execute_query = True

        if not is_execute_query:
            continue
        if not node.args:
            continue

        # Extract the SQL string from the first argument
        sql_strings = _extract_sql(node.args[0], node.lineno, str_assignments)

        for sql in sql_strings:
            if _MUTATION_RE.search(sql):
                # Check for inline suppression
                line_idx = node.lineno - 1
                suppression = None
                if 0 <= line_idx < len(source_lines):
                    m = _SUPPRESS_RE.search(source_lines[line_idx])
                    if m:
                        suppression = m.group(1).strip() or "no reason given"

                # Also check previous line (suppression comment above)
                if suppression is None and 0 <= line_idx - 1 < len(source_lines):
                    m = _SUPPRESS_RE.search(source_lines[line_idx - 1])
                    if m:
                        suppression = m.group(1).strip() or "no reason given"

                # Extract mutation type for clear messaging
                mut_match = _MUTATION_RE.search(sql)
                mut_keyword = mut_match.group(1).split()[0].upper() if mut_match else "MUTATION"

                v = Violation(
                    file=str(path),
                    line=node.lineno,
                    col=node.col_offset,
                    rule=Rule.INV1_MUTATION_VIA_QUERY,
                    message=f"SQL {mut_keyword} inside execute_query() — must use execute_transaction()",
                    fix_hint=f"Replace execute_query(...) with execute_transaction([(sql, params)])",
                    suppressed=suppression is not None,
                    suppression_reason=suppression,
                )
                result.add(v)
                break  # one violation per call site

    return result


def _extract_sql(node: ast.expr, call_line: int, str_assignments: dict) -> list[str]:
    """Extract SQL string(s) from the first argument of execute_query."""
    strings: list[str] = []

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        strings.append(node.value)

    elif isinstance(node, ast.JoinedStr):
        # f-string — extract literal parts
        for val in node.values:
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                strings.append(val.value)

    elif isinstance(node, ast.Name):
        # Variable reference — look back up to 10 lines for assignment
        var_name = node.id
        for line_no in range(call_line, max(0, call_line - 11), -1):
            assignments = str_assignments.get(line_no, {})
            if var_name in assignments:
                strings.append(assignments[var_name])
                break

    return strings
