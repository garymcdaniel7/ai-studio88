"""Unit tests for ScalabilityVerificationService.

Tests the scalability architecture verification logic:
- User growth independent of GPU scaling (R91.1, R76.8)
- Job transport replaceable without API contract change (R91.3, R76.10)
- Backend stateless behind load balancer (R7.5)
- Scaling documentation exists (R91.4)

Validates: Requirements R91.1, R91.3, R91.4, R76.8, R76.10
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from app.schemas.scalability import (
    ScalabilityVerdict,
    ScalingDirection,
)
from app.services.scalability_verification_service import (
    ScalabilityVerificationService,
)


@pytest.mark.unit
class TestVerifyUserGpuIndependence:
    """Tests for verify_user_gpu_independence().

    Validates: R91.1, R76.8 — user growth does not require GPU scaling.
    """

    def test_passes_when_user_paths_have_no_gpu_imports(self, tmp_path: Path) -> None:
        """User auth/CRUD modules with no GPU imports → pass."""
        # Create a minimal project structure
        backend_dir = tmp_path / "backend"
        app_dir = backend_dir / "app"

        # Create user-path modules without GPU imports
        (app_dir / "core").mkdir(parents=True)
        (app_dir / "core" / "security.py").write_text(
            "from datetime import datetime\nimport jwt\n"
        )
        (app_dir / "core" / "dependencies.py").write_text(
            "from fastapi import Depends\nfrom app.core.security import decode\n"
        )
        (app_dir / "services").mkdir(parents=True)
        (app_dir / "services" / "talent_service.py").write_text(
            "from uuid import UUID\nclass TalentService:\n    pass\n"
        )
        (app_dir / "services" / "provisioning_service.py").write_text(
            "class ProvisioningService:\n    pass\n"
        )

        service = ScalabilityVerificationService(project_root=tmp_path)
        result = service.verify_user_gpu_independence()

        assert result.verified is True
        assert result.verdict == ScalabilityVerdict.PASS
        assert result.property_name == "user_gpu_independence"
        assert "R91.1" in result.requirement_ids
        assert "R76.8" in result.requirement_ids

    def test_fails_when_user_path_imports_gpu_provider(self, tmp_path: Path) -> None:
        """User auth module importing GPU provider → fail."""
        backend_dir = tmp_path / "backend"
        app_dir = backend_dir / "app"

        (app_dir / "core").mkdir(parents=True)
        # This module imports a GPU provider — violation!
        (app_dir / "core" / "security.py").write_text(
            "from app.providers.compute import ComputeProvider\nimport jwt\n"
        )
        (app_dir / "services").mkdir(parents=True)
        (app_dir / "services" / "talent_service.py").write_text(
            "class TalentService:\n    pass\n"
        )

        service = ScalabilityVerificationService(project_root=tmp_path)
        result = service.verify_user_gpu_independence()

        assert result.verified is False
        assert result.verdict == ScalabilityVerdict.FAIL
        assert any("imports" in e for e in result.evidence)

    def test_handles_missing_modules_gracefully(self, tmp_path: Path) -> None:
        """Missing modules are skipped, not treated as failures."""
        # Empty project — no modules exist
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        service = ScalabilityVerificationService(project_root=tmp_path)
        result = service.verify_user_gpu_independence()

        # Should pass since no violations are found (modules don't exist)
        assert result.verified is True
        assert result.verdict == ScalabilityVerdict.PASS
        assert any("not found" in e for e in result.evidence)


@pytest.mark.unit
class TestVerifyJobTransportReplaceability:
    """Tests for verify_job_transport_replaceability().

    Validates: R91.3, R76.10 — job transport is replaceable.
    """

    def test_passes_with_interface_and_service_layer(self, tmp_path: Path) -> None:
        """ComputeProvider Protocol + JobService + no direct provider imports → pass."""
        backend_dir = tmp_path / "backend"
        app_dir = backend_dir / "app"

        # Create ComputeProvider interface
        (app_dir / "providers").mkdir(parents=True)
        (app_dir / "providers" / "compute.py").write_text(
            "from typing import Protocol\n\n"
            "class ComputeProvider(Protocol):\n"
            "    async def provision(self) -> None: ...\n"
        )

        # Create JobService
        (app_dir / "services").mkdir(parents=True)
        (app_dir / "services" / "job_service.py").write_text(
            "class JobService:\n    pass\n"
        )

        # Create endpoint that uses service layer (not direct provider)
        (app_dir / "api" / "v1" / "endpoints").mkdir(parents=True)
        (app_dir / "api" / "v1" / "endpoints" / "jobs.py").write_text(
            "from app.services.job_service import JobService\n"
        )

        service = ScalabilityVerificationService(project_root=tmp_path)
        result = service.verify_job_transport_replaceability()

        assert result.verified is True
        assert result.verdict == ScalabilityVerdict.PASS
        assert "R91.3" in result.requirement_ids
        assert "R76.10" in result.requirement_ids

    def test_fails_when_endpoint_imports_specific_provider(self, tmp_path: Path) -> None:
        """Endpoint importing specific provider directly → fail."""
        backend_dir = tmp_path / "backend"
        app_dir = backend_dir / "app"

        # Create ComputeProvider interface
        (app_dir / "providers").mkdir(parents=True)
        (app_dir / "providers" / "compute.py").write_text(
            "from typing import Protocol\n\nclass ComputeProvider(Protocol):\n    pass\n"
        )

        # Create JobService
        (app_dir / "services").mkdir(parents=True)
        (app_dir / "services" / "job_service.py").write_text("class JobService:\n    pass\n")

        # Endpoint imports a specific provider — violation!
        (app_dir / "api" / "v1" / "endpoints").mkdir(parents=True)
        (app_dir / "api" / "v1" / "endpoints" / "generate.py").write_text(
            "import runpod\n\nasync def generate(): pass\n"
        )

        service = ScalabilityVerificationService(project_root=tmp_path)
        result = service.verify_job_transport_replaceability()

        assert result.verified is False
        assert result.verdict == ScalabilityVerdict.FAIL

    def test_fails_when_no_compute_provider_interface(self, tmp_path: Path) -> None:
        """Missing ComputeProvider interface → fail."""
        backend_dir = tmp_path / "backend"
        app_dir = backend_dir / "app"

        # No providers directory
        (app_dir / "services").mkdir(parents=True)
        (app_dir / "services" / "job_service.py").write_text("class JobService:\n    pass\n")

        (app_dir / "api" / "v1" / "endpoints").mkdir(parents=True)
        (app_dir / "api" / "v1" / "endpoints" / "jobs.py").write_text("pass\n")

        service = ScalabilityVerificationService(project_root=tmp_path)
        result = service.verify_job_transport_replaceability()

        assert result.verified is False
        assert result.verdict == ScalabilityVerdict.FAIL


@pytest.mark.unit
class TestVerifyBackendStatelessness:
    """Tests for verify_backend_statelessness().

    Validates: R91.4, R7.5 — backend is stateless.
    """

    def test_passes_with_no_mutable_state(self, tmp_path: Path) -> None:
        """Clean modules with no mutable state → pass."""
        backend_dir = tmp_path / "backend"
        app_dir = backend_dir / "app"

        (app_dir / "services").mkdir(parents=True)
        (app_dir / "services" / "talent_service.py").write_text(
            '"""Service module."""\n\n'
            "from app.core.logging import get_logger\n\n"
            "logger = get_logger(__name__)\n\n"
            "MAX_ITEMS = 100\n\n"
            "class TalentService:\n"
            "    def __init__(self):\n"
            "        self.items = {}\n"
        )

        (app_dir / "core").mkdir(parents=True)
        (app_dir / "core" / "config.py").write_text(
            "from pydantic import BaseModel\n\n"
            "class Settings(BaseModel):\n"
            "    debug: bool = False\n"
        )

        (app_dir / "api" / "v1" / "endpoints").mkdir(parents=True)
        (app_dir / "api" / "v1" / "endpoints" / "talent.py").write_text(
            "from fastapi import APIRouter\n\n"
            "router = APIRouter()\n\n"
            "@router.get('/talent')\n"
            "async def list_talent(): pass\n"
        )

        service = ScalabilityVerificationService(project_root=tmp_path)
        result = service.verify_backend_statelessness()

        assert result.verified is True
        assert result.verdict == ScalabilityVerdict.PASS

    def test_detects_module_level_mutable_dict(self, tmp_path: Path) -> None:
        """Module-level mutable dict assignment → detected."""
        backend_dir = tmp_path / "backend"
        app_dir = backend_dir / "app"

        (app_dir / "services").mkdir(parents=True)
        (app_dir / "services" / "bad_service.py").write_text(
            '"""Bad service with mutable state."""\n\n'
            "user_sessions = {}\n\n"
            "class BadService:\n"
            "    pass\n"
        )

        service = ScalabilityVerificationService(project_root=tmp_path)
        result = service.verify_backend_statelessness()

        # Should detect the mutable state
        assert result.verdict in (ScalabilityVerdict.WARN, ScalabilityVerdict.FAIL)
        assert any("user_sessions" in e for e in result.evidence)

    def test_ignores_constants_and_safe_patterns(self, tmp_path: Path) -> None:
        """UPPER_CASE constants, logger, router are safe and ignored."""
        backend_dir = tmp_path / "backend"
        app_dir = backend_dir / "app"

        (app_dir / "services").mkdir(parents=True)
        (app_dir / "services" / "safe_service.py").write_text(
            "from app.core.logging import get_logger\n\n"
            "logger = get_logger(__name__)\n"
            "MAX_RETRIES = 3\n"
            "ALLOWED_TYPES = {}\n"
            "_INTERNAL_CACHE = {}\n"
        )

        (app_dir / "core").mkdir(parents=True)
        (app_dir / "core" / "__init__.py").write_text("")

        service = ScalabilityVerificationService(project_root=tmp_path)
        result = service.verify_backend_statelessness()

        # Constants and safe patterns should not trigger warnings
        assert result.verdict == ScalabilityVerdict.PASS


@pytest.mark.unit
class TestVerifyScalingDocumentation:
    """Tests for verify_scaling_documentation().

    Validates: R91.4 — scaling strategy documented per component.
    """

    def test_passes_when_doc_exists_with_all_sections(self, tmp_path: Path) -> None:
        """SCALING_STRATEGY.md with all required sections → pass."""
        docs_dir = tmp_path / "docs" / "architecture"
        docs_dir.mkdir(parents=True)
        (docs_dir / "SCALING_STRATEGY.md").write_text(
            "# Scaling Strategy\n\n"
            "## Backend\n"
            "Stateless FastAPI.\n\n"
            "## Database\n"
            "Supabase PostgreSQL.\n\n"
            "## Storage\n"
            "Backblaze B2.\n\n"
            "## GPU\n"
            "Provider-abstracted.\n\n"
            "## Realtime\n"
            "Supabase Realtime.\n"
        )

        service = ScalabilityVerificationService(project_root=tmp_path)
        result = service.verify_scaling_documentation()

        assert result.verified is True
        assert result.verdict == ScalabilityVerdict.PASS
        assert "R91.4" in result.requirement_ids

    def test_fails_when_doc_missing(self, tmp_path: Path) -> None:
        """No SCALING_STRATEGY.md → fail."""
        service = ScalabilityVerificationService(project_root=tmp_path)
        result = service.verify_scaling_documentation()

        assert result.verified is False
        assert result.verdict == ScalabilityVerdict.FAIL
        assert any("not found" in e for e in result.evidence)


@pytest.mark.unit
class TestGetComponentScalingInfo:
    """Tests for get_component_scaling_info().

    Validates: R91.4 — documents horizontal vs vertical per component.
    """

    def test_returns_all_components(self, tmp_path: Path) -> None:
        """Returns scaling info for all major components."""
        service = ScalabilityVerificationService(project_root=tmp_path)
        components = service.get_component_scaling_info()

        assert len(components) >= 6
        component_names = [c.component for c in components]
        assert "FastAPI Backend" in component_names
        assert "Supabase PostgreSQL" in component_names
        assert "Backblaze B2 Storage" in component_names
        assert "GPU Compute (Provider-Abstracted)" in component_names
        assert "Supabase Realtime" in component_names
        assert "Brain/LLM Providers" in component_names

    def test_backend_is_horizontal(self, tmp_path: Path) -> None:
        """Backend should be classified as horizontal scaling."""
        service = ScalabilityVerificationService(project_root=tmp_path)
        components = service.get_component_scaling_info()

        backend = next(c for c in components if "Backend" in c.component)
        assert backend.scaling_direction == ScalingDirection.HORIZONTAL

    def test_database_is_vertical(self, tmp_path: Path) -> None:
        """Database should be classified as vertical scaling."""
        service = ScalabilityVerificationService(project_root=tmp_path)
        components = service.get_component_scaling_info()

        db = next(c for c in components if "PostgreSQL" in c.component)
        assert db.scaling_direction == ScalingDirection.VERTICAL

    def test_storage_is_managed(self, tmp_path: Path) -> None:
        """Storage should be classified as managed (auto-scales)."""
        service = ScalabilityVerificationService(project_root=tmp_path)
        components = service.get_component_scaling_info()

        storage = next(c for c in components if "B2" in c.component)
        assert storage.scaling_direction == ScalingDirection.MANAGED

    def test_gpu_is_horizontal(self, tmp_path: Path) -> None:
        """GPU compute should be classified as horizontal scaling."""
        service = ScalabilityVerificationService(project_root=tmp_path)
        components = service.get_component_scaling_info()

        gpu = next(c for c in components if "GPU" in c.component)
        assert gpu.scaling_direction == ScalingDirection.HORIZONTAL


@pytest.mark.unit
class TestGetScalabilityStatus:
    """Tests for get_scalability_status() — the main entry point.

    Validates: R91.1, R91.3, R91.4, R76.8, R76.10
    """

    def test_returns_complete_status_response(self, tmp_path: Path) -> None:
        """Returns a valid ScalabilityStatusResponse with all fields."""
        # Create minimal project structure for all checks to work
        backend_dir = tmp_path / "backend"
        app_dir = backend_dir / "app"

        (app_dir / "providers").mkdir(parents=True)
        (app_dir / "providers" / "compute.py").write_text(
            "from typing import Protocol\n\nclass ComputeProvider(Protocol):\n    pass\n"
        )
        (app_dir / "services").mkdir(parents=True)
        (app_dir / "services" / "job_service.py").write_text("class JobService:\n    pass\n")
        (app_dir / "core").mkdir(parents=True)
        (app_dir / "core" / "security.py").write_text("import jwt\n")
        (app_dir / "api" / "v1" / "endpoints").mkdir(parents=True)
        (app_dir / "api" / "v1" / "endpoints" / "jobs.py").write_text("pass\n")

        docs_dir = tmp_path / "docs" / "architecture"
        docs_dir.mkdir(parents=True)
        (docs_dir / "SCALING_STRATEGY.md").write_text(
            "# Backend\n## Database\n## Storage\n## GPU\n## Realtime\n"
        )

        service = ScalabilityVerificationService(project_root=tmp_path)
        response = service.get_scalability_status()

        assert response.properties is not None
        assert len(response.properties) == 4
        assert response.component_scaling is not None
        assert len(response.component_scaling) >= 6
        assert response.documentation_exists is True
        assert response.verified_at is not None

    def test_overall_pass_when_no_failures(self, tmp_path: Path) -> None:
        """overall_pass is True when no properties have FAIL verdict."""
        backend_dir = tmp_path / "backend"
        app_dir = backend_dir / "app"

        (app_dir / "providers").mkdir(parents=True)
        (app_dir / "providers" / "compute.py").write_text(
            "from typing import Protocol\n\nclass ComputeProvider(Protocol):\n    pass\n"
        )
        (app_dir / "services").mkdir(parents=True)
        (app_dir / "services" / "job_service.py").write_text("class JobService:\n    pass\n")
        (app_dir / "core").mkdir(parents=True)
        (app_dir / "core" / "security.py").write_text("import jwt\n")
        (app_dir / "api" / "v1" / "endpoints").mkdir(parents=True)
        (app_dir / "api" / "v1" / "endpoints" / "jobs.py").write_text("pass\n")

        docs_dir = tmp_path / "docs" / "architecture"
        docs_dir.mkdir(parents=True)
        (docs_dir / "SCALING_STRATEGY.md").write_text(
            "# Backend\n## Database\n## Storage\n## GPU\n## Realtime\n"
        )

        service = ScalabilityVerificationService(project_root=tmp_path)
        response = service.get_scalability_status()

        assert response.overall_pass is True

    def test_overall_fail_when_any_property_fails(self, tmp_path: Path) -> None:
        """overall_pass is False when any property has FAIL verdict."""
        # No docs → scaling_documentation will fail
        backend_dir = tmp_path / "backend"
        app_dir = backend_dir / "app"
        (app_dir / "providers").mkdir(parents=True)
        (app_dir / "providers" / "compute.py").write_text(
            "from typing import Protocol\n\nclass ComputeProvider(Protocol):\n    pass\n"
        )
        (app_dir / "services").mkdir(parents=True)
        (app_dir / "services" / "job_service.py").write_text("class JobService:\n    pass\n")
        (app_dir / "core").mkdir(parents=True)
        (app_dir / "api" / "v1" / "endpoints").mkdir(parents=True)

        service = ScalabilityVerificationService(project_root=tmp_path)
        response = service.get_scalability_status()

        assert response.overall_pass is False
        assert response.documentation_exists is False
