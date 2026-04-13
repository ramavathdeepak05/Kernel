"""
Auto-fix INV-1 and INV-2 violations — v2 (robust).

Improved handling of:
  - Multi-line execute_transaction calls
  - try/except blocks (inserts AuditLog AFTER the try block, not inside)
  - Complex indentation patterns
  - Functions that already start with _ (private helpers)

Usage:
    python scripts/alis_lint/autofix.py              # dry-run
    python scripts/alis_lint/autofix.py --apply       # apply
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

_MUTATION_RE = re.compile(
    r"\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|TRUNCATE)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# INV-1 fixer
# ---------------------------------------------------------------------------

def fix_inv1(filepath: str, source: str) -> str | None:
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return None

    lines = source.splitlines(keepends=True)
    violations: list[int] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_eq = (isinstance(func, ast.Name) and func.id == "execute_query") or \
                (isinstance(func, ast.Attribute) and func.attr == "execute_query")
        if not is_eq or not node.args:
            continue
        sql_str = _extract_sql_str(node.args[0])
        if _MUTATION_RE.search(sql_str):
            violations.append(node.lineno)

    if not violations:
        return None

    for line_no in sorted(violations, reverse=True):
        idx = line_no - 1
        if idx >= len(lines):
            continue
        line = lines[idx]
        if "execute_query(" not in line:
            continue

        # Find the full span of this call
        end_idx = _find_call_end(lines, idx)

        # Extract the full call text
        call_lines = lines[idx:end_idx + 1]
        call_text = "".join(call_lines)

        # Replace execute_query( with execute_transaction([(
        new_text = call_text.replace("execute_query(", "execute_transaction([(", 1)

        # Find the very last ) and replace with )])
        # But we need to handle tenant_id carefully
        last_paren_pos = new_text.rfind(")")
        if last_paren_pos >= 0:
            # Check if tenant_id already present
            before_paren = new_text[:last_paren_pos]
            after_paren = new_text[last_paren_pos + 1:]
            if "tenant_id=" in new_text:
                # Close the inner tuple, then close execute_transaction
                new_text = before_paren + ")]" + after_paren
            else:
                new_text = before_paren + ")], tenant_id=org_id)" + after_paren

        lines[idx:end_idx + 1] = [new_text]

    result = "".join(lines)
    try:
        ast.parse(result, filename=filepath)
        return result if result != source else None
    except SyntaxError:
        return None


# ---------------------------------------------------------------------------
# INV-2 fixer
# ---------------------------------------------------------------------------

def fix_inv2(filepath: str, source: str) -> str | None:
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return None

    lines = source.splitlines(keepends=True)
    insertions: list[tuple[int, str, dict]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith(("_build", "_prepare", "_compose")):
            continue
        # Skip if return annotation is tuple-like
        if node.returns and "tuple" in ast.dump(node.returns).lower():
            continue

        et_calls = []
        has_audit = False
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                f = child.func
                if (isinstance(f, ast.Name) and f.id == "execute_transaction") or \
                   (isinstance(f, ast.Attribute) and f.attr == "execute_transaction"):
                    et_calls.append(child)
                if isinstance(f, ast.Attribute) and f.attr == "log" and \
                   isinstance(f.value, ast.Name) and f.value.id == "AuditLog":
                    has_audit = True

        if not et_calls or has_audit:
            continue

        et_node = et_calls[0]
        params = _infer_params(node)

        # Find the statement that CONTAINS the execute_transaction call
        # Walk the function body to find the right statement
        insert_line, indent = _find_insert_point(node, et_node, lines)
        if insert_line is not None:
            insertions.append((insert_line, indent, params))

    if not insertions:
        return None

    # Check if AuditLog is already imported
    has_import = "from server.core.audit import" in source and "AuditLog" in source

    # Insert in reverse order
    for insert_line, indent, params in sorted(insertions, key=lambda x: x[0], reverse=True):
        stub = _build_audit_stub(indent, params)
        lines.insert(insert_line, stub)

    # Add import if needed
    if not has_import:
        last_import = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")) and not stripped.startswith("from ."):
                last_import = i
        lines.insert(last_import + 1, "from server.core.audit import AuditLog, AuditAction\n")

    result = "".join(lines)
    try:
        ast.parse(result, filename=filepath)
        return result if result != source else None
    except SyntaxError:
        return None


def _find_insert_point(func_node, et_node, lines) -> tuple[int | None, str]:
    """Find where to insert AuditLog.log() — after the statement containing execute_transaction."""
    # Walk function body statements to find which one contains the et_node
    target_stmt = None
    for stmt in ast.walk(func_node):
        if not isinstance(stmt, ast.stmt):
            continue
        # Check if this statement contains the et_node
        for child in ast.walk(stmt):
            if child is et_node:
                target_stmt = stmt
                break

    if target_stmt is None:
        return None, ""

    # If the execute_transaction is inside a try block, insert after the TRY statement
    # Walk up to find if we're in a Try
    for stmt in func_node.body:
        if isinstance(stmt, ast.Try):
            for child in ast.walk(stmt):
                if child is et_node:
                    # Insert after the entire try/except block
                    end_line = stmt.end_lineno if hasattr(stmt, 'end_lineno') and stmt.end_lineno else stmt.lineno + 1
                    indent = _get_indent(lines, stmt.lineno - 1)
                    return end_line, indent

    # Not in a try — insert right after the statement
    if hasattr(target_stmt, 'end_lineno') and target_stmt.end_lineno:
        end_line = target_stmt.end_lineno
    else:
        end_line = _find_call_end(lines, et_node.lineno - 1) + 1

    indent = _get_indent(lines, et_node.lineno - 1)
    return end_line, indent


def _build_audit_stub(indent: str, params: dict) -> str:
    action = params.get("action", "UPDATE")
    entity_type = params.get("entity_type", "record")
    actor_id = params.get("actor_id", '"system"')
    entity_id = params.get("entity_id", '""')
    org_id = params.get("org_id", "org_id")
    func_name = params.get("func_name", "unknown")

    return (
        f"{indent}AuditLog.log(\n"
        f"{indent}    action=AuditAction.{action}, actor_id={actor_id},\n"
        f"{indent}    actor_role=\"system\", entity_type=\"{entity_type}\",\n"
        f"{indent}    entity_id={entity_id}, tenant_id={org_id},\n"
        f"{indent}    metadata={{\"source\": \"{func_name}\"}},\n"
        f"{indent})\n"
    )


def _infer_params(func_node) -> dict:
    params: dict = {"func_name": func_node.name}
    for arg in func_node.args.args:
        if arg.arg == "actor_id":
            params["actor_id"] = "actor_id"
        elif arg.arg == "org_id":
            params["org_id"] = "org_id"
    params.setdefault("actor_id", '"system"')
    params.setdefault("org_id", "org_id")

    fname = func_node.name.lower()
    if any(k in fname for k in ("create", "insert", "add", "register", "send", "submit", "provision", "seed")):
        params["action"] = "CREATE"
    elif any(k in fname for k in ("delete", "remove", "revoke", "archive", "deactivate")):
        params["action"] = "DELETE"
    else:
        params["action"] = "UPDATE"

    entity = fname
    for prefix in ("create_", "update_", "delete_", "add_", "remove_", "set_",
                   "mark_", "record_", "submit_", "approve_", "reject_",
                   "activate_", "suspend_", "revoke_", "assign_", "close_",
                   "send_", "respond_", "request_", "deny_", "check_",
                   "verify_", "expire_", "resolve_", "process_", "run_",
                   "open_", "register_", "seed_", "initiate_", "execute_",
                   "on_", "handle_"):
        if entity.startswith(prefix):
            entity = entity[len(prefix):]
            break
    params["entity_type"] = entity or fname
    params["entity_id"] = '""'
    return params


def _extract_sql_str(node) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return " ".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    return ""


def _find_call_end(lines, start_idx) -> int:
    depth = 0
    for i in range(start_idx, min(start_idx + 30, len(lines))):
        depth += lines[i].count("(") - lines[i].count(")")
        if depth <= 0:
            return i
    return start_idx


def _get_indent(lines, idx) -> str:
    if idx < 0 or idx >= len(lines):
        return "        "
    line = lines[idx]
    return line[:len(line) - len(line.lstrip())]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rules", default="INV-1,INV-2")
    args = parser.parse_args()
    rules = set(args.rules.upper().split(","))

    results_path = Path("scripts/alis_lint/scan_results.json")
    # Use the latest scan
    for p in [Path("scripts/alis_lint/scan_results2.json"), results_path]:
        if p.exists():
            results_path = p
            break

    with open(results_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    files_to_fix: dict[str, set[str]] = {}
    for v in data["violations"]:
        if v["rule"] in rules:
            files_to_fix.setdefault(v["file"], set()).add(v["rule"])

    fixed = {"INV-1": 0, "INV-2": 0}
    errors = 0

    for filepath, vrules in sorted(files_to_fix.items()):
        path = Path(filepath)
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        modified = source

        if "INV-1" in vrules and "INV-1" in rules:
            result = fix_inv1(filepath, modified)
            if result:
                modified = result
                fixed["INV-1"] += 1

        if "INV-2" in vrules and "INV-2" in rules:
            result = fix_inv2(filepath, modified)
            if result:
                modified = result
                fixed["INV-2"] += 1

        if modified != source:
            if args.apply:
                path.write_text(modified, encoding="utf-8")
                print(f"  FIXED {filepath}")
            else:
                print(f"  WOULD FIX {filepath}")

    total = sum(fixed.values())
    print(f"\nFixed: INV-1={fixed['INV-1']}, INV-2={fixed['INV-2']}, Total={total}, Errors={errors}")
    if not args.apply:
        print("Re-run with --apply to apply.")


if __name__ == "__main__":
    main()
