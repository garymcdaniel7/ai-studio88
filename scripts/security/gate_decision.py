#!/usr/bin/env python3
"""Security Gate Decision — aggregates scanner results and produces final verdict.

Evaluates all required scanners passed, checks for expired exceptions,
and produces machine-readable + human-readable evidence.

Usage:
    python scripts/security/gate_decision.py \
        --policy=.security/severity-policy.yml \
        --exceptions=.security/exceptions.yml \
        --commit=abc123 \
        --ref=refs/heads/main \
        --dependency-audit=success \
        --static-analysis=success \
        --secret-scan=success \
        --container-scan=success \
        --artifact-integrity=success

Exit codes:
    0: Gate PASSED — release may proceed
    1: Gate BLOCKED — findings violate policy
    2: Gate ERROR — required scanner failed to run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import yaml


def load_yaml(path: str) -> dict:
    """Load YAML safely."""
    p = Path(path)
    if not p.exists():
        return {}
    with open(p) as f:
        return yaml.safe_load(f) or {}


def check_expired_exceptions(exceptions_path: str) -> list[dict]:
    """Find exceptions that have expired (BLOCKS release)."""
    data = load_yaml(exceptions_path)
    expired = []
    for exc in data.get("exceptions", []):
        if exc.get("status") != "active":
            continue
        expires = exc.get("expires_at", "")
        if not expires:
            continue
        try:
            expiry_date = datetime.strptime(str(expires), "%Y-%m-%d").date()
            if expiry_date < date.today():
                expired.append(exc)
        except (ValueError, TypeError):
            expired.append(exc)  # Unparseable expiry = expired
    return expired


def main():
    parser = argparse.ArgumentParser(description="Security gate decision")
    parser.add_argument("--policy", required=True)
    parser.add_argument("--exceptions", required=True)
    parser.add_argument("--commit", default="unknown")
    parser.add_argument("--ref", default="unknown")
    parser.add_argument("--dependency-audit", default="skipped")
    parser.add_argument("--static-analysis", default="skipped")
    parser.add_argument("--secret-scan", default="skipped")
    parser.add_argument("--container-scan", default="skipped")
    parser.add_argument("--artifact-integrity", default="skipped")
    args = parser.parse_args()

    policy = load_yaml(args.policy)
    required_scanners = policy.get("required_scanners", [])
    advisory_scanners = policy.get("advisory_scanners", [])

    # Map job names to their results
    scanner_results = {
        "dependency-audit": args.dependency_audit,
        "static-analysis": args.static_analysis,
        "secret-scan": args.secret_scan,
        "container-scan": args.container_scan,
        "artifact-integrity": args.artifact_integrity,
    }

    # Check required scanners
    blocked_reasons = []
    for scanner in required_scanners:
        result = scanner_results.get(scanner, "skipped")
        if result == "failure":
            blocked_reasons.append(f"Required scanner FAILED: {scanner}")
        elif result == "skipped":
            blocked_reasons.append(f"Required scanner did not run: {scanner}")

    # Check expired exceptions
    expired = check_expired_exceptions(args.exceptions)
    for exc in expired:
        blocked_reasons.append(
            f"Exception EXPIRED: {exc.get('id', '?')} — {exc.get('finding', '?')} "
            f"(expired {exc.get('expires_at', '?')}). Must be renewed or finding fixed."
        )

    # Determine verdict
    if blocked_reasons:
        verdict = "BLOCKED"
        exit_code = 1
    else:
        verdict = "PASSED"
        exit_code = 0

    # Build decision record
    decision = {
        "verdict": verdict,
        "commit": args.commit,
        "ref": args.ref,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "scanner_results": scanner_results,
        "required_scanners": required_scanners,
        "advisory_scanners": advisory_scanners,
        "blocked_reasons": blocked_reasons,
        "expired_exceptions": [e.get("id") for e in expired],
        "policy_version": policy.get("version", "unknown"),
    }

    # Write evidence
    report_path = Path("/tmp/gate-decision.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(decision, f, indent=2)

    # Human-readable output
    print(f"\n{'='*60}")
    print(f"  🚦 SECURITY GATE: {verdict}")
    print(f"{'='*60}")
    print(f"  Commit: {args.commit[:12]}")
    print(f"  Ref: {args.ref}")
    print(f"  Policy: v{policy.get('version', '?')}")
    print(f"  Timestamp: {decision['timestamp']}")
    print()
    print("  Scanner Results:")
    for scanner, result in scanner_results.items():
        icon = "✅" if result == "success" else "❌" if result == "failure" else "⏭️"
        required = "REQUIRED" if scanner in required_scanners else "advisory"
        print(f"    {icon} {scanner}: {result} ({required})")

    if blocked_reasons:
        print(f"\n  ❌ BLOCKED ({len(blocked_reasons)} reason(s)):")
        for reason in blocked_reasons:
            print(f"    - {reason}")
    else:
        print(f"\n  ✅ All required checks passed. Release may proceed.")

    print(f"\n  Evidence: {report_path}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
