#!/usr/bin/env python3
"""
ALIS Custom Linter — §12.4 of Engineering Build Guidelines

Flags hardcoding violations that the standard linter cannot catch:
  1. Hardcoded role names in business logic (outside tests/migrations)
  2. Numeric literals in threshold/eligibility functions
  3. Raw SQL UPDATE status= outside migrations
  4. Direct LLM client calls outside AI Gateway module
  5. Cross-module service imports in business logic

Usage:
    python scripts/lint_alis.py [path]          # check path (default: ALIS/server)
    python scripts/lint_alis.py --fix-report    # output JSON report

Exit codes:
    0 — no violations
    1 — violations found
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# §12.4 rule 1: Role name literals forbidden in business logic
# NOTE: "system" is intentionally excluded — it is used as actor_id/actor_type
# throughout the codebase (system-level operations) and is NOT an RBAC role.
FORBIDDEN_ROLE_LITERALS = {
    "registrar", "hod", "faculty", "finance_officer", "hr_admin",
    "super_admin", "admin", "student", "dean", "ai_agent",
    "exam_controller", "m1_manager", "m2_manager", "m3_manager",
    "m4_manager", "m5_manager", "m6_manager", "m7_manager", "m8_manager",
    "m9_manager",
}

# §12.4 rule 4: Direct LLM client imports outside the AI gateway
FORBIDDEN_LLM_IMPORTS = {"ollama", "openai", "anthropic", "langchain"}

# Paths that are exempt from rules (tests, migrations, scripts, gateway itself)
EXEMPT_DIRS = {
    "tests", "migrations", "scripts", "server/core/ai_gateway",
    "server/core/llm_router", "server/tasks",
    # admissions_templates is a data/seed file that bootstraps notification templates
    # into the communication module — exempt from R05 (not business logic)
    "server/admissions/admissions_templates",
}

# Modules that may NOT be imported into each other's business logic
MODULE_DIRS = [
    "server/admissions", "server/academics", "server/examinations",
    "server/finance", "server/hr", "server/student_services",
    "server/communication", "server/alumni", "server/phd",
    "server/convocation", "server/regulatory", "server/consent",
    "server/process_engine",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    file: str
    line: int
    rule: str
    detail: str


@dataclass
class LintResult:
    violations: List[Violation] = field(default_factory=list)

    def add(self, file: str, line: int, rule: str, detail: str) -> None:
        self.violations.append(Violation(file, line, rule, detail))

    @property
    def ok(self) -> bool:
        return len(self.violations) == 0


# ---------------------------------------------------------------------------
# Rule checkers
# ---------------------------------------------------------------------------

def _is_exempt(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root).as_posix()
    return any(exempt in rel for exempt in EXEMPT_DIRS)


def check_role_literals(source: str, file: str, result: LintResult) -> None:
    """§12.4 rule 1 — role name string literals in business logic."""
    in_docstring = False
    docstring_quote = ""

    for lineno, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()

        # Track triple-quoted string state (docstrings / multiline strings)
        for quote in ('"""', "'''"):
            count = stripped.count(quote)
            if not in_docstring:
                if count % 2 == 1:
                    in_docstring = True
                    docstring_quote = quote
            elif docstring_quote == quote:
                if count % 2 == 1:
                    in_docstring = False
                    docstring_quote = ""

        # Skip comment lines and docstring content
        if stripped.startswith("#") or in_docstring:
            continue

        for role in FORBIDDEN_ROLE_LITERALS:
            # Match quoted role name (but not inside a class/enum definition)
            pattern = rf'["\']({re.escape(role)})["\']'
            if re.search(pattern, line):
                # Allow Role.X = "role_name" enum definitions
                if re.search(r"^\s+\w+\s*=\s*[\"']", line):
                    continue
                # Allow ROLE_PERMISSIONS dict keys and Role enum references
                if "Role." in line or "ROLE_" in line:
                    continue
                # Allow actor_id / actor_type defaults — not RBAC role checks
                if re.search(r'actor_(?:id|type)\s*[=:]\s*(?:str\s*=\s*)?["\']', line):
                    continue
                # Allow FastAPI route tags (tags=["..."])
                if re.search(r'tags\s*=\s*\[', line):
                    continue
                # Allow dict keys for entity types ("faculty": [...] or "student": [...])
                if re.search(rf'["\'](?:{re.escape(role)})["\']:\s*[\[\{{]', line):
                    continue
                # Allow JSON response dict keys ({"faculty": items})
                if re.search(rf'["\'](?:{re.escape(role)})["\']:\s*\w', line) and \
                   re.search(r'(?:return|JSONResponse|content)\s*', line):
                    continue
                # Allow entity_type comparisons (migration pipeline uses entity types, not roles)
                if re.search(r'entity_type\s*(?:==|!=|not\s+in|in)\s', line) or \
                   re.search(r'entity_type\s*not\s+in\s*\(', line):
                    continue
                # Skip dict keys that map to variables/constants ("role": something)
                if re.search(r'["\']' + re.escape(role) + r'["\']:\s*\w', line):
                    continue
                # Skip entity-type string args to state registry / validation calls
                if re.search(r'validate_transition\s*\(', line):
                    continue
                # Skip list/array items (entity names in SUPPORTED_ENTITIES etc.)
                # Catches list-continuation lines that are only strings, commas, whitespace
                line_code = line.split("#")[0]
                _list_only = re.match(r"""^[\s"',\w\[\]]+$""", line_code)
                if re.search(r"=\s*\[", line_code) or _list_only:
                    continue
                # Skip dict/context .get() lookups (not role comparisons)
                if re.search(r'\.get\s*\(', line):
                    continue
                # Skip description= / docstring parameter strings in API decorators
                if re.search(r"description\s*=\s*[\"']", line):
                    continue
                # Skip inline comments (e.g., # e.g., "student")
                code_part = line.split("#")[0]
                if not re.search(pattern, code_part):
                    continue
                # Skip audience_type / entity_type defaults (not RBAC roles)
                if re.search(r"(?:audience_type|entity_type)\s*[=:].*[\"']", line):
                    continue
                # Skip third-party build()/API calls where 'admin' is a service name
                if re.search(r'build\s*\(', line):
                    continue
                result.add(file, lineno, "R01-ROLE-LITERAL",
                           f"Hardcoded role string '{role}' — use Permission/Role enum or runtime RBAC check")


