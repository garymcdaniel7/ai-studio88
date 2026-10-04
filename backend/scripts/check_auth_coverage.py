"""Enforce per-category auth coverage floors from a coverage.py JSON report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_FILES = (
    "backend/app/core/auth_policy.py",
    "backend/app/core/middleware.py",
    "backend/auth.py",
)


def main() -> int:
    """Check line and branch coverage for each security-boundary file."""
    parser = argparse.ArgumentParser()
    parser.add_argument("coverage_json", type=Path, help="coverage.py --cov-report=json file")
    parser.add_argument("--minimum", type=float, default=80.0)
    args = parser.parse_args()
    data = json.loads(args.coverage_json.read_text(encoding="utf-8"))
    files = data.get("files", {})
    failures: list[str] = []
    for path in REQUIRED_FILES:
        metrics = files.get(path, {}).get("summary")
        if not metrics:
            failures.append(f"{path}: missing from coverage report")
            continue
        line = (
            float(metrics.get("covered_lines", 0))
            / float(metrics.get("num_statements", 1))
            * 100
        )
        if line < args.minimum:
            failures.append(f"{path}: line coverage {line:.1f}% < {args.minimum:.1f}%")
        # coverage.py JSON reports branch counts rather than a separate percentage.
        branch_total = int(metrics.get("num_branches", 0))
        branch = (
            float(metrics.get("covered_branches", 0)) / branch_total * 100
            if branch_total
            else 0.0
        )
        if branch < args.minimum:
            failures.append(f"{path}: branch coverage {branch:.1f}% < {args.minimum:.1f}%")
    if failures:
        print("AUTH_COVERAGE_GATE=BLOCKED")
        print("\n".join(failures))
        return 1
    print(f"AUTH_COVERAGE_GATE=UNIT-READY minimum={args.minimum:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
