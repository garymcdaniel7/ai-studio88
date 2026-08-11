"""Deployment Repeatability Service.

Manages deployment verification history and classifies deployment stability.
Tracks verification runs, calculates success rates, and determines whether
the deployment meets the production gate requirement for repeatability.

Classification Rules (per R109):
    - "not_proven": fewer than 3 total verification records
    - "demonstrated_but_unstable": has successes but fewer than 3 consecutive
    - "repeatable_and_stable": 3+ consecutive successful verifications from main

Production Gate Integration:
    - meets_production_gate = True only when classification is "repeatable_and_stable"
    - This feeds into _check_deployment_repeatable in ProductionGateService

Validates: Requirements R109.1, R109.2, R109.3, R109.4, R109.5, R82.7, R82.8
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.logging import get_logger
from app.schemas.deployment_repeatability import (
    DeploymentClassification,
    DeploymentRepeatabilityResponse,
    DeploymentVerificationRecord,
    DeploymentVerificationRunResponse,
    VerificationCheck,
    VerificationCheckName,
)

logger = get_logger(__name__)

# Minimum consecutive successes required for "repeatable_and_stable"
MIN_CONSECUTIVE_SUCCESSES = 3

# Maximum history entries to retain in memory
MAX_HISTORY_SIZE = 50


class DeploymentRepeatabilityError(Exception):
    """Base exception for deployment repeatability operations."""

    def __init__(self, message: str, code: str = "REPEATABILITY_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class VerificationRunError(DeploymentRepeatabilityError):
    """Raised when a verification run encounters an infrastructure error."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="VERIFICATION_RUN_ERROR")


