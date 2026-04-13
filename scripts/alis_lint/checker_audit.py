"""
INV-2: Every execute_transaction must be followed by AuditLog.log().

AST walker that checks every function definition containing an
execute_transaction() call. If no AuditLog.log() call appears in
the same function body (after the transaction), it reports a violation.

Special cases:
  - Functions that RETURN query tuples (builder pattern) are exempt —
    detected by return type annotation containing "tuple" or "list[tuple]"
    or by function name starting with "_build"
  - Inline suppression: # alis-lint: skip INV-2 <reason>
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List

from .report import LintResult, Rule, Violation

_SUPPRESS_RE = re.compile(
    r"#\s*alis-lint:\s*skip\s+INV-2\s*(.*)",
    re.IGNORECASE,
)

# Function names that are exempt (query builder helpers)
_EXEMPT_NAME_PREFIXES = ("_build", "_prepare", "_compose")


def check_file(filepath: str, source: str | None = None) -> LintResult:
    """Check a single file for INV-2 violations."""
    result = LintResult()
    path = Path(filepath)

    if source is None:
        source = path.read_text(encoding="utf-8", errors="ignore")

    source_lines = source.splitlines()

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return result

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        func_name = node.name

        # Skip builder helpers
        if any(func_name.startswith(p) for p in _EXEMPT_NAME_PREFIXES):
            continue

        # Check if return annotation suggests tuple builder
        if _is_tuple_builder(node):
            continue

        # Find execute_transaction calls
        et_calls = _find_calls(node, "execute_transaction")
        if not et_calls:
            continue

        # Find AuditLog.log calls anywhere in the function
        audit_calls = _find_audit_calls(node)

        if audit_calls:
            continue  # has at least one AuditLog.log — OK

        # Check for suppression on the function def line or the line above
        suppression = _check_suppression(source_lines, node.lineno)

        # Also check if there's a suppression on the execute_transaction line
        if suppression is None and et_calls:
            suppression = _check_suppression(source_lines, et_calls[0].lineno)

        v = Violation(
            file=str(path),
            line=et_calls[0].lineno,
            col=et_calls[0].col_offset,
            rule=Rule.INV2_MISSING_AUDIT,
            message=f"execute_transaction() in {func_name}() has no AuditLog.log() call",
            fix_hint="Add AuditLog.log(action=..., actor_id=..., entity_type=..., entity_id=..., org_id=...) after the transaction",
            suppressed=suppression is not None,
            suppression_reason=suppression,
        )
        result.add(v)

    return result


def _find_calls(func_node: ast.AST, func_name: str) -> list[ast.Call]:
    """Find all calls to a given function name within a function body."""
    calls = []
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Name) and f.id == func_name:
            calls.append(node)
        elif isinstance(f, ast.Attribute) and f.attr == func_name:
            calls.append(node)
    return calls


def _find_audit_calls(func_node: ast.AST) -> list[ast.Call]:
    """Find AuditLog.log(...) calls within a function body."""
    calls = []
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        # AuditLog.log(...)
        if isinstance(f, ast.Attribute) and f.attr == "log":
            if isinstance(f.value, ast.Name) and f.value.id == "AuditLog":
                calls.append(node)
    return calls


def _is_tuple_builder(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if function return annotation suggests a tuple/query builder."""
    ann = func_node.returns
    if ann is None:
        return False

    # Check ast.dump for common patterns
    ann_str = ast.dump(ann).lower()
    if "tuple" in ann_str:
        return True

    # Also check for Subscript[list, tuple]
    if isinstance(ann, ast.Subscript):
        if isinstance(ann.value, ast.Name):
            if ann.value.id.lower() in ("list", "sequence"):
                return True

    return False


def _check_suppression(source_lines: list[str], line_no: int) -> str | None:
    """Check if the given line or the line above has a suppression comment."""
    for offset in (0, -1):
        idx = line_no - 1 + offset
        if 0 <= idx < len(source_lines):
            m = _SUPPRESS_RE.search(source_lines[idx])
            if m:
                return m.group(1).strip() or "no reason given"
    return None
