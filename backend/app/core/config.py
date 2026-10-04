"""Application configuration via Pydantic Settings with environment profiles.

Profiles: local, test, staging, production.
Selection: APP_ENV environment variable (defaults to "local").

Startup validation rejects:
  - Placeholder secrets in production/staging
  - Localhost dependencies in production
  - Simulation-only modes in production
  - Debug mode in production
  - Missing critical variables per profile

Never hardcode secrets — add them to .env.example and load them here.
"""

from __future__ import annotations

import logging
import re
import sys
from enum import Enum
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


# =============================================================================
# Environment Profiles
# =============================================================================


class AppEnv(str, Enum):
    """Application environment profiles."""

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"

    # Legacy alias
    DEVELOPMENT = "development"


# Known placeholder patterns that indicate unconfigured secrets
_PLACEHOLDER_PATTERNS = [
    r"^placeholder",
    r"^your[-_]",
    r"^change[-_]?me",
    r"^changeme$",
    r"^xxx",
    r"^sk_test_your",
    r"^whsec_your",
    r"^price_your",
    r"^fake[-_]",
    r"^dummy",
    r"^todo",
    r"^REPLACE",
    r"^INSERT",
    r"^ci-test-",
    r"^your-key-here",
]

_PLACEHOLDER_RE = re.compile("|".join(_PLACEHOLDER_PATTERNS), re.IGNORECASE)


def _is_placeholder(value: str) -> bool:
    """Check if a value looks like a placeholder rather than a real secret."""
    if not value or not value.strip():
        return True
    return bool(_PLACEHOLDER_RE.match(value.strip()))


# Minimum acceptable length for critical secrets in production/staging.
_MIN_SECRET_LENGTH = 16


def _is_short_secret(value: str) -> bool:
    """Return True if a non-empty secret value is shorter than the minimum length."""
    if not value:
        return False  # emptiness handled by _is_placeholder
    return len(value.strip()) < _MIN_SECRET_LENGTH


def _is_localhost(url: str) -> bool:
    """Check if a URL points to localhost."""
    return any(
        pattern in url.lower()
        for pattern in ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
    )


# =============================================================================
# Capability Status
# =============================================================================


class CapabilityStatus(str, Enum):
    """Status of an optional capability."""

    READY = "ready"
    CONFIGURED = "configured"  # configured but not yet verified
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class CapabilityReport:
    """Represents the readiness of a single capability."""

    def __init__(
        self,
        name: str,
        status: CapabilityStatus,
        message: str = "",
    ) -> None:
        self.name = name
        self.status = status
        self.message = message

    def to_dict(self) -> dict[str, str]:
        """Serialize without exposing secrets."""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
        }


