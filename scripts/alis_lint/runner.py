"""
ALIS Architectural Linter — CLI runner.

Usage:
    python scripts/alis_lint/runner.py [paths...]             # scan specific files/dirs
    python scripts/alis_lint/runner.py ALIS/server/           # scan entire backend
    python scripts/alis_lint/runner.py --format json          # machine-readable
    python scripts/alis_lint/runner.py --rules INV-1,INV-3    # run only specific rules
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .report import LintResult, Rule, format_console, format_json
from . import checker_mutations, checker_audit, checker_lateral


CHECKERS = {
    Rule.INV1_MUTATION_VIA_QUERY: checker_mutations,
    Rule.INV2_MISSING_AUDIT:      checker_audit,
    Rule.INV3_LATERAL_IMPORT:     checker_lateral,
}


def collect_python_files(paths: list[str]) -> list[Path]:
    """Collect all .py files from the given paths."""
    files: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix == ".py":
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
    # Exclude __pycache__, migrations, tests, .venv
    return [
        f for f in files
        if "__pycache__" not in str(f)
        and ".venv" not in str(f)
        and "migrations" not in str(f)
    ]


def run(paths: list[str], rules: set[Rule] | None = None) -> LintResult:
    """Run all (or selected) checkers on the given paths."""
    files = collect_python_files(paths)
    result = LintResult()

    active_checkers = {
        rule: checker
        for rule, checker in CHECKERS.items()
        if rules is None or rule in rules
    }

    for filepath in files:
        try:
            source = filepath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for rule, checker in active_checkers.items():
            file_result = checker.check_file(str(filepath), source)
            result.merge(file_result)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="alis-lint",
        description="ALIS Architectural Linter — enforces core invariants",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["ALIS/server/"],
        help="Files or directories to scan (default: ALIS/server/)",
    )
    parser.add_argument(
        "--format",
        choices=["console", "json"],
        default="console",
        help="Output format (default: console)",
    )
    parser.add_argument(
        "--rules",
        type=str,
        default=None,
        help="Comma-separated rules to check (e.g. INV-1,INV-3)",
    )

    args = parser.parse_args()

    # Parse rules filter
    rules = None
    if args.rules:
        rules = set()
        for r in args.rules.split(","):
            r = r.strip().upper()
            try:
                rules.add(Rule(r))
            except ValueError:
                print(f"Unknown rule: {r}", file=sys.stderr)
                sys.exit(2)

    t0 = time.perf_counter()
    result = run(args.paths, rules)
    dt = time.perf_counter() - t0

    if args.format == "json":
        print(format_json(result))
    else:
        files_count = len(collect_python_files(args.paths))
        print(f"\n  Scanned {files_count} files in {dt:.1f}s\n")
        print(format_console(result))

    sys.exit(1 if result.has_errors else 0)


if __name__ == "__main__":
    main()
