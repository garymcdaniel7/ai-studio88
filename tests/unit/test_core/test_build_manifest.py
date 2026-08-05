"""Worker build manifest verification tests — Story 050.

Tests prove:
  - Manifest exists and is valid YAML
  - All required sections are present
  - Base image has digest pin
  - Repositories have commit pins
  - Python packages have version pins
  - Binaries have checksum entries
  - Models have checksum entries
  - Unverified remote execution (curl|sh) is flagged
  - License/provenance metadata is tracked
  - Verification script catches missing pins
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

# Import the verification module
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "scripts" / "security"))
from verify_build_manifest import validate_manifest, REQUIRED_SECTIONS, UNVERIFIED_MARKER


REPO_ROOT = Path(__file__).parent.parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "docker" / "comfyui-worker" / "build-manifest.yml"


# =============================================================================
# Manifest Existence and Structure
# =============================================================================


@pytest.mark.unit
class TestManifestStructure:
    """Verify the manifest exists and has required sections."""

    def test_manifest_file_exists(self):
        assert MANIFEST_PATH.exists(), "Build manifest not found"

    def test_manifest_is_valid_yaml(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)

    def test_manifest_has_version(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        assert "version" in data

    def test_manifest_has_required_sections(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        for section in REQUIRED_SECTIONS:
            assert section in data, f"Missing required section: {section}"


# =============================================================================
# Base Image Pinning
# =============================================================================


@pytest.mark.unit
class TestBaseImagePinning:
    """Verify base image is pinned by digest."""

    def test_base_image_has_digest(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        base = data["base_image"]
        assert "digest" in base, "Base image must have a digest pin"
        assert base["digest"], "Digest must not be empty"

    def test_base_image_has_repository(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        assert data["base_image"]["repository"] == "pytorch/pytorch"

    def test_base_image_has_tag(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        assert "cuda" in data["base_image"]["tag"]


# =============================================================================
# Repository Commit Pinning
# =============================================================================


@pytest.mark.unit
class TestRepositoryPinning:
    """Verify git repositories are pinned by commit."""

    def test_comfyui_has_commit(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        assert "commit" in data["repositories"]["comfyui"]
        assert data["repositories"]["comfyui"]["commit"]  # Non-empty

    def test_comfyui_manager_has_commit(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        assert "commit" in data["repositories"]["comfyui_manager"]

    def test_simpletuner_has_commit(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        assert "commit" in data["repositories"]["simpletuner"]

    def test_all_repos_have_url(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        for name, repo in data["repositories"].items():
            assert "url" in repo, f"Repository '{name}' missing URL"
            assert repo["url"].startswith("https://"), f"Repository '{name}' URL not HTTPS"


# =============================================================================
# Python Package Version Pinning
# =============================================================================


@pytest.mark.unit
class TestPythonPackagePinning:
    """Verify Python packages have explicit version pins."""

    def test_all_packages_have_versions(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        for pkg in data["python_packages"]:
            name = pkg.get("name", "unknown")
            assert "version" in pkg, f"Package '{name}' missing version"
            assert pkg["version"], f"Package '{name}' version is empty"

    def test_critical_packages_pinned(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        pkg_names = {p["name"] for p in data["python_packages"]}
        assert "fastapi" in pkg_names
        assert "huggingface-hub" in pkg_names
        assert "uvicorn" in pkg_names


# =============================================================================
# Binary Integrity
# =============================================================================


@pytest.mark.unit
class TestBinaryIntegrity:
    """Verify binaries have checksums and sources."""

    def test_ollama_has_checksum(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        assert "ollama" in data["binaries"]
        assert "sha256" in data["binaries"]["ollama"]

    def test_ollama_has_source_url(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        assert data["binaries"]["ollama"]["source"].startswith("https://")

    def test_ollama_not_installed_via_pipe_sh(self):
        """The manifest must replace curl|sh with direct binary download."""
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        ollama = data["binaries"]["ollama"]
        # Source should be a direct binary URL, not an install script
        assert "install.sh" not in ollama["source"]


# =============================================================================
# Model Checksums
# =============================================================================


@pytest.mark.unit
class TestModelChecksums:
    """Verify model artifacts have integrity metadata."""

    def test_models_have_checksums(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        for name, model in data.get("models", {}).items():
            assert "sha256" in model, f"Model '{name}' missing SHA-256"

    def test_models_have_sources(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        for name, model in data.get("models", {}).items():
            assert "source" in model, f"Model '{name}' missing source"

    def test_models_have_licenses(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        for name, model in data.get("models", {}).items():
            assert "license" in model, f"Model '{name}' missing license"


# =============================================================================
# Verification Script Logic
# =============================================================================


@pytest.mark.unit
class TestVerificationScript:
    """Verify the verification script catches issues."""

    def test_missing_manifest_returns_error(self):
        errors, _, _ = validate_manifest("/nonexistent/path.yml")
        assert len(errors) > 0

    def test_empty_manifest_returns_errors(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("{}")
            f.flush()
            errors, _, _ = validate_manifest(f.name)
        os.unlink(f.name)
        assert len(errors) >= len(REQUIRED_SECTIONS)

    def test_valid_manifest_pinned_items_counted(self):
        """Our actual manifest should have pinned items in info."""
        errors, warnings, info = validate_manifest(str(MANIFEST_PATH))
        # Should have at least some pinned items (even if VERIFY_ON_FIRST_BUILD)
        assert len(info) + len(warnings) > 0

    def test_unverified_marker_produces_warning(self):
        """VERIFY_ON_FIRST_BUILD entries produce warnings, not errors."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump({
                "base_image": {"repository": "test", "tag": "latest", "digest": UNVERIFIED_MARKER},
                "repositories": {},
                "python_packages": [],
                "binaries": {},
                "build": {"sbom_format": "cyclonedx", "scan_tool": "trivy"},
            }, f)
            f.flush()
            errors, warnings, _ = validate_manifest(f.name)
        os.unlink(f.name)
        # VERIFY_ON_FIRST_BUILD should be a warning, not an error
        assert any("initial verification" in w for w in warnings)


# =============================================================================
# Build Metadata
# =============================================================================


@pytest.mark.unit
class TestBuildMetadata:
    """Verify build metadata is present."""

    def test_sbom_format_specified(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        assert data["build"]["sbom_format"] == "cyclonedx"

    def test_scan_tool_specified(self):
        with open(MANIFEST_PATH) as f:
            data = yaml.safe_load(f)
        assert data["build"]["scan_tool"] == "trivy"