_INFRA_TABLES = {
    # System infrastructure tables — no business state machine, raw SQL is correct here
    "domain_events", "export_jobs", "import_jobs", "prompt_registry",
    "celery_task_meta", "payment_webhook_log",
}

def check_status_updates(source: str, file: str, result: LintResult) -> None:
    """§12.4 rule 3 — raw UPDATE status= in Python (not migrations)."""
    for lineno, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.search(r"UPDATE\s+\w+\s+SET\s+status\s*=", line, re.IGNORECASE):
            # Extract table name from UPDATE <table> SET
            m = re.search(r"UPDATE\s+(\w+)\s+SET\s+status\s*=", line, re.IGNORECASE)
            if m and m.group(1).lower() in _INFRA_TABLES:
                continue  # Infrastructure table — raw SQL is the correct abstraction
            result.add(file, lineno, "R03-RAW-STATUS-UPDATE",
                       "Raw SQL UPDATE status= — use the state machine (StateMachine.transition())")


def check_llm_imports(tree: ast.Module, file: str, result: LintResult) -> None:
    """§12.4 rule 4 — direct LLM client imports outside AI Gateway."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if name in FORBIDDEN_LLM_IMPORTS:
                    result.add(file, node.lineno, "R04-DIRECT-LLM-IMPORT",
                               f"Direct import of '{name}' — all LLM calls must go through server.core.ai_gateway")


def check_cross_module_imports(tree: ast.Module, file: str, result: LintResult) -> None:
    """§12.4 rule 5 — cross-module service imports between bounded contexts."""
    # Determine which module this file belongs to
    current_module: Optional[str] = None
    for mod_dir in MODULE_DIRS:
        if mod_dir.replace("/", os.sep) in file:
            current_module = mod_dir
            break

    if current_module is None:
        return  # Not inside a module — skip

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for other_module in MODULE_DIRS:
                if other_module == current_module:
                    continue
                other_pkg = other_module.replace("/", ".")  # e.g. server.admissions
                if node.module.startswith(other_pkg):
                    result.add(
                        file, node.lineno, "R05-CROSS-MODULE-IMPORT",
                        f"Module '{current_module}' imports from '{other_module}' — use domain events instead"
                    )


def check_numeric_thresholds(source: str, file: str, result: LintResult) -> None:
    """§12.4 rule 2 — numeric literals in eligibility/threshold functions.

    Heuristic: flags numeric literals (int/float) inside functions whose
    names contain eligibility/threshold keywords.
    """
    threshold_keywords = {"eligib", "threshold", "attendance", "grace", "passing", "cutoff", "crit"}
    in_threshold_fn = False
    fn_indent = 0
    in_docstring = False
    docstring_quote = ""

    for lineno, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()

        # Track triple-quoted string state (docstrings + multiline strings)
        for quote in ('"""', "'''"):
            count = stripped.count(quote)
            if not in_docstring:
                if count % 2 == 1:  # odd number = entering docstring
                    in_docstring = True
                    docstring_quote = quote
            elif docstring_quote == quote:
                if count % 2 == 1:  # odd number = exiting docstring
                    in_docstring = False
                    docstring_quote = ""

        # Detect function definition
        fn_match = re.match(r"^(\s*)def\s+(\w+)\s*\(", line)
        if fn_match:
            indent = len(fn_match.group(1))
            fn_name = fn_match.group(2).lower()
            if any(kw in fn_name for kw in threshold_keywords):
                in_threshold_fn = True
                fn_indent = indent
            elif in_threshold_fn and indent <= fn_indent:
                in_threshold_fn = False

        if in_threshold_fn and not in_docstring and not stripped.startswith("#"):
            # Flag standalone numeric literals used in comparisons
            for match in re.finditer(r'(?<!["\'\w])(\d+\.?\d*)(?!["\'\w%])', line):
                val = match.group(1)
                # Skip 0 and 1 (common loop/boolean literals)
                if val in ("0", "1", "0.0", "1.0"):
                    continue
                # Skip version numbers and IDs
                if re.search(r'version|id|index|count|limit|offset', line, re.IGNORECASE):
                    continue
                # Skip calendar/weekday boundary (weekday() < 5 is not a threshold)
                if re.search(r'weekday\(\)', line):
                    continue
                # Skip .get() defaults (value comes from context, number is just a safe fallback)
                if re.search(r'\.get\s*\(', line):
                    continue
                # Skip SQL CASE math constants (THEN 100.0 ELSE 0.0 are not config thresholds)
                if re.search(r'THEN\s+\d|ELSE\s+\d', line):
                    continue
                result.add(
                    file, lineno, "R02-HARDCODED-THRESHOLD",
                    f"Numeric literal {val} in threshold function — read from policy_engine instead"
                )


