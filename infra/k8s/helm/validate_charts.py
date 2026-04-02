"""
S6 Helm Chart Structural Validator

Validates chart structure, required files, and template correctness
without requiring helm CLI. Run: python validate_charts.py
"""
import os
import sys
import re
from pathlib import Path

CHARTS_DIR = Path(__file__).parent
CHARTS = ["alis-data-plane", "alis-control-plane", "alis-ai-service"]
ERRORS = []
WARNINGS = []


def error(chart: str, msg: str):
    ERRORS.append(f"  [ERROR] {chart}: {msg}")


def warn(chart: str, msg: str):
    WARNINGS.append(f"  [WARN]  {chart}: {msg}")


def ok(chart: str, msg: str):
    print(f"  [OK]    {chart}: {msg}")


def validate_chart(name: str):
    chart_dir = CHARTS_DIR / name
    if not chart_dir.is_dir():
        error(name, f"Chart directory not found: {chart_dir}")
        return

    # 1. Required files
    for req in ["Chart.yaml", "values.yaml"]:
        if (chart_dir / req).exists():
            ok(name, f"{req} exists")
        else:
            error(name, f"Missing required file: {req}")

    # 2. Templates directory
    tpl_dir = chart_dir / "templates"
    if not tpl_dir.is_dir():
        error(name, "Missing templates/ directory")
        return
    ok(name, "templates/ directory exists")

    # 3. _helpers.tpl
    if (tpl_dir / "_helpers.tpl").exists():
        ok(name, "_helpers.tpl exists")
    else:
        warn(name, "Missing _helpers.tpl (optional but recommended)")

    # 4. Template files are valid YAML-ish (check for common issues)
    template_files = list(tpl_dir.glob("*.yaml")) + list(tpl_dir.glob("*.yml"))
    ok(name, f"{len(template_files)} template file(s) found")

    for tf in template_files:
        content = tf.read_text(encoding="utf-8")

        # Check for unbalanced {{ }}
        opens = content.count("{{")
        closes = content.count("}}")
        if opens != closes:
            error(name, f"{tf.name}: unbalanced template delimiters ({{ {opens} vs }} {closes})")

        # Check for apiVersion
        if "apiVersion:" in content:
            ok(name, f"{tf.name}: has apiVersion")
        elif tf.name != "_helpers.tpl":
            warn(name, f"{tf.name}: missing apiVersion (might be conditional)")

        # Check for kind
        if "kind:" in content:
            ok(name, f"{tf.name}: has kind")
        elif tf.name != "_helpers.tpl":
            warn(name, f"{tf.name}: missing kind")

    # 5. Chart.yaml has required fields
    chart_yaml = (chart_dir / "Chart.yaml").read_text(encoding="utf-8")
    for field in ["apiVersion:", "name:", "version:", "appVersion:"]:
        if field in chart_yaml:
            ok(name, f"Chart.yaml has {field.rstrip(':')}")
        else:
            error(name, f"Chart.yaml missing {field.rstrip(':')}")

    # 6. values.yaml has image config
    values = (chart_dir / "values.yaml").read_text(encoding="utf-8")
    if "repository:" in values:
        ok(name, "values.yaml has image repository")
    else:
        warn(name, "values.yaml missing image repository")

    # 7. Data plane specific checks
    if name == "alis-data-plane":
        expected_templates = [
            "deployment.yaml", "service.yaml", "ingress.yaml",
            "hpa.yaml", "pdb.yaml", "configmap.yaml", "secret.yaml",
            "serviceaccount.yaml", "networkpolicy.yaml",
            "celery-worker.yaml", "celery-beat.yaml",
        ]
        for et in expected_templates:
            if (tpl_dir / et).exists():
                ok(name, f"template {et} present")
            else:
                error(name, f"Missing expected template: {et}")

        # Check celery-beat is Recreate strategy (singleton)
        beat = (tpl_dir / "celery-beat.yaml").read_text(encoding="utf-8")
        if "Recreate" in beat:
            ok(name, "celery-beat uses Recreate strategy (singleton)")
        else:
            warn(name, "celery-beat should use Recreate strategy")

        # Check worker has terminationGracePeriodSeconds
        worker = (tpl_dir / "celery-worker.yaml").read_text(encoding="utf-8")
        if "terminationGracePeriodSeconds" in worker:
            ok(name, "celery-worker has terminationGracePeriodSeconds")
        else:
            warn(name, "celery-worker missing terminationGracePeriodSeconds")


def main():
    print("=" * 60)
    print("ALIS Helm Chart Validation — S6")
    print("=" * 60)

    for chart in CHARTS:
        print(f"\n--- {chart} ---")
        validate_chart(chart)

    print("\n" + "=" * 60)
    if WARNINGS:
        print(f"\nWarnings ({len(WARNINGS)}):")
        for w in WARNINGS:
            print(w)

    if ERRORS:
        print(f"\nErrors ({len(ERRORS)}):")
        for e in ERRORS:
            print(e)
        print(f"\nFAILED — {len(ERRORS)} error(s)")
        return 1
    else:
        print(f"\nPASSED — 0 errors, {len(WARNINGS)} warning(s)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
