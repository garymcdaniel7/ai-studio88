#!/usr/bin/env python3
"""Artifact Integrity Verification — checksums for source-controlled artifacts.

Verifies that critical files (workflows, worker scripts, Dockerfiles) have not
been tampered with or unexpectedly changed without updating the manifest.

Usage:
    python scripts/security/verify_artifacts.py \
        --manifest=.security/artifact-checksums.yml \
        --report=/tmp/artifact-verification.json

Exit codes:
    0: All artifacts verified (or manifest uses VERIFY_ON_FIRST_RUN)
    1: Checksum mismatch detected
    2: Manifest missing or unparseable
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml


def compute_sha256(filepath: str) -> str | None:
    """Compute SHA-256 of a file. Returns None if file doesn't exist."""
    p = Path(filepath)
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(manifest_path: str, report_path: str) -> int:
    """Verify all artifacts in the manifest."""
    p = Path(manifest_path)
    if not p.exists():
        print(f"ERROR: Manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    with open(p) as f:
        manifest = yaml.safe_load(f) or {}

    results = []
    mismatches = []
    missing = []
    first_run = []

    # Collect all artifact entries
    all_artifacts = []
    for category in ["workflows", "scripts", "docker"]:
        for entry in manifest.get(category, []):
            all_artifacts.append(entry)

    for artifact in all_artifacts:
        path = artifact.get("path", "")
        expected = artifact.get("sha256", "")
        desc = artifact.get("description", "")

        actual = compute_sha256(path)

        if actual is None:
            missing.append({"path": path, "description": desc})
            results.append({
                "path": path,
                "status": "MISSING",
                "expected": expected,
                "actual": None,
            })
        elif expected == "VERIFY_ON_FIRST_RUN":
            first_run.append({"path": path, "sha256": actual})
            results.append({
                "path": path,
                "status": "FIRST_RUN",
                "actual": actual,
            })
        elif actual != expected:
            mismatches.append({"path": path, "expected": expected, "actual": actual})
            results.append({
                "path": path,
                "status": "MISMATCH",
                "expected": expected,
                "actual": actual,
            })
        else:
            results.append({
                "path": path,
                "status": "VERIFIED",
                "sha256": actual,
            })

    # Write report
    report = {
        "total": len(all_artifacts),
        "verified": len([r for r in results if r["status"] == "VERIFIED"]),
        "mismatches": len(mismatches),
        "missing": len(missing),
        "first_run": len(first_run),
        "results": results,
    }

    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  Artifact Integrity Report")
    print(f"{'='*60}")
    print(f"  Total artifacts: {report['total']}")
    print(f"  Verified: {report['verified']}")
    print(f"  First run (baseline needed): {report['first_run']}")
    print(f"  Missing: {report['missing']}")
    print(f"  MISMATCHES: {report['mismatches']}")

    if first_run:
        print(f"\n⚠️  First-run artifacts need baseline checksums:")
        for item in first_run:
            print(f"    {item['path']}: {item['sha256']}")
        print(f"\n  Update .security/artifact-checksums.yml with these values.")

    if mismatches:
        print(f"\n❌ CHECKSUM MISMATCHES (release blocked):")
        for m in mismatches:
            print(f"  - {m['path']}")
            print(f"    Expected: {m['expected'][:16]}...")
            print(f"    Actual:   {m['actual'][:16]}...")
        return 1

    if missing:
        print(f"\n⚠️  Missing artifacts (non-blocking if optional):")
        for m in missing:
            print(f"  - {m['path']}: {m['description']}")

    print(f"\n✅ Artifact integrity: PASS")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Verify artifact checksums")
    parser.add_argument("--manifest", required=True, help="Path to checksums YAML")
    parser.add_argument("--report", default="/tmp/artifact-verification.json", help="Report output path")
    args = parser.parse_args()

    exit_code = verify(args.manifest, args.report)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