# ---------------------------------------------------------------------------
# File walker
# ---------------------------------------------------------------------------

def lint_file(path: Path, repo_root: Path, result: LintResult) -> None:
    if _is_exempt(path, repo_root):
        return

    try:
        source = path.read_text(encoding="utf-8")
    except Exception:
        return

    rel = str(path.relative_to(repo_root))

    # AST-based checks
    try:
        tree = ast.parse(source, filename=str(path))
        check_llm_imports(tree, rel, result)
        check_cross_module_imports(tree, rel, result)
    except SyntaxError:
        pass  # Syntax errors reported by mypy/pylint

    # Regex-based checks
    check_role_literals(source, rel, result)
    check_status_updates(source, rel, result)
    check_numeric_thresholds(source, rel, result)


def lint_path(root: Path, repo_root: Path) -> LintResult:
    result = LintResult()
    for py_file in root.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        lint_file(py_file, repo_root, result)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="ALIS custom linter §12.4")
    parser.add_argument("path", nargs="?", default="ALIS/server",
                        help="Path to lint (default: ALIS/server)")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--max-violations", type=int, default=0,
                        help="Exit 0 if violations <= this number (for baseline tracking)")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent.resolve()
    lint_target = (repo_root / args.path).resolve()

    if not lint_target.exists():
        print(f"ERROR: path does not exist: {lint_target}", file=sys.stderr)
        return 2

    result = lint_path(lint_target, repo_root)

    if args.json:
        report = [
            {"file": v.file, "line": v.line, "rule": v.rule, "detail": v.detail}
            for v in result.violations
        ]
        print(json.dumps(report, indent=2))
    else:
        if result.violations:
            print(f"\nALIS Linter — {len(result.violations)} violation(s) found:\n")
            for v in result.violations:
                print(f"  {v.file}:{v.line}  [{v.rule}]  {v.detail}")
            print()
        else:
            print("ALIS Linter — no violations found.")

    if args.max_violations > 0 and len(result.violations) <= args.max_violations:
        return 0

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