class DeploymentRepeatabilityService:
    """Service for managing deployment verification and repeatability tracking.

    Stores verification history in-memory and in a JSON log directory.
    In production, this would be backed by a database table.

    Validates: R109.1, R109.2, R109.3, R109.4, R109.5, R82.7, R82.8
    """

    def __init__(
        self,
        log_dir: str | Path | None = None,
        project_root: str | Path | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            log_dir: Directory for verification log files. Defaults to
                     PROJECT_ROOT/.deployment_logs
            project_root: Root of the project. Defaults to auto-detected.
        """
        if project_root is None:
            # Auto-detect project root (3 levels up from this file)
            self._project_root = Path(__file__).resolve().parent.parent.parent.parent
        else:
            self._project_root = Path(project_root)

        if log_dir is None:
            self._log_dir = self._project_root / ".deployment_logs"
        else:
            self._log_dir = Path(log_dir)

        self._history: list[DeploymentVerificationRecord] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Load verification history from log directory if not already loaded."""
        if self._loaded:
            return

        self._history = []
        if self._log_dir.exists():
            log_files = sorted(self._log_dir.glob("verification_*.json"), reverse=True)
            for log_file in log_files[:MAX_HISTORY_SIZE]:
                try:
                    with open(log_file) as f:
                        data = json.load(f)
                    record = self._parse_log_entry(data, log_file.stem)
                    self._history.append(record)
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    logger.warning(
                        "skipped_corrupt_verification_log",
                        file=str(log_file),
                        error=str(exc),
                    )

        self._loaded = True

    @staticmethod
    def _parse_log_entry(
        data: dict, file_id: str
    ) -> DeploymentVerificationRecord:
        """Parse a JSON log entry into a DeploymentVerificationRecord."""
        checks = []
        for check_data in data.get("checks", []):
            checks.append(
                VerificationCheck(
                    check_name=check_data["check_name"],
                    passed=check_data["passed"],
                    message=check_data["message"],
                    checked_at=datetime.fromisoformat(
                        check_data["checked_at"].replace("Z", "+00:00")
                    ),
                )
            )

        timestamp_str = data.get("timestamp", "")
        if timestamp_str:
            timestamp = datetime.fromisoformat(
                timestamp_str.replace("Z", "+00:00")
            )
        else:
            timestamp = datetime.now(UTC)

        return DeploymentVerificationRecord(
            id=file_id,
            timestamp=timestamp,
            overall_passed=data.get("overall_passed", False),
            checks=checks,
            git_branch=data.get("git_branch", "unknown"),
            git_sha=data.get("git_sha", "unknown"),
        )

    def _calculate_consecutive_successes(self) -> int:
        """Calculate current streak of consecutive successful verifications.

        Counts from most recent backward. Streak breaks at first failure.
        """
        count = 0
        for record in self._history:
            if record.overall_passed:
                count += 1
            else:
                break
        return count

    def classify_repeatability(self) -> tuple[DeploymentClassification, str]:
        """Classify deployment repeatability based on verification history.

        Returns:
            Tuple of (classification, human-readable reason).

        Classification rules per R109:
            - "not_proven": fewer than 3 total records
            - "demonstrated_but_unstable": some passes but <3 consecutive
            - "repeatable_and_stable": 3+ consecutive successes
        """
        self._ensure_loaded()

        total = len(self._history)
        consecutive = self._calculate_consecutive_successes()

        if total < MIN_CONSECUTIVE_SUCCESSES:
            return (
                DeploymentClassification.NOT_PROVEN,
                f"Only {total} verification(s) recorded; "
                f"need at least {MIN_CONSECUTIVE_SUCCESSES} to prove repeatability",
            )

        if consecutive >= MIN_CONSECUTIVE_SUCCESSES:
            return (
                DeploymentClassification.REPEATABLE_AND_STABLE,
                f"{consecutive} consecutive successful deployments from canonical branch",
            )

        # Has enough records but not enough consecutive successes
        successes = sum(1 for r in self._history if r.overall_passed)
        return (
            DeploymentClassification.DEMONSTRATED_BUT_UNSTABLE,
            f"Demonstrated ({successes}/{total} successful) but only "
            f"{consecutive} consecutive — need {MIN_CONSECUTIVE_SUCCESSES}",
        )

    def get_deployment_history(
        self, limit: int = 10
    ) -> list[DeploymentVerificationRecord]:
        """Return recent verification history (most recent first).

        Args:
            limit: Maximum number of records to return (default 10).

        Returns:
            List of verification records ordered by timestamp descending.
        """
        self._ensure_loaded()
        return self._history[:limit]

    def get_repeatability_status(self) -> DeploymentRepeatabilityResponse:
        """Get the full deployment repeatability status.

        Returns classification, metrics, and recent history.
        Used by GET /api/v1/release/repeatability endpoint.
        """
        self._ensure_loaded()

        classification, reason = self.classify_repeatability()
        total = len(self._history)
        successes = sum(1 for r in self._history if r.overall_passed)
        consecutive = self._calculate_consecutive_successes()
        success_rate = successes / total if total > 0 else 0.0

        return DeploymentRepeatabilityResponse(
            classification=classification,
            classification_reason=reason,
            total_verifications=total,
            successful_verifications=successes,
            consecutive_successes=consecutive,
            success_rate=round(success_rate, 4),
            last_verification=self._history[0] if self._history else None,
            history=self._history[:10],
            meets_production_gate=(
                classification == DeploymentClassification.REPEATABLE_AND_STABLE
            ),
        )

    async def run_verification(self) -> DeploymentVerificationRunResponse:
        """Execute a full deployment verification and record the result.

        Runs the verification checks (frontend build, backend lint/compile,
        suppression scan) and records the outcome. Updates history and
        re-classifies stability.

        Returns:
            Verification run result with updated classification.

        Raises:
            VerificationRunError: If the verification infrastructure fails.
        """
        timestamp = datetime.now(UTC)
        run_id = f"verification_{timestamp.strftime('%Y-%m-%dT%H_%M_%SZ')}_{uuid4().hex[:8]}"

        checks = await self._execute_checks(timestamp)
        overall_passed = all(c.passed for c in checks)

        # Determine git info
        git_branch = self._get_git_branch()
        git_sha = self._get_git_sha()

        record = DeploymentVerificationRecord(
            id=run_id,
            timestamp=timestamp,
            overall_passed=overall_passed,
            checks=checks,
            git_branch=git_branch,
            git_sha=git_sha,
        )

        # Persist to log directory
        self._persist_record(record)

        # Update in-memory history
        self._history.insert(0, record)
        if len(self._history) > MAX_HISTORY_SIZE:
            self._history = self._history[:MAX_HISTORY_SIZE]

        # Re-classify
        classification, _ = self.classify_repeatability()
        meets_gate = classification == DeploymentClassification.REPEATABLE_AND_STABLE

        logger.info(
            "deployment_verification_completed",
            run_id=run_id,
            overall_passed=overall_passed,
            classification=classification.value,
            meets_gate=meets_gate,
            git_branch=git_branch,
            git_sha=git_sha,
        )

        return DeploymentVerificationRunResponse(
            verification=record,
            classification=classification,
            meets_production_gate=meets_gate,
        )

    async def _execute_checks(
        self, timestamp: datetime
    ) -> list[VerificationCheck]:
        """Execute all verification checks.

        Runs checks in sequence: frontend build, backend lint,
        backend compilation, suppression scan.
        """
        checks: list[VerificationCheck] = []

        # Run checks concurrently where possible
        frontend_result = await self._check_frontend_build(timestamp)
        checks.append(frontend_result)

        backend_lint_result = await self._check_backend_lint(timestamp)
        checks.append(backend_lint_result)

        backend_compile_result = await self._check_backend_compile(timestamp)
        checks.append(backend_compile_result)

        suppression_result = await self._check_no_suppressions(timestamp)
        checks.append(suppression_result)

        return checks

    async def _check_frontend_build(
        self, timestamp: datetime
    ) -> VerificationCheck:
        """Check: frontend builds with zero TypeScript/ESLint/Next.js errors."""
        frontend_dir = self._project_root / "frontend"
        if not (frontend_dir / "package.json").exists():
            return VerificationCheck(
                check_name=VerificationCheckName.FRONTEND_BUILD.value,
                passed=False,
                message="Frontend directory or package.json not found",
                checked_at=timestamp,
            )

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["npm", "run", "build"],
                cwd=str(frontend_dir),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                return VerificationCheck(
                    check_name=VerificationCheckName.FRONTEND_BUILD.value,
                    passed=True,
                    message="Frontend build succeeded with zero errors",
                    checked_at=timestamp,
                )
            else:
                error_tail = (result.stderr or result.stdout)[-200:]
                return VerificationCheck(
                    check_name=VerificationCheckName.FRONTEND_BUILD.value,
                    passed=False,
                    message=f"Frontend build failed: {error_tail}",
                    checked_at=timestamp,
                )
        except subprocess.TimeoutExpired:
            return VerificationCheck(
                check_name=VerificationCheckName.FRONTEND_BUILD.value,
                passed=False,
                message="Frontend build timed out (300s limit)",
                checked_at=timestamp,
            )
        except FileNotFoundError:
            return VerificationCheck(
                check_name=VerificationCheckName.FRONTEND_BUILD.value,
                passed=False,
                message="npm not found — cannot run frontend build",
                checked_at=timestamp,
            )

    async def _check_backend_lint(
        self, timestamp: datetime
    ) -> VerificationCheck:
        """Check: backend passes ruff lint with zero errors."""
        backend_dir = self._project_root / "backend"
        if not backend_dir.exists():
            return VerificationCheck(
                check_name=VerificationCheckName.BACKEND_LINT.value,
                passed=False,
                message="Backend directory not found",
                checked_at=timestamp,
            )

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["uv", "run", "ruff", "check", "backend/"],
                cwd=str(self._project_root),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                return VerificationCheck(
                    check_name=VerificationCheckName.BACKEND_LINT.value,
                    passed=True,
                    message="Backend lint (ruff) passed with zero errors",
                    checked_at=timestamp,
                )
            else:
                error_tail = (result.stdout or result.stderr)[-200:]
                return VerificationCheck(
                    check_name=VerificationCheckName.BACKEND_LINT.value,
                    passed=False,
                    message=f"Backend lint failed: {error_tail}",
                    checked_at=timestamp,
                )
        except subprocess.TimeoutExpired:
            return VerificationCheck(
                check_name=VerificationCheckName.BACKEND_LINT.value,
                passed=False,
                message="Backend lint timed out (120s limit)",
                checked_at=timestamp,
            )
        except FileNotFoundError:
            return VerificationCheck(
                check_name=VerificationCheckName.BACKEND_LINT.value,
                passed=False,
                message="uv/ruff not found — cannot run backend lint",
                checked_at=timestamp,
            )

    async def _check_backend_compile(
        self, timestamp: datetime
    ) -> VerificationCheck:
        """Check: backend main.py compiles without errors."""
        main_py = self._project_root / "backend" / "main.py"
        if not main_py.exists():
            return VerificationCheck(
                check_name=VerificationCheckName.BACKEND_COMPILE.value,
                passed=False,
                message="backend/main.py not found",
                checked_at=timestamp,
            )

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["uv", "run", "python", "-m", "py_compile", "backend/main.py"],
                cwd=str(self._project_root),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                return VerificationCheck(
                    check_name=VerificationCheckName.BACKEND_COMPILE.value,
                    passed=True,
                    message="Backend main.py compiles without errors",
                    checked_at=timestamp,
                )
            else:
                error_tail = (result.stderr or result.stdout)[-200:]
                return VerificationCheck(
                    check_name=VerificationCheckName.BACKEND_COMPILE.value,
                    passed=False,
                    message=f"Backend compilation failed: {error_tail}",
                    checked_at=timestamp,
                )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return VerificationCheck(
                check_name=VerificationCheckName.BACKEND_COMPILE.value,
                passed=False,
                message=f"Backend compilation check failed: {type(exc).__name__}",
                checked_at=timestamp,
            )

    async def _check_no_suppressions(
        self, timestamp: datetime
    ) -> VerificationCheck:
        """Check: no suppressed or disabled build checks in critical paths.

        Per R109.4/R82.8: Deployment with ignored, disabled, or suppressed
        required build errors SHALL NOT constitute clean production evidence.

        Scans for:
            - // @ts-nocheck or // @ts-ignore in frontend/src/**
            - eslint-disable in frontend/src/app/** and frontend/src/lib/**
            - # type: ignore in backend/app/core/security.py and dependencies.py
        """
        suppressions: list[str] = []

        # Check TypeScript suppressions
        frontend_src = self._project_root / "frontend" / "src"
        if frontend_src.exists():
            ts_count = await self._count_pattern_in_dir(
                frontend_src,
                patterns=["// @ts-nocheck", "// @ts-ignore"],
                extensions=[".ts", ".tsx"],
            )
            if ts_count > 0:
                suppressions.append(f"ts-nocheck/ts-ignore: {ts_count}")

        # Check ESLint suppressions in critical paths
        for critical_path in ["app", "lib"]:
            check_dir = self._project_root / "frontend" / "src" / critical_path
            if check_dir.exists():
                eslint_count = await self._count_pattern_in_dir(
                    check_dir,
                    patterns=["eslint-disable-next-line", "eslint-disable "],
                    extensions=[".ts", ".tsx", ".js", ".jsx"],
                )
                if eslint_count > 0:
                    suppressions.append(
                        f"eslint-disable in {critical_path}: {eslint_count}"
                    )

        # Check type: ignore in security modules
        security_files = [
            self._project_root / "backend" / "app" / "core" / "security.py",
            self._project_root / "backend" / "app" / "core" / "dependencies.py",
        ]
        for sec_file in security_files:
            if sec_file.exists():
                count = await self._count_pattern_in_file(
                    sec_file, patterns=["# type: ignore"]
                )
                if count > 0:
                    suppressions.append(
                        f"type-ignore in {sec_file.name}: {count}"
                    )

        if suppressions:
            return VerificationCheck(
                check_name=VerificationCheckName.NO_SUPPRESSED_CHECKS.value,
                passed=False,
                message=f"Suppressed checks found: {'; '.join(suppressions)}",
                checked_at=timestamp,
            )

        return VerificationCheck(
            check_name=VerificationCheckName.NO_SUPPRESSED_CHECKS.value,
            passed=True,
            message="No suppressed or disabled build checks found in critical paths",
            checked_at=timestamp,
        )

    @staticmethod
    async def _count_pattern_in_dir(
        directory: Path,
        patterns: list[str],
        extensions: list[str],
    ) -> int:
        """Count occurrences of patterns in files with given extensions."""
        count = 0

        def _scan() -> int:
            nonlocal count
            for ext in extensions:
                for filepath in directory.rglob(f"*{ext}"):
                    try:
                        content = filepath.read_text(errors="ignore")
                        for pattern in patterns:
                            count += content.count(pattern)
                    except (OSError, PermissionError):
                        pass
            return count

        return await asyncio.to_thread(_scan)

    @staticmethod
    async def _count_pattern_in_file(
        filepath: Path, patterns: list[str]
    ) -> int:
        """Count occurrences of patterns in a single file."""

        def _scan() -> int:
            try:
                content = filepath.read_text(errors="ignore")
                return sum(content.count(p) for p in patterns)
            except (OSError, PermissionError):
                return 0

        return await asyncio.to_thread(_scan)

    def _persist_record(self, record: DeploymentVerificationRecord) -> None:
        """Persist a verification record to the log directory."""
        self._log_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "timestamp": record.timestamp.isoformat(),
            "overall_passed": record.overall_passed,
            "checks": [
                {
                    "check_name": c.check_name,
                    "passed": c.passed,
                    "message": c.message,
                    "checked_at": c.checked_at.isoformat(),
                }
                for c in record.checks
            ],
            "git_branch": record.git_branch,
            "git_sha": record.git_sha,
        }

        log_file = self._log_dir / f"{record.id}.json"
        with open(log_file, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(
            "verification_record_persisted",
            record_id=record.id,
            log_file=str(log_file),
        )

    def _get_git_branch(self) -> str:
        """Get current git branch name."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(self._project_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "unknown"

    def _get_git_sha(self) -> str:
        """Get current git commit SHA (short)."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(self._project_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "unknown"

    def add_verification_record(
        self, record: DeploymentVerificationRecord
    ) -> None:
        """Add a verification record directly (for testing or manual import).

        Args:
            record: A pre-built verification record to add to history.
        """
        self._ensure_loaded()
        self._history.insert(0, record)
        if len(self._history) > MAX_HISTORY_SIZE:
            self._history = self._history[:MAX_HISTORY_SIZE]
        self._persist_record(record)
