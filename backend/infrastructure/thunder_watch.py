"""Safe Thunder Compute instance watcher and Railway scheduler.

The watcher is deliberately fail-closed: database uncertainty protects all
instances, and provider failures prevent termination rather than guessing. It
uses the durable ``public.jobs`` table as the application activity source and
never exposes tenant, job, or credential data in its response.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from backend.app.core.config import Settings, get_settings

logger = structlog.get_logger(__name__)

WATCH_INTERVAL_SECONDS = 30 * 60
FORCE_TERMINATE_AFTER = timedelta(hours=8)
WARN_AFTER = timedelta(hours=4)
IDLE_TERMINATE_AFTER = timedelta(hours=1)
ACTIVE_JOB_LOOKBACK = timedelta(hours=1)
ACTIVE_JOB_STATUSES = ("queued", "started", "running", "claimed")
RUNNING_INSTANCE_STATUSES = frozenset({"RUNNING", "STARTED", "ACTIVE"})

JobActivityReader = Callable[[datetime], Awaitable[bool]]
HttpClientFactory = Callable[[], httpx.AsyncClient]
Clock = Callable[[], datetime]


class ThunderWatchError(RuntimeError):
    """Raised when Thunder instance inventory cannot be read safely."""


class ThunderWatcher:
    """Evaluate and safely terminate idle Thunder Compute instances."""

    def __init__(
        self,
        settings: Settings | Any | None = None,
        *,
        job_activity_reader: JobActivityReader | None = None,
        client_factory: HttpClientFactory | None = None,
        clock: Clock | None = None,
    ) -> None:
        """Initialize the watcher with settings and injectable I/O seams."""
        self.settings = settings or get_settings()
        self._job_activity_reader = job_activity_reader or read_recent_job_activity
        self._client_factory = client_factory or self._default_client
        self._clock = clock or (lambda: datetime.now(UTC))

    def _default_client(self) -> httpx.AsyncClient:
        """Create the async Thunder client without exposing its token."""
        token = str(getattr(self.settings, "thunder_compute_api_key", ""))
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        timeout = float(getattr(self.settings, "provider_timeout_seconds", 60.0))
        return httpx.AsyncClient(headers=headers, timeout=timeout)

    @property
    def _base_url(self) -> str:
        """Return the configured Thunder endpoint without a trailing slash."""
        return str(getattr(self.settings, "thunder_compute_base_url", "")).rstrip("/")

    async def run(self) -> dict[str, list[str]]:
        """Run one idempotent watch pass and return only terminated/warned IDs."""
        now = self._clock()
        active_job_exists = await self._job_activity_reader(now)

        async with self._client_factory() as client:
            instances = await self._list_instances(client)
            terminated: list[str] = []
            warned: list[str] = []

            for instance in instances:
                instance_id = _instance_id(instance)
                if not instance_id or not _is_running(instance):
                    continue

                started_at = _parse_timestamp(instance.get("started_at"))
                if started_at is None:
                    # Missing timestamps are unsafe to classify as idle.
                    logger.warning("thunder_watch_missing_started_at")
                    continue

                uptime = max(timedelta(0), now - started_at)
                force_terminate = uptime > FORCE_TERMINATE_AFTER
                over_warn_threshold = uptime > WARN_AFTER
                idle = uptime > IDLE_TERMINATE_AFTER and not active_job_exists

                # The eight-hour ceiling is an explicit force-kill. A recent
                # generation protects ordinary idle cleanup, not a leaked box.
                if force_terminate or idle:
                    await self._terminate(client, instance_id)
                    terminated.append(instance_id)
                elif over_warn_threshold:
                    warned.append(instance_id)

            return {"terminated": terminated, "warned": warned}

    async def _list_instances(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        """Fetch the Thunder inventory, failing closed on malformed responses."""
        try:
            response = await client.get(f"{self._base_url}/v1/instances/list")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("thunder_watch_inventory_failed", error_type=type(exc).__name__)
            raise ThunderWatchError("Thunder inventory unavailable") from exc

        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            logger.warning("thunder_watch_inventory_invalid")
            raise ThunderWatchError("Thunder inventory unavailable")
        return payload

    async def _terminate(self, client: httpx.AsyncClient, instance_id: str) -> None:
        """Delete one instance without logging provider credentials or payloads."""
        try:
            response = await client.delete(f"{self._base_url}/v1/instances/{instance_id}")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "thunder_watch_termination_failed",
                instance_id=instance_id,
                error_type=type(exc).__name__,
            )
            raise ThunderWatchError("Thunder termination unavailable") from exc


def _instance_id(instance: dict[str, Any]) -> str:
    """Extract the provider instance identifier without trusting other fields."""
    value = instance.get("uuid") or instance.get("id")
    return str(value) if value is not None else ""


def _is_running(instance: dict[str, Any]) -> bool:
    """Return whether a provider inventory row represents a running instance."""
    return str(instance.get("status", "")).upper() in RUNNING_INSTANCE_STATUSES


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO timestamp into UTC, returning None for unsafe input."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).astimezone(UTC)


async def read_recent_job_activity(now: datetime) -> bool:
    """Return whether any tenant has recent active generation work.

    Supabase's Python client is synchronous, so the query runs in a worker
    thread to keep the FastAPI event loop responsive. Any database failure
    returns ``True`` (protective hold) rather than authorizing termination.
    """
    try:
        rows = await asyncio.to_thread(_read_active_job_rows)
    except Exception as exc:  # provider/database boundary must fail closed
        logger.warning("thunder_watch_job_activity_failed", error_type=type(exc).__name__)
        return True

    cutoff = now - ACTIVE_JOB_LOOKBACK
    for row in rows:
        if not isinstance(row, dict):
            continue
        if any(
            (timestamp := _parse_timestamp(row.get(field))) is not None and timestamp >= cutoff
            for field in ("started_at", "created_at", "updated_at")
        ):
            return True
    return False


def _read_active_job_rows() -> list[dict[str, Any]]:
    """Read active job metadata through the existing service-role DB client."""
    from backend.database import get_supabase_client

    result = (
        get_supabase_client()
        .table("jobs")
        .select("id,org_id,status,created_at,started_at,updated_at")
        .in_("status", list(ACTIVE_JOB_STATUSES))
        .execute()
    )
    return list(result.data or [])


_scheduler_task: asyncio.Task[None] | None = None
_scheduler_lock = asyncio.Lock()


async def _watch_loop(
    watcher_factory: Callable[[], ThunderWatcher],
    interval_seconds: int,
) -> None:
    """Run the watcher periodically until application shutdown."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await watcher_factory().run()
        except asyncio.CancelledError:
            raise
        except ThunderWatchError:
            # The watcher already emitted a safe, non-secret reason.
            continue
        except Exception as exc:  # keep the Railway process alive
            logger.warning("thunder_watch_scheduler_pass_failed", error_type=type(exc).__name__)


async def start_thunder_watch_scheduler(
    settings: Settings | Any | None = None,
    *,
    watcher_factory: Callable[[], ThunderWatcher] | None = None,
) -> asyncio.Task[None] | None:
    """Start exactly one in-process 30-minute watcher task when configured."""
    global _scheduler_task
    settings = settings or get_settings()
    if not bool(getattr(settings, "thunder_watch_enabled", True)):
        return None
    if not str(getattr(settings, "thunder_compute_api_key", "")):
        logger.info("thunder_watch_scheduler_disabled", reason="provider_not_configured")
        return None

    async with _scheduler_lock:
        if _scheduler_task is not None and not _scheduler_task.done():
            return _scheduler_task
        interval = max(
            60,
            int(getattr(settings, "thunder_watch_interval_seconds", WATCH_INTERVAL_SECONDS)),
        )
        factory = watcher_factory or (lambda: ThunderWatcher(settings))
        _scheduler_task = asyncio.create_task(_watch_loop(factory, interval))
        return _scheduler_task


async def stop_thunder_watch_scheduler() -> None:
    """Cancel and await the watcher task during graceful application shutdown."""
    global _scheduler_task
    async with _scheduler_lock:
        task = _scheduler_task
        _scheduler_task = None
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
