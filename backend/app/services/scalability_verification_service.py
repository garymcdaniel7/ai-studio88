"""Scalability Architecture Verification Service.

Verifies that the AI Studio architecture satisfies scalability requirements:
- User growth does NOT require proportional GPU scaling (R91.1, R76.8)
- Job transport is replaceable without API contract change (R91.3, R76.10)
- Backend is stateless behind a load balancer (R7.5)
- Horizontal vs vertical scaling is documented per component (R91.4)

This service performs static analysis of the codebase architecture to verify
these properties hold. It checks:
1. No coupling between user auth/CRUD paths and GPU provider code
2. ComputeProvider interface is used (not direct provider calls)
3. No in-process mutable state used in request handling
4. Scaling documentation exists

Validates: Requirements R91.1, R91.3, R91.4, R76.8, R76.10
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.core.logging import get_logger
from app.schemas.scalability import (
    ComponentScalingInfo,
    ScalabilityProperty,
    ScalabilityStatusResponse,
    ScalabilityVerdict,
    ScalingDirection,
)

logger = get_logger(__name__)

# Modules in the user auth/CRUD path that should NOT import GPU providers
USER_PATH_MODULES = [
    "app.core.security",
    "app.core.dependencies",
    "app.services.provisioning_service",
    "app.services.talent_service",
    "app.services.asset_service",
    "app.services.brain_memory_service",
    "app.services.brain_conversation_service",
]

# GPU/compute provider modules that user auth paths should not depend on
GPU_PROVIDER_MODULES = [
    "app.providers.compute",
    "app.services.workload_scheduler",
    "backend.infrastructure",
    "backend.gpu",
    "backend.worker",
]

# Known patterns indicating mutable module-level state in request handling
MUTABLE_STATE_PATTERNS = [
    "global ",
    "= {}  # module-level mutable",
    "= []  # module-level mutable",
    "_cache = {}",
    "_state = {}",
    "_instances = {}",
]

# Files to check for statelessness (request-handling paths)
STATELESSNESS_CHECK_PATHS = [
    "app/api/v1/endpoints",
    "app/services",
    "app/core",
]

# Provider interface marker — we look for Protocol usage
COMPUTE_PROVIDER_INTERFACE_MARKER = "ComputeProvider"


class ScalabilityVerificationService:
    """Service for verifying scalability architecture properties.

    Performs static analysis of the codebase to verify that architectural
    properties for scalability hold without running the full system.

    Validates: Requirements R91.1, R91.3, R91.4, R76.8, R76.10
    """

    def __init__(self, project_root: str | Path | None = None) -> None:
        """Initialize the service.

        Args:
            project_root: Root of the project. Defaults to auto-detected.
        """
        if project_root is None:
            # Auto-detect: 4 levels up from this file (app/services/ -> backend/ -> project root)
            self._project_root = Path(__file__).resolve().parent.parent.parent.parent
        else:
            self._project_root = Path(project_root)

        self._backend_root = self._project_root / "backend"

    def verify_user_gpu_independence(self) -> ScalabilityProperty:
        """Verify that user growth does not require GPU scaling.

        Checks that user auth/CRUD code paths have no direct imports of
        GPU provider modules. User registration, login, talent CRUD, memory,
        and conversation services should work entirely without GPU infrastructure.

        Validates: R91.1, R76.8
        """
        violations: list[str] = []
        evidence: list[str] = []

        for module_path in USER_PATH_MODULES:
            # Convert module path to file path
            file_path = self._module_to_filepath(module_path)
            if not file_path.exists():
                evidence.append(f"Module {module_path} not found (skipped)")
                continue

            content = file_path.read_text(errors="ignore")

            # Check for GPU provider imports
            for gpu_module in GPU_PROVIDER_MODULES:
                # Check various import patterns
                import_patterns = [
                    f"from {gpu_module}",
                    f"import {gpu_module}",
                ]
                for pattern in import_patterns:
                    if pattern in content:
                        violations.append(
                            f"{module_path} imports {gpu_module}"
                        )

        if not violations:
            evidence.append(
                "User auth/CRUD modules have no direct GPU provider dependencies"
            )
            evidence.append(
                f"Checked {len(USER_PATH_MODULES)} user-path modules against "
                f"{len(GPU_PROVIDER_MODULES)} GPU provider modules"
            )
            return ScalabilityProperty(
                property_name="user_gpu_independence",
                description=(
                    "User growth (registration, auth, CRUD) does not require "
                    "proportional GPU scaling. User-facing code paths have no "
                    "coupling to GPU provider infrastructure."
                ),
                verified=True,
                verdict=ScalabilityVerdict.PASS,
                evidence=evidence,
                requirement_ids=["R91.1", "R76.8"],
            )

        evidence.extend(violations)
        return ScalabilityProperty(
            property_name="user_gpu_independence",
            description=(
                "User growth (registration, auth, CRUD) does not require "
                "proportional GPU scaling. User-facing code paths have no "
                "coupling to GPU provider infrastructure."
            ),
            verified=False,
            verdict=ScalabilityVerdict.FAIL,
            evidence=evidence,
            requirement_ids=["R91.1", "R76.8"],
        )

    def verify_job_transport_replaceability(self) -> ScalabilityProperty:
        """Verify that job transport is replaceable without API contract change.

        Checks that:
        1. A ComputeProvider interface (Protocol) exists
        2. Job submission endpoints use the service layer (not direct provider calls)
        3. The job table schema defines the public contract (not a queue-specific schema)

        Validates: R91.3, R76.10
        """
        evidence: list[str] = []

        # Check 1: ComputeProvider interface exists
        compute_provider_path = self._backend_root / "app" / "providers" / "compute.py"
        interface_found = False
        if compute_provider_path.exists():
            content = compute_provider_path.read_text(errors="ignore")
            if "Protocol" in content and COMPUTE_PROVIDER_INTERFACE_MARKER in content:
                interface_found = True
                evidence.append(
                    "ComputeProvider Protocol interface found in app/providers/compute.py"
                )
        else:
            evidence.append("app/providers/compute.py not found")

        # Check 2: Job endpoints use service layer, not direct provider calls
        endpoints_dir = self._backend_root / "app" / "api" / "v1" / "endpoints"
        direct_provider_calls: list[str] = []
        if endpoints_dir.exists():
            for endpoint_file in endpoints_dir.glob("*.py"):
                content = endpoint_file.read_text(errors="ignore")
                # Check for direct imports of specific providers (not the interface)
                specific_providers = [
                    "from backend.providers.vast",
                    "import runpod",
                    "import vastai",
                    "from runpod",
                    "from vastai",
                ]
                for provider_import in specific_providers:
                    if provider_import in content:
                        direct_provider_calls.append(
                            f"{endpoint_file.name} imports specific provider: {provider_import}"
                        )

        if not direct_provider_calls:
            evidence.append(
                "No endpoint files import specific compute providers directly"
            )

        # Check 3: Job service exists as the abstraction layer
        job_service_path = self._backend_root / "app" / "services" / "job_service.py"
        job_service_exists = job_service_path.exists()
        if job_service_exists:
            evidence.append("JobService exists as the abstraction layer for job dispatch")

        verified = interface_found and not direct_provider_calls and job_service_exists

        return ScalabilityProperty(
            property_name="job_transport_replaceability",
            description=(
                "Job transport technology (queue implementation) can be replaced "
                "without changing the public API contract. Jobs are submitted via "
                "a service abstraction, not direct provider calls."
            ),
            verified=verified,
            verdict=ScalabilityVerdict.PASS if verified else ScalabilityVerdict.FAIL,
            evidence=evidence + direct_provider_calls,
            requirement_ids=["R91.3", "R76.10"],
        )

    def verify_backend_statelessness(self) -> ScalabilityProperty:
        """Verify that the backend is stateless behind a load balancer.

        Checks for module-level mutable state in request-handling code paths
        that would prevent horizontal scaling. The backend should store all
        persistent state in Supabase, storage providers, or Redis.

        Validates: R91.4 (implicit), R7.5
        """
        evidence: list[str] = []
        stateful_findings: list[str] = []

        for relative_path in STATELESSNESS_CHECK_PATHS:
            check_dir = self._backend_root / relative_path
            if not check_dir.exists():
                evidence.append(f"Directory {relative_path} not found (skipped)")
                continue

            for py_file in check_dir.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue
                try:
                    content = py_file.read_text(errors="ignore")
                    rel_name = str(py_file.relative_to(self._backend_root))

                    # Check for dangerous module-level mutable state patterns
                    # We specifically look for dicts/lists at module level that
                    # are written to during request handling
                    lines = content.split("\n")
                    for i, line in enumerate(lines, 1):
                        stripped = line.strip()
                        # Skip comments and docstrings
                        if stripped.startswith("#") or stripped.startswith('"""'):
                            continue
                        # Look for module-level mutable dict/list assignments
                        # that aren't type annotations, constants, or configs
                        if self._is_dangerous_mutable_state(line, lines, i):
                            stateful_findings.append(
                                f"{rel_name}:{i}: {stripped[:80]}"
                            )
                except (OSError, PermissionError):
                    continue

        if not stateful_findings:
            evidence.append(
                "No dangerous module-level mutable state detected in request-handling paths"
            )
            evidence.append(
                f"Scanned {len(STATELESSNESS_CHECK_PATHS)} directory trees"
            )
            return ScalabilityProperty(
                property_name="backend_statelessness",
                description=(
                    "Backend is stateless — no in-process mutable state that prevents "
                    "horizontal scaling. All persistent state is stored externally "
                    "(Supabase, B2, Redis)."
                ),
                verified=True,
                verdict=ScalabilityVerdict.PASS,
                evidence=evidence,
                requirement_ids=["R91.4", "R7.5"],
            )

        # Found potential issues — report as warning (not all mutable state is
        # necessarily problematic; some may be caches with proper invalidation)
        evidence.append(
            f"Found {len(stateful_findings)} potential mutable state location(s)"
        )
        evidence.extend(stateful_findings[:10])  # Cap at 10 for readability

        return ScalabilityProperty(
            property_name="backend_statelessness",
            description=(
                "Backend is stateless — no in-process mutable state that prevents "
                "horizontal scaling. All persistent state is stored externally "
                "(Supabase, B2, Redis)."
            ),
            verified=len(stateful_findings) == 0,
            verdict=(
                ScalabilityVerdict.WARN
                if len(stateful_findings) <= 5
                else ScalabilityVerdict.FAIL
            ),
            evidence=evidence,
            requirement_ids=["R91.4", "R7.5"],
        )

    def verify_scaling_documentation(self) -> ScalabilityProperty:
        """Verify that scaling documentation exists.

        Checks for the SCALING_STRATEGY.md document that documents
        horizontal vs vertical scaling per component.

        Validates: R91.4
        """
        evidence: list[str] = []

        docs_path = self._project_root / "docs" / "architecture" / "SCALING_STRATEGY.md"
        doc_exists = docs_path.exists()

        if doc_exists:
            content = docs_path.read_text(errors="ignore")
            # Check for key sections
            required_sections = [
                "Backend",
                "Database",
                "Storage",
                "GPU",
                "Realtime",
            ]
            found_sections = [s for s in required_sections if s.lower() in content.lower()]
            evidence.append(
                f"SCALING_STRATEGY.md exists with {len(found_sections)}/{len(required_sections)} "
                f"required sections"
            )
            if len(found_sections) == len(required_sections):
                evidence.append("All required scaling sections documented")
            else:
                missing = set(required_sections) - set(found_sections)
                evidence.append(f"Missing sections: {', '.join(missing)}")
        else:
            evidence.append("docs/architecture/SCALING_STRATEGY.md not found")

        return ScalabilityProperty(
            property_name="scaling_documentation",
            description=(
                "Horizontal vs vertical scaling strategy is documented per "
                "system component in SCALING_STRATEGY.md."
            ),
            verified=doc_exists,
            verdict=ScalabilityVerdict.PASS if doc_exists else ScalabilityVerdict.FAIL,
            evidence=evidence,
            requirement_ids=["R91.4"],
        )

    def get_component_scaling_info(self) -> list[ComponentScalingInfo]:
        """Get the scaling strategy classification for each system component.

        Documents which components scale horizontally, vertically, or are
        managed services that auto-scale.

        Validates: R91.4
        """
        return [
            ComponentScalingInfo(
                component="FastAPI Backend",
                scaling_direction=ScalingDirection.HORIZONTAL,
                description=(
                    "Stateless FastAPI application behind a load balancer. "
                    "Multiple instances serve requests independently with no "
                    "shared in-process state."
                ),
                current_constraint="Single instance in development; "
                "Railway/Render supports multi-instance",
            ),
            ComponentScalingInfo(
                component="Supabase PostgreSQL",
                scaling_direction=ScalingDirection.VERTICAL,
                description=(
                    "Primary database with connection pooling (PgBouncer). "
                    "Scales vertically via Supabase plan upgrades. "
                    "Read replicas available for read-heavy workloads."
                ),
                current_constraint="Supabase Pro plan connection limits; "
                "read replicas for horizontal read scaling",
            ),
            ComponentScalingInfo(
                component="Backblaze B2 Storage",
                scaling_direction=ScalingDirection.MANAGED,
                description=(
                    "Object storage auto-scales with no action needed. "
                    "No capacity planning required. Pay-per-use model."
                ),
                current_constraint=None,
            ),
            ComponentScalingInfo(
                component="GPU Compute (Provider-Abstracted)",
                scaling_direction=ScalingDirection.HORIZONTAL,
                description=(
                    "GPU workers scale independently of user base via "
                    "ComputeProvider abstraction. Adding providers or workers "
                    "does not require user-facing changes."
                ),
                current_constraint="Provider availability and cost budget limits",
            ),
            ComponentScalingInfo(
                component="Supabase Realtime",
                scaling_direction=ScalingDirection.MANAGED,
                description=(
                    "Managed WebSocket service that scales with connections. "
                    "No infrastructure management required."
                ),
                current_constraint="Supabase plan connection limits",
            ),
            ComponentScalingInfo(
                component="Brain/LLM Providers",
                scaling_direction=ScalingDirection.HORIZONTAL,
                description=(
                    "Provider routing allows adding LLM capacity without code "
                    "changes. Multiple providers can serve requests concurrently. "
                    "Local Ollama + cloud providers scale independently."
                ),
                current_constraint="Provider API rate limits and cost",
            ),
        ]

    def get_scalability_status(self) -> ScalabilityStatusResponse:
        """Run all scalability verification checks and return full status.

        This is the main entry point called by the API endpoint.

        Returns:
            ScalabilityStatusResponse with all properties, component scaling info,
            and overall pass/fail status.
        """
        properties = [
            self.verify_user_gpu_independence(),
            self.verify_job_transport_replaceability(),
            self.verify_backend_statelessness(),
            self.verify_scaling_documentation(),
        ]

        # Overall pass requires all critical properties to pass
        # (warn is acceptable for statelessness since some caches are fine)
        overall_pass = all(
            p.verdict != ScalabilityVerdict.FAIL for p in properties
        )

        component_scaling = self.get_component_scaling_info()

        docs_path = self._project_root / "docs" / "architecture" / "SCALING_STRATEGY.md"

        logger.info(
            "scalability_verification_completed",
            overall_pass=overall_pass,
            properties_count=len(properties),
            passed_count=sum(1 for p in properties if p.verified),
        )

        return ScalabilityStatusResponse(
            overall_pass=overall_pass,
            properties=properties,
            component_scaling=component_scaling,
            documentation_exists=docs_path.exists(),
            verified_at=datetime.now(UTC),
        )

    def _module_to_filepath(self, module_path: str) -> Path:
        """Convert a dotted module path to a filesystem path.

        Example: 'app.core.security' -> backend/app/core/security.py
        """
        parts = module_path.split(".")
        relative = Path(*parts)
        return self._backend_root / relative.with_suffix(".py")

    @staticmethod
    def _is_dangerous_mutable_state(line: str, all_lines: list[str], line_num: int) -> bool:
        """Determine if a line represents dangerous module-level mutable state.

        Heuristic: A module-level dict/list assignment that is NOT:
        - A type annotation
        - A constant (UPPER_CASE name)
        - Inside a function/class (indented)
        - A Pydantic/dataclass field
        - A __all__ or similar dunder
        """
        # Must be at module level (no indentation)
        if line != line.lstrip():
            return False

        stripped = line.strip()

        # Skip empty lines, comments, decorators
        if not stripped or stripped.startswith("#") or stripped.startswith("@"):
            return False

        # Skip class/function definitions
        if stripped.startswith("class ") or stripped.startswith("def ") or stripped.startswith("async def"):
            return False

        # Skip imports
        if stripped.startswith("import ") or stripped.startswith("from "):
            return False

        # Skip type annotations
        if ": " in stripped and "=" not in stripped:
            return False

        # Check for mutable dict/list assignment
        if "=" in stripped:
            var_name = stripped.split("=")[0].strip()

            # Skip constants (UPPER_CASE)
            if var_name.isupper() or (var_name.startswith("_") and var_name[1:].isupper()):
                return False

            # Skip dunders
            if var_name.startswith("__") and var_name.endswith("__"):
                return False

            # Skip type aliases and known safe patterns
            safe_patterns = [
                "logger",
                "router",
                "settings",
                "Dep",
                "Type",
                "Annotated",
                "Field",
                "Depends",
            ]
            if any(p in var_name or p in stripped for p in safe_patterns):
                return False

            # Check if the value is a mutable container being assigned
            value_part = stripped.split("=", 1)[1].strip()
            if value_part in ("{}", "[]", "dict()", "list()", "set()"):
                return True

        return False
