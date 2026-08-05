#!/usr/bin/env python3
"""Security Finding Evaluator — normalizes scanner output and applies severity policy.

Usage:
    python scripts/security/evaluate_findings.py \
        --tool=pip-audit \
        --input=/tmp/pip-audit-results.json \
        --policy=.security/severity-policy.yml \
        --exceptions=.security/exceptions.yml

Exit codes:
    0: No blocking findings (pass)
    1: Blocking findings detected (fail)
    2: Scanner output missing or unparseable (fail-safe)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import yaml


def load_yaml(path: str) -> dict:
    """Load a YAML file safely."""
    p = Path(path)
    if not p.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(2)
    with open(p) as f:
        return yaml.safe_load(f) or {}


def load_json(path: str) -> dict | list | None:
    """Load scanner JSON output."""
    p = Path(path)
    if not p.exists():
        print(f"WARNING: Scanner output not found: {path}", file=sys.stderr)
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"ERROR: Cannot parse {path}: {e}", file=sys.stderr)
        return None


def is_exception_valid(exc: dict) -> bool:
    """Check if an exception is currently active (not expired or revoked)."""
    if exc.get("status") != "active":
        return False
    expires = exc.get("expires_at", "")
    if not expires:
        return False
    try:
        expiry_date = datetime.strptime(str(expires), "%Y-%m-%d").date()
        return expiry_date >= date.today()
    except (ValueError, TypeError):
        return False


def normalize_pip_audit(data: dict | list) -> list[dict]:
    """Normalize pip-audit JSON to standard findings."""
    findings = []
    vulns = data if isinstance(data, list) else data.get("dependencies", [])
    for dep in vulns:
        if isinstance(dep, dict) and dep.get("vulns"):
            for vuln in dep["vulns"]:
                findings.append({
                    "tool": "pip-audit",
                    "id": vuln.get("id", "UNKNOWN"),
                    "severity": _map_pip_severity(vuln),
                    "package": dep.get("name", ""),
                    "version": dep.get("version", ""),
                    "description": vuln.get("description", "")[:200],
                    "fix_available": bool(vuln.get("fix_versions")),
                })
    return findings


def _map_pip_severity(vuln: dict) -> str:
    """Map pip-audit vulnerability to severity."""
    # pip-audit doesn't always include severity — default to high
    aliases = vuln.get("aliases", [])
    desc = vuln.get("description", "").lower()
    if "critical" in desc:
        return "critical"
    if "remote code execution" in desc or "rce" in desc:
        return "critical"
    return "high"  # Default conservative


def normalize_bandit(data: dict | list) -> list[dict]:
    """Normalize bandit JSON to standard findings."""
    findings = []
    results = data.get("results", []) if isinstance(data, dict) else data
    for r in results:
        severity = r.get("issue_severity", "MEDIUM").lower()
        confidence = r.get("issue_confidence", "MEDIUM").lower()
        # Only report high-confidence findings
        if confidence in ("high", "medium"):
            findings.append({
                "tool": "bandit",
                "id": r.get("test_id", ""),
                "severity": severity,
                "location": f"{r.get('filename', '')}:{r.get('line_number', '')}",
                "description": _redact_secrets(r.get("issue_text", "")[:200]),
                "fix_available": True,  # Code fixes are always possible
            })
    return findings


def normalize_trivy(data: dict | list) -> list[dict]:
    """Normalize Trivy JSON to standard findings."""
    findings = []
    results = data.get("Results", []) if isinstance(data, dict) else []
    for result in results:
        for vuln in result.get("Vulnerabilities", []):
            findings.append({
                "tool": "trivy",
                "id": vuln.get("VulnerabilityID", ""),
                "severity": vuln.get("Severity", "UNKNOWN").lower(),
                "package": vuln.get("PkgName", ""),
                "version": vuln.get("InstalledVersion", ""),
                "description": _redact_secrets(vuln.get("Title", "")[:200]),
                "fix_available": bool(vuln.get("FixedVersion")),
            })
    return findings


def _redact_secrets(text: str) -> str:
    """Remove potential secret values from finding descriptions."""
    import re
    # Redact anything that looks like a token, key, or password
    text = re.sub(r"(key|token|password|secret|credential)\s*[=:]\s*\S+", r"\1=***REDACTED***", text, flags=re.IGNORECASE)
    return text


def evaluate(tool: str, input_path: str, policy_path: str, exceptions_path: str) -> int:
    """Evaluate findings against policy. Returns exit code."""
    policy = load_yaml(policy_path)
    exceptions_data = load_yaml(exceptions_path)
    data = load_json(input_path)

    if data is None:
        print(f"FAIL-SAFE: Scanner output missing or unparseable for {tool}")
        return 2

    # Normalize findings based on tool
    normalizers = {
        "pip-audit": normalize_pip_audit,
        "bandit": normalize_bandit,
        "trivy": normalize_trivy,
    }
    normalizer = normalizers.get(tool)
    if not normalizer:
        print(f"Unknown tool: {tool}")
        return 2

    findings = normalizer(data)
    if not findings:
        print(f"✅ {tool}: No findings")
        return 0

    # Get blocking severities for this tool
    tool_key = {
        "pip-audit": "dependency",
        "bandit": "static_analysis",
        "trivy": "container",
    }.get(tool, tool)
    blocking_config = policy.get("blocking", {}).get(tool_key, {})
    block_on = set(blocking_config.get("block_on", []))

    # Load active exceptions
    active_exceptions = [
        e for e in exceptions_data.get("exceptions", [])
        if is_exception_valid(e) and e.get("tool") == tool
    ]
    excepted_ids = {e.get("finding") for e in active_exceptions}

    # Evaluate each finding
    blocking_findings = []
    advisory_findings = []

    for finding in findings:
        fid = finding.get("id", "")
        severity = finding.get("severity", "unknown")

        # Check if excepted
        if fid in excepted_ids:
            print(f"  ⚠️  EXCEPTED: {fid} ({severity}) — active exception")
            continue

        if severity in block_on or "any" in block_on:
            blocking_findings.append(finding)
        else:
            advisory_findings.append(finding)

    # Report
    print(f"\n{'='*60}")
    print(f"  {tool.upper()} Security Gate Report")
    print(f"{'='*60}")
    print(f"  Total findings: {len(findings)}")
    print(f"  Blocking: {len(blocking_findings)}")
    print(f"  Advisory: {len(advisory_findings)}")
    print(f"  Excepted: {len(findings) - len(blocking_findings) - len(advisory_findings)}")

    if blocking_findings:
        print(f"\n❌ BLOCKING FINDINGS ({len(blocking_findings)}):")
        for f in blocking_findings[:10]:  # Cap output
            print(f"  - [{f['severity'].upper()}] {f['id']}: {f.get('description', '')[:80]}")
        return 1

    print(f"\n✅ {tool}: Gate passed (no blocking findings)")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Evaluate security findings against policy")
    parser.add_argument("--tool", required=True, help="Scanner tool name")
    parser.add_argument("--input", required=True, help="Path to scanner JSON output")
    parser.add_argument("--policy", required=True, help="Path to severity policy YAML")
    parser.add_argument("--exceptions", required=True, help="Path to exceptions YAML")
    args = parser.parse_args()

    exit_code = evaluate(args.tool, args.input, args.policy, args.exceptions)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
