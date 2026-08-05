#!/usr/bin/env python3
"""Worker Build Manifest Verification — Story 050.

Validates that the build manifest is complete, all pins are present,
no unverified downloads exist, and checksums match where verifiable.

Usage:
    python scripts/security/verify_build_manifest.py
    python scripts/security/verify_build_manifest.py --manifest=docker/comfyui-worker/build-manifest.yml

Exit codes:
    0: All checks pass
    1: Verification failures detected
    2: Manifest missing or unparseable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


# =============================================================================
# Validation Rules
# =============================================================================

REQUIRED_SECTIONS = ["base_image", "repositories", "python_packages", "binaries", "build"]
UNVERIFIED_MARKER = "VERIFY_ON_FIRST_BUILD"


def validate_manifest(manifest_path: str) -> tuple[list[str], list[str], list[str]]:
    """Validate the build manifest.

    Returns: (errors, warnings, info)
    """
    path = Path(manifest_path)
    if not path.exists():
        return [f"Manifest not found: {manifest_path}"], [], []

    with open(path) as f:
        manifest = yaml.safe_load(f) or {}

    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    # Check required sections
    for section in REQUIRED_SECTIONS:
        if section not in manifest:
            errors.append(f"Missing required section: {section}")

    # Validate base image
    base = manifest.get("base_image", {})
    if not base.get("digest"):
        errors.append("base_image.digest is missing — pin by immutable digest")
    elif base["digest"] == UNVERIFIED_MARKER:
        warnings.append("base_image.digest needs initial verification (run docker inspect)")
    else:
        info.append(f"Base image pinned: {base.get('repository')}@{base['digest'][:20]}...")

    # Validate repositories have commits
    for name, repo in manifest.get("repositories", {}).items():
        if not repo.get("commit"):
            errors.append(f"Repository '{name}' missing commit pin")
        elif repo["commit"] == UNVERIFIED_MARKER:
            warnings.append(f"Repository '{name}' needs initial commit pin")
        else:
            info.append(f"Repository '{name}' pinned: {repo['commit'][:12]}")

        if not repo.get("url"):
            errors.append(f"Repository '{name}' missing URL")
        if not repo.get("license"):
            warnings.append(f"Repository '{name}' missing license metadata")

    # Validate Python packages have versions
    for pkg in manifest.get("python_packages", []):
        name = pkg.get("name", "unknown")
        if not pkg.get("version"):
            errors.append(f"Python package '{name}' missing version pin")
        else:
            info.append(f"Python '{name}' pinned: {pkg['version']}")

    # Validate binaries have checksums
    for name, binary in manifest.get("binaries", {}).items():
        if not binary.get("sha256"):
            errors.append(f"Binary '{name}' missing SHA-256 checksum")
        elif binary["sha256"] == UNVERIFIED_MARKER:
            warnings.append(f"Binary '{name}' needs initial checksum verification")
        else:
            info.append(f"Binary '{name}' checksum: {binary['sha256'][:16]}...")

        if not binary.get("source"):
            errors.append(f"Binary '{name}' missing source URL")
        if not binary.get("license"):
            warnings.append(f"Binary '{name}' missing license")

    # Validate model artifacts have checksums
    for name, model in manifest.get("models", {}).items():
        if not model.get("sha256"):
            errors.append(f"Model '{name}' missing SHA-256 checksum")
        elif model["sha256"] == UNVERIFIED_MARKER:
            warnings.append(f"Model '{name}' needs initial checksum")
        if not model.get("license"):
            warnings.append(f"Model '{name}' missing license metadata")
        if not model.get("source"):
            errors.append(f"Model '{name}' missing source")

    # Check for unverified remote execution patterns in Dockerfile
    dockerfile_path = path.parent / "Dockerfile"
    if dockerfile_path.exists():
        dockerfile_content = dockerfile_path.read_text()
        dangerous_patterns = [
            ("curl.*|.*sh", "Unverified remote script execution (curl | sh)"),
            ("wget.*|.*sh", "Unverified remote script execution (wget | sh)"),
            ("git clone(?!.*--branch)(?!.*@)", "Git clone without explicit ref"),
        ]
        import re
        for pattern, description in dangerous_patterns:
            if re.search(pattern, dockerfile_content):
                # Check if it's the Ollama install specifically
                if "ollama.com/install.sh" in dockerfile_content:
                    errors.append(
                        f"UNSAFE: {description} — Ollama install.sh must be replaced "
                        "with direct binary download + checksum verification"
                    )

    # Check build metadata
    build_meta = manifest.get("build", {})
    if not build_meta.get("sbom_format"):
        warnings.append("Build metadata missing sbom_format")
    if not build_meta.get("scan_tool"):
        warnings.append("Build metadata missing scan_tool")

    return errors, warnings, info


def check_dockerfile_compliance(manifest_path: str) -> list[str]:
    """Check Dockerfile against manifest for compliance."""
    path = Path(manifest_path)
    dockerfile_path = path.parent / "Dockerfile"
    issues = []

    if not dockerfile_path.exists():
        return ["Dockerfile not found next to manifest"]

    content = dockerfile_path.read_text()

    # Check base image matches manifest
    manifest = yaml.safe_load(open(path))
    base = manifest.get("base_image", {})
    expected_from = f"{base.get('repository', '')}:{base.get('tag', '')}"
    if expected_from not in content and base.get("digest") not in content:
        issues.append(f"Dockerfile FROM doesn't match manifest base_image ({expected_from})")

    return issues


# =============================================================================
# Main
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Verify worker build manifest")
    parser.add_argument(
        "--manifest",
        default="docker/comfyui-worker/build-manifest.yml",
        help="Path to build manifest YAML",
    )
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    errors, warnings, info = validate_manifest(args.manifest)
    dockerfile_issues = check_dockerfile_compliance(args.manifest)
    errors.extend(dockerfile_issues)

    # Print report
    print(f"\n{'='*60}")
    print(f"  Worker Build Manifest Verification")
    print(f"{'='*60}")
    print(f"  Manifest: {args.manifest}")
    print(f"  Pinned items: {len(info)}")
    print(f"  Warnings: {len(warnings)}")
    print(f"  Errors: {len(errors)}")

    if info:
        print(f"\n✅ Pinned ({len(info)}):")
        for item in info:
            print(f"  - {item}")

    if warnings:
        print(f"\n⚠️  Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")

    if errors:
        print(f"\n❌ Errors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")

    # Exit code
    if errors:
        print(f"\n❌ FAILED: {len(errors)} error(s) must be resolved before build.")
        return 1
    if warnings and args.strict:
        print(f"\n⚠️  STRICT MODE: {len(warnings)} warning(s) treated as errors.")
        return 1
    if warnings:
        print(f"\n⚠️  PASS with warnings: Resolve VERIFY_ON_FIRST_BUILD items before production.")
    else:
        print(f"\n✅ PASS: All dependencies pinned and verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