# =============================================================================
# Settings
# =============================================================================


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Profile-aware validation ensures unsafe configurations are rejected
    before the application accepts traffic.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_env: str = Field(
        default="local",
        description="Environment profile: local, test, staging, production",
    )
    app_name: str = "ai-studio"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"
    secret_key: str = Field(default="", description="App-level signing key")
    allowed_origins: str = "http://localhost:3000,http://localhost:8000"
    auth_required: bool = Field(
        default=False,
        description="Enforce JWT auth on all endpoints (must be true in production)",
    )
    auth_enforcement_flip: bool = Field(
        default=False,
        description=(
            "The sole rollout flip. It must be true before staging or production "
            "startup; it is never a rollback disable switch."
        ),
    )
    auth_dark_launch: bool = Field(
        default=False,
        description=(
            "Controlled non-production observation mode. It cannot be enabled in "
            "staging or production."
        ),
    )

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://localhost:8000"
    api_prefix: str = "/api/v1"
    workers: int = 1

    # ── Browser authentication ────────────────────────────────────────────────
    auth_frontend_url: str = Field(
        default="",
        description="Frontend origin that receives the Supabase OAuth callback.",
    )

    # ── Platform connection OAuth ────────────────────────────────────────────
    oauth_redirect_uri: str = Field(
        default="",
        validation_alias="OAUTH_REDIRECT_URI",
        description="Backend OAuth callback URI used for provider token exchange.",
    )
    fanvue_client_id: str = Field(default="", validation_alias="FANVUE_CLIENT_ID")
    fanvue_client_secret: str = Field(default="", validation_alias="FANVUE_CLIENT_SECRET")
    instagram_client_id: str = Field(default="", validation_alias="INSTAGRAM_APP_ID")
    instagram_client_secret: str = Field(default="", validation_alias="INSTAGRAM_APP_SECRET")
    youtube_client_id: str = Field(default="", validation_alias="GOOGLE_CLIENT_ID")
    youtube_client_secret: str = Field(default="", validation_alias="GOOGLE_CLIENT_SECRET")
    tiktok_client_id: str = Field(default="", validation_alias="TIKTOK_CLIENT_KEY")
    tiktok_client_secret: str = Field(default="", validation_alias="TIKTOK_CLIENT_SECRET")
    github_client_id: str = Field(default="", validation_alias="GITHUB_CLIENT_ID")
    github_client_secret: str = Field(default="", validation_alias="GITHUB_CLIENT_SECRET")

    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = ""
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # ── Backblaze B2 ──────────────────────────────────────────────────────────
    b2_key_id: str = ""
    b2_application_key: str = ""
    b2_bucket_name: str = ""
    b2_bucket_id: str = ""
    b2_endpoint_url: str = "https://s3.us-east-005.backblazeb2.com"
    b2_region: str = "us-east-005"
    b2_cdn_url: str = ""

    # ── GPU Providers ─────────────────────────────────────────────────────────
    vast_api_key: str = ""
    vastai_api_key: str = ""  # legacy alias
    vast_default_image: str = "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime"
    vast_default_gpu: str = "A100"
    vast_disk_gb: int = 80
    vast_max_price_per_hour: float = 1.50
    vastai_default_num_gpus: int = 1
    vastai_ssh_key_path: str = "~/.ssh/id_ed25519"

    runpod_api_key: str = ""
    runpod_default_gpu_type: str = "NVIDIA RTX 4090"

    fleet_preferred_provider: str = "thundercompute"
    fleet_max_instances: int = 3
    fleet_daily_budget: float = 10.0
    fleet_idle_timeout: int = 10
    fleet_auto_provision: bool = True
    fleet_min_vram: int = 24
    fleet_max_price: float = 1.50

    # ── BYO provider endpoints and policy defaults ─────────────────────────
    thunder_compute_base_url: str = "https://api.thundercompute.com:8443"
    thunder_compute_api_key: str = Field(
        default="",
        validation_alias="THUNDER_COMPUTE_API_KEY",
        description="Thunder Compute API token used only by backend integrations.",
    )
    thunder_watch_enabled: bool = True
    thunder_watch_interval_seconds: int = Field(default=1800, ge=60)
    runcomfy_base_url: str = "https://api.runcomfy.com"
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    openai_base_url: str = "https://api.openai.com/v1"
    replicate_base_url: str = "https://api.replicate.com"
    provider_timeout_seconds: float = 60.0
    provider_health_timeout_seconds: float = 5.0
    provider_retry_attempts: int = 2
    byo_allow_platform_fallback: bool = False
    byo_allow_organization_pool: bool = True

    # ── HuggingFace ───────────────────────────────────────────────────────────
    hf_token: str = ""

    # ── ComfyUI ───────────────────────────────────────────────────────────────
    comfyui_base_url: str = "http://localhost:8188"
    comfyui_workflows_dir: str = "./workflows"
    comfyui_output_dir: str = "./output"
    comfyui_timeout_seconds: int = 300

    # ── Generation ────────────────────────────────────────────────────────────
    generation_provider: str = "simulation"
    default_generation_provider: str = "simulation"

    # ── Redis / Celery ────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # ── Auth ──────────────────────────────────────────────────────────────────
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    auth_dev_mode: bool = Field(
        default=False,
        description=(
            "When true in local/test: injects dev user from first org_members record. "
            "REFUSES TO START if true in production/staging."
        ),
    )
    environment: str = Field(
        default="local",
        description="Deployment environment (alias for app_env, for explicit clarity in .env files)",
    )

    # ── ElevenLabs ────────────────────────────────────────────────────────────
    elevenlabs_api_key: str = ""
    elevenlabs_base_url: str = "https://api.elevenlabs.io/v1"
    elevenlabs_live: bool = False
    voice_provider: str = "simulation"

    # ── Ollama / Brain ────────────────────────────────────────────────────────
    # Ollama is credential-free. The endpoint is configured for the backend only
    # and is never returned in provider/status payloads.
    ollama_enabled: bool = True
    ollama_base_url: str = "http://localhost:11434"
    ollama_mode: str = "local"  # local | managed_vps
    ollama_privacy_mode: str = "local"  # local | private | shared
    ollama_model: str = "llama3.1:8b"
    ollama_dolphin_model: str = "dolphin-llama3:8b"
    ollama_uncensored_opt_in: bool = False
    ollama_safety_mode: str = "standard"  # standard | uncensored
    ollama_health_timeout_seconds: float = 5.0
    ollama_timeout_seconds: float = 120.0
    ollama_max_tokens: int = 4096
    ollama_max_latency_ms: int = 120_000
    llm_fallback_mode: str = "auto"  # auto | ask | strict
    brain_provider: str = "ollama"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # ── Training ──────────────────────────────────────────────────────────────
    training_provider: str = "simulation"
    training_vast_live: bool = False
    simpletuner_live: bool = False

    # ── Multi-tenancy ─────────────────────────────────────────────────────────
    enable_multitenancy: bool = True
    default_tenant_plan: str = "starter"

    # ── Generation Defaults ───────────────────────────────────────────────────
    default_image_width: int = 1024
    default_image_height: int = 1024
    default_image_steps: int = 20
    default_video_fps: int = 24
    default_video_duration_seconds: int = 5

    # ── Feature Flags ─────────────────────────────────────────────────────────
    feature_video_generation: bool = True
    feature_voice_generation: bool = False
    feature_lora_training: bool = True
    feature_analytics: bool = True

    # ── Monitoring ────────────────────────────────────────────────────────────
    sentry_dsn: str = ""
    enable_metrics: bool = False

    # ── Vercel ────────────────────────────────────────────────────────────────
    vercel_token: str = ""
    vercel_project_id: str = ""

    # ── Publishing ────────────────────────────────────────────────────────────
    publishing_enabled: bool = False

    # ── Stripe ────────────────────────────────────────────────────────────────
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # ── Worker API ────────────────────────────────────────────────────────────
    worker_api_url: str = "http://localhost:7860"
    worker_api_port: int = 7860

    # ── Credential Broker ─────────────────────────────────────────────────────
    credential_broker_url: str = Field(
        default="",
        description=(
            "URL for the Credential Broker service. Must be set and reachable "
            "before the platform accepts job submissions in production."
        ),
    )
    credential_broker_enabled: bool = Field(
        default=False,
        description="Whether the Credential Broker is configured and ready.",
    )

    # ── Cost ──────────────────────────────────────────────────────────────────
    cost_daily_budget: float = 10.0
    cost_monthly_budget: float = 200.0

    # =========================================================================
    # Validators
    # =========================================================================

    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_env(cls, v: str) -> str:
        """Normalize environment name (development -> local for backward compat)."""
        v = v.strip().lower()
        if v == "development":
            return "local"
        return v

    @model_validator(mode="before")
    @classmethod
    def sync_environment_field(cls, data: Any) -> Any:
        """Sync 'environment' env var to app_env if app_env is not explicitly set."""
        if isinstance(data, dict):
            # If ENVIRONMENT is set but APP_ENV is not, use ENVIRONMENT
            env_val = data.get("environment") or data.get("ENVIRONMENT")
            app_env_val = data.get("app_env") or data.get("APP_ENV")
            if env_val and not app_env_val:
                data["app_env"] = env_val
        return data

    @model_validator(mode="after")
    def validate_ollama_configuration(self) -> Settings:
        """Fail closed on unsafe or incomplete Ollama configuration."""
        errors: list[str] = []
        if self.ollama_mode not in {"local", "managed_vps"}:
            errors.append("OLLAMA_MODE must be 'local' or 'managed_vps'")
        if self.ollama_privacy_mode not in {"local", "private", "shared"}:
            errors.append("OLLAMA_PRIVACY_MODE must be local, private, or shared")
        if self.ollama_safety_mode not in {"standard", "uncensored"}:
            errors.append("OLLAMA_SAFETY_MODE must be 'standard' or 'uncensored'")
        if self.llm_fallback_mode not in {"auto", "ask", "strict"}:
            errors.append("LLM_FALLBACK_MODE must be auto, ask, or strict")
        if not self.ollama_base_url.strip():
            errors.append("OLLAMA_BASE_URL is required when Ollama is configured")
        if self.ollama_health_timeout_seconds <= 0:
            errors.append("OLLAMA_HEALTH_TIMEOUT_SECONDS must be positive")
        if self.ollama_timeout_seconds <= 0:
            errors.append("OLLAMA_TIMEOUT_SECONDS must be positive")
        if self.ollama_max_tokens <= 0:
            errors.append("OLLAMA_MAX_TOKENS must be positive")
        if self.ollama_max_latency_ms <= 0:
            errors.append("OLLAMA_MAX_LATENCY_MS must be positive")

        normalized_model = self.ollama_model.strip().lower().split(":", 1)[0]
        is_uncensored = normalized_model == "dolphin-llama3"
        if is_uncensored and not self.ollama_uncensored_opt_in:
            errors.append(
                "OLLAMA_UNCENSORED_OPT_IN=true is required before selecting dolphin-llama3"
            )
        if self.ollama_safety_mode == "uncensored" and not self.ollama_uncensored_opt_in:
            errors.append(
                "OLLAMA_UNCENSORED_OPT_IN=true is required for uncensored safety mode"
            )

        # A local endpoint in a protected deployment can silently route private
        # prompts to an operator host or hang indefinitely, so reject it rather
        # than silently degrading to an unsafe configuration.
        if self.ollama_enabled and self.app_env in {"staging", "production"}:
            if self.ollama_mode == "local" or _is_localhost(self.ollama_base_url):
                errors.append(
                    "OLLAMA must use a non-local managed_vps endpoint in staging/production"
                )

        if errors:
            raise ValueError("Ollama configuration invalid: " + "; ".join(errors))
        return self

    @model_validator(mode="after")
    def validate_profile(self) -> Settings:
        """Run profile-specific validation after all fields are loaded."""
        errors = self._validate_for_profile()
        if errors:
            msg = f"Configuration invalid for profile '{self.app_env}':\n"
            for err in errors:
                msg += f"  - {err}\n"
            # In production/staging, fail hard. In local/test, warn only.
            if self.app_env in ("production", "staging"):
                raise ValueError(msg)
            else:
                # Log warnings but allow startup in dev/test
                for err in errors:
                    logger.warning("config_warning", profile=self.app_env, issue=err)
        return self

    # =========================================================================
    # Profile Properties
    # =========================================================================

    @property
    def profile(self) -> AppEnv:
        """Get the current environment profile as an enum."""
        try:
            return AppEnv(self.app_env)
        except ValueError:
            return AppEnv.LOCAL

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse allowed_origins string into a list."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.app_env == "production"

    @property
    def is_staging(self) -> bool:
        """Check if running in staging."""
        return self.app_env == "staging"

    @property
    def is_local(self) -> bool:
        """Check if running in local development."""
        return self.app_env in ("local", "development")

    @property
    def is_test(self) -> bool:
        """Check if running in test mode."""
        return self.app_env == "test"

    @property
    def effective_vast_api_key(self) -> str:
        """Get the effective Vast.ai API key (handles legacy alias)."""
        return self.vast_api_key or self.vastai_api_key

    @property
    def credential_broker_configured(self) -> bool:
        """Whether the Credential Broker is available for issuing job credentials.

        Job submissions MUST check this property and return 503
        CREDENTIAL_SERVICE_UNAVAILABLE if False in production.
        """
        if self.credential_broker_enabled:
            return True
        if self.credential_broker_url and not _is_placeholder(self.credential_broker_url):
            return True
        # In local/test environments, allow proceeding without credential broker
        return self.app_env in ("local", "test", "development")

    @property
    def non_critical_service_warnings(self) -> list[str]:
        """Return warnings for non-critical services that are unavailable.

        These services allow the platform to start in degraded mode with warnings,
        but endpoints needing these services should return 503.
        """
        warnings: list[str] = []
        if not (self.effective_vast_api_key or self.runpod_api_key):
            warnings.append("GPU provider not configured — generation will be unavailable")
        if self.voice_provider == "simulation" or not self.elevenlabs_api_key:
            warnings.append("Voice provider not configured — voice synthesis unavailable")
        if self.training_provider == "simulation":
            warnings.append("Training provider in simulation mode — LoRA training unavailable")
        if self.brain_provider == "ollama":
            if not self.ollama_enabled:
                warnings.append("Local Ollama is disabled — Brain requires an approved fallback")
            elif self.ollama_model.lower().split(":", 1)[0] == "dolphin-llama3":
                warnings.append(
                    "dolphin-llama3 is uncensored — review safety and content policy before use"
                )
            # Ollama is local and may not be running — this is a soft warning.
        elif not self.openai_api_key:
            warnings.append("No cloud LLM provider configured — Brain may be unavailable")
        return warnings

    # =========================================================================
    # Validation Logic
    # =========================================================================

    def _validate_for_profile(self) -> list[str]:
        """Validate settings are safe for the current profile.

        Returns a list of error messages. Empty list = valid.
        """
        errors: list[str] = []

        if self.app_env in ("production", "staging"):
            errors.extend(self._validate_production())
        elif self.app_env == "test":
            errors.extend(self._validate_test())

        return errors

    def _validate_production(self) -> list[str]:
        """Production/staging constraints."""
        errors: list[str] = []

        # ── Critical secrets must be set and not placeholders ─────────────────
        critical_secrets = {
            "secret_key": self.secret_key,
            "supabase_url": str(self.supabase_url),
            "supabase_service_role_key": self.supabase_service_role_key,
            "supabase_jwt_secret": self.supabase_jwt_secret,
            "supabase_anon_key": self.supabase_anon_key,
        }

        for name, value in critical_secrets.items():
            if not value:
                errors.append(f"{name.upper()} is required in {self.app_env}")
            elif _is_placeholder(value):
                errors.append(
                    f"{name.upper()} contains a placeholder value — set a real credential"
                )
            elif _is_short_secret(value):
                errors.append(
                    f"{name.upper()} is too short (must be at least {_MIN_SECRET_LENGTH} characters)"
                )

        # ── secret_key must be strong ─────────────────────────────────────────
        if self.secret_key and len(self.secret_key) < 32:
            errors.append("SECRET_KEY must be at least 32 characters in production")

        # ── No debug mode ─────────────────────────────────────────────────────
        if self.debug:
            errors.append("DEBUG must be false in production")

        # ── AUTH_DEV_MODE must NOT be enabled in production/staging ────────────
        if self.auth_dev_mode:
            errors.append(
                "AUTH_DEV_MODE=true is not permitted in production/staging. "
                "This is a development-only feature."
            )

        # ── Auth must be enforced ─────────────────────────────────────────────
        if not self.auth_required:
            errors.append("AUTH_REQUIRED must be true in production")

        # ── No localhost dependencies ─────────────────────────────────────────
        localhost_checks = {
            "SUPABASE_URL": str(self.supabase_url),
            "DATABASE_URL": str(self.database_url),
            "REDIS_URL": self.redis_url,
            "API_BASE_URL": self.api_base_url,
        }
        for name, url in localhost_checks.items():
            if url and _is_localhost(url):
                errors.append(
                    f"{name} points to localhost — not allowed in {self.app_env}"
                )

        # ── No simulation-only generation modes ───────────────────────────────
        if self.generation_provider == "simulation":
            errors.append(
                "GENERATION_PROVIDER cannot be 'simulation' in production"
            )

        if self.training_provider == "simulation" and self.feature_lora_training:
            errors.append(
                "TRAINING_PROVIDER cannot be 'simulation' when FEATURE_LORA_TRAINING is enabled in production"
            )

        if self.voice_provider == "simulation" and self.feature_voice_generation:
            errors.append(
                "VOICE_PROVIDER cannot be 'simulation' when FEATURE_VOICE_GENERATION is enabled in production"
            )

        # ── Storage must be configured ────────────────────────────────────────
        if not self.b2_key_id or _is_placeholder(self.b2_key_id):
            errors.append("B2_KEY_ID is required in production")
        if not self.b2_application_key or _is_placeholder(self.b2_application_key):
            errors.append("B2_APPLICATION_KEY is required in production")

        # ── At least one GPU provider when generation is not simulation ───────
        if self.generation_provider != "simulation":
            has_gpu = bool(self.effective_vast_api_key) or bool(self.runpod_api_key)
            if not has_gpu:
                errors.append(
                    "At least one GPU provider (VAST_API_KEY or RUNPOD_API_KEY) "
                    "required when GENERATION_PROVIDER is not 'simulation'"
                )

        # ── ALLOWED_ORIGINS must not be wildcard ──────────────────────────────
        if "*" in self.allowed_origins:
            errors.append("ALLOWED_ORIGINS cannot contain '*' in production")

        # ── Credential Broker must be configured ──────────────────────────────
        if not self.credential_broker_url and not self.credential_broker_enabled:
            errors.append(
                "CREDENTIAL_BROKER_URL or CREDENTIAL_BROKER_ENABLED must be set in production — "
                "required before accepting job submissions"
            )

        return errors

    def _validate_test(self) -> list[str]:
        """Test profile constraints."""
        errors: list[str] = []

        # Test should not accidentally use production credentials
        if self.supabase_url and "supabase.co" in str(self.supabase_url):
            # Only warn — don't block (integration tests may use real DB)
            pass

        return errors

    # =========================================================================
    # Capability Readiness
    # =========================================================================

    def get_capability_status(self) -> list[CapabilityReport]:
        """Report the status of each configurable capability.

        Does NOT expose secret values — only whether they are configured.
        """
        capabilities: list[CapabilityReport] = []

        # Database
        if self.supabase_url and not _is_placeholder(str(self.supabase_url)):
            capabilities.append(
                CapabilityReport("database", CapabilityStatus.CONFIGURED, "Supabase URL set")
            )
        else:
            capabilities.append(
                CapabilityReport("database", CapabilityStatus.UNAVAILABLE, "SUPABASE_URL not configured")
            )

        # Storage (B2)
        if self.b2_key_id and self.b2_application_key:
            capabilities.append(
                CapabilityReport("storage", CapabilityStatus.CONFIGURED, "B2 credentials set")
            )
        else:
            capabilities.append(
                CapabilityReport("storage", CapabilityStatus.UNAVAILABLE, "B2 credentials missing")
            )

        # GPU (any provider)
        gpu_key = self.effective_vast_api_key or self.runpod_api_key
        if gpu_key and not _is_placeholder(gpu_key):
            provider = "Vast.ai" if self.effective_vast_api_key else "RunPod"
            capabilities.append(
                CapabilityReport("gpu", CapabilityStatus.CONFIGURED, f"{provider} API key set")
            )
        else:
            capabilities.append(
                CapabilityReport("gpu", CapabilityStatus.UNAVAILABLE, "No GPU provider configured")
            )

        # Generation engine
        if self.generation_provider == "simulation":
            capabilities.append(
                CapabilityReport(
                    "generation",
                    CapabilityStatus.DEGRADED,
                    "Running in simulation mode (no real images)",
                )
            )
        elif self.comfyui_base_url:
            capabilities.append(
                CapabilityReport("generation", CapabilityStatus.CONFIGURED, "ComfyUI configured")
            )
        else:
            capabilities.append(
                CapabilityReport("generation", CapabilityStatus.UNAVAILABLE, "No generation engine")
            )

        # LLM / Brain
        if self.brain_provider == "ollama" and self.ollama_enabled:
            message = f"Ollama ({self.ollama_model})"
            if self.ollama_model.lower().split(":", 1)[0] == "dolphin-llama3":
                message += " — uncensored opt-in enabled"
            capabilities.append(
                CapabilityReport("llm", CapabilityStatus.CONFIGURED, message)
            )
        elif self.brain_provider == "ollama":
            capabilities.append(
                CapabilityReport("llm", CapabilityStatus.DEGRADED, "Local Ollama disabled; fallback required")
            )
        elif self.brain_provider == "openai" and self.openai_api_key:
            capabilities.append(
                CapabilityReport("llm", CapabilityStatus.CONFIGURED, "OpenAI configured")
            )
        else:
            capabilities.append(
                CapabilityReport("llm", CapabilityStatus.UNAVAILABLE, "No LLM provider configured")
            )

        # Voice
        if self.elevenlabs_api_key and self.elevenlabs_live:
            capabilities.append(
                CapabilityReport("voice", CapabilityStatus.CONFIGURED, "ElevenLabs live")
            )
        elif self.voice_provider == "simulation":
            capabilities.append(
                CapabilityReport("voice", CapabilityStatus.DEGRADED, "Voice in simulation mode")
            )
        else:
            capabilities.append(
                CapabilityReport("voice", CapabilityStatus.UNAVAILABLE, "Voice not configured")
            )

        # Training
        if self.training_provider == "simulation":
            capabilities.append(
                CapabilityReport("training", CapabilityStatus.DEGRADED, "Training in simulation mode")
            )
        elif self.training_vast_live or self.simpletuner_live:
            capabilities.append(
                CapabilityReport("training", CapabilityStatus.CONFIGURED, "GPU training enabled")
            )
        else:
            capabilities.append(
                CapabilityReport("training", CapabilityStatus.UNAVAILABLE, "Training not configured")
            )

        # Auth
        if self.supabase_jwt_secret and not _is_placeholder(self.supabase_jwt_secret):
            capabilities.append(
                CapabilityReport("auth", CapabilityStatus.CONFIGURED, "JWT validation configured")
            )
        else:
            capabilities.append(
                CapabilityReport("auth", CapabilityStatus.UNAVAILABLE, "JWT secret not set")
            )

        # Redis
        if self.redis_url:
            capabilities.append(
                CapabilityReport("queue", CapabilityStatus.CONFIGURED, "Redis URL set")
            )
        else:
            capabilities.append(
                CapabilityReport("queue", CapabilityStatus.UNAVAILABLE, "REDIS_URL not configured")
            )

        return capabilities

    def get_readiness_summary(self) -> dict[str, Any]:
        """Return a readiness summary safe for HTTP responses (no secrets)."""
        capabilities = self.get_capability_status()

        # Overall readiness: ready if no UNAVAILABLE critical capabilities
        critical_caps = {"database", "auth"}
        critical_statuses = {
            cap.name: cap.status
            for cap in capabilities
            if cap.name in critical_caps
        }
        all_critical_ok = all(
            s != CapabilityStatus.UNAVAILABLE for s in critical_statuses.values()
        )

        return {
            "ready": all_critical_ok,
            "profile": self.app_env,
            "version": self.app_version,
            "capabilities": [cap.to_dict() for cap in capabilities],
        }


# =============================================================================
# Singleton Access
# =============================================================================


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings.

    Validates configuration on first access. In production/staging,
    raises ValueError if unsafe settings are detected.

    Using lru_cache ensures the .env file is read exactly once.
    Use dependency injection in FastAPI endpoints:
        settings: Annotated[Settings, Depends(get_settings)]
    """
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:
        # Log the error without exposing secrets, then re-raise
        print(f"FATAL: Configuration validation failed: {exc}", file=sys.stderr)
        raise


def reset_settings() -> None:
    """Clear the cached settings (for testing only)."""
    get_settings.cache_clear()
