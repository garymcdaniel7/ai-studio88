"""Application configuration via Pydantic Settings.

All values are read from environment variables / .env file.
Never hardcode secrets — add them to .env.example and load them here.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AnyHttpUrl, Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_env: str = Field(default="development", pattern="^(development|staging|production)$")
    app_name: str = "ai-studio"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"
    secret_key: str = Field(min_length=32)
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"
    workers: int = 1

    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url: AnyHttpUrl
    supabase_anon_key: str
    supabase_service_role_key: str
    supabase_jwt_secret: str

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: PostgresDsn
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # ── Backblaze B2 ──────────────────────────────────────────────────────────
    b2_key_id: str
    b2_application_key: str
    b2_bucket_name: str
    b2_bucket_id: str = ""
    b2_endpoint_url: str = "https://s3.us-west-000.backblazeb2.com"
    b2_region: str = "us-west-000"
    b2_cdn_url: str = ""

    # ── Vast.ai ───────────────────────────────────────────────────────────────
    vastai_api_key: str = ""
    vastai_default_disk_gb: int = 50
    vastai_default_gpu_type: str = "RTX_4090"
    vastai_default_num_gpus: int = 1

    # ── RunPod (future) ───────────────────────────────────────────────────────
    runpod_api_key: str = ""

    # ── ComfyUI ───────────────────────────────────────────────────────────────
    comfyui_base_url: AnyHttpUrl = "http://localhost:8188"  # type: ignore[assignment]
    comfyui_workflows_dir: str = "./workflows"
    comfyui_output_dir: str = "./output"
    comfyui_timeout_seconds: int = 300

    # ── Redis / Celery ────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # ── Auth ──────────────────────────────────────────────────────────────────
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ── Generation Defaults ───────────────────────────────────────────────────
    default_image_width: int = 1024
    default_image_height: int = 1024
    default_image_steps: int = 20
    default_video_fps: int = 24
    default_video_duration_seconds: int = 5

    # ── Multi-tenancy ─────────────────────────────────────────────────────────
    enable_multitenancy: bool = True
    default_tenant_plan: str = "starter"

    # ── Feature Flags ─────────────────────────────────────────────────────────
    feature_video_generation: bool = True
    feature_voice_generation: bool = False
    feature_lora_training: bool = True
    feature_analytics: bool = True

    # ── Monitoring ────────────────────────────────────────────────────────────
    sentry_dsn: str = ""
    enable_metrics: bool = False

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings.

    Using lru_cache ensures the .env file is read exactly once.
    Use dependency injection in FastAPI endpoints:
        settings: Annotated[Settings, Depends(get_settings)]
    """
    return Settings()  # type: ignore[call-arg]


# Convenience alias for direct imports where DI is not available
settings = get_settings()
