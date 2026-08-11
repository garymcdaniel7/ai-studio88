"""Video Pipeline API Router — Hardened (Story 017).

All video operations require authenticated workspace context.
Parent-project ownership is validated for all child resources.
Destructive and paid actions produce audit entries.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import AuthUser, require_auth
from backend.data_access import AuthorizationError
from backend.data_access_helpers import get_authorized_client, get_authorized_client_strict
from backend.video.provider import (
    VIDEO_PROVIDERS,
    VideoRequest,
    get_video_provider,
)

router = APIRouter(prefix="/api/v1", tags=["video"])


# =============================================================================
# Audit helpers (destructive/paid video actions)
# =============================================================================

_video_audit: list[dict] = []
_MAX_AUDIT = 500


def _audit(action: str, resource_type: str, resource_id: str, user: AuthUser, details: str = ""):
    from datetime import UTC, datetime

    _video_audit.append({
        "timestamp": datetime.now(UTC).isoformat(),
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "actor_user_id": user.user_id,
        "org_id": user.org_id,
        "details": details,
    })
    if len(_video_audit) > _MAX_AUDIT:
        _video_audit.pop(0)


# =============================================================================
# Video Providers (informational — no auth required)
# =============================================================================


@router.get("/video/providers")
def list_video_providers():
    """List available video generation providers and their health/capabilities.

    Uses the canonical provider registry (Story 143). No provider-specific
    branching — all providers advertise typed capabilities.
    """
    from backend.video.registry import get_video_provider_registry

    registry = get_video_provider_registry()
    providers = registry.list_providers()

    results = []
    for name in providers:
        provider = registry.get_provider(name)
        if provider:
            caps = provider.capabilities()
            health = provider.health()
            results.append({
                "name": provider.name,
                "display_name": provider.display_name,
                "health": {
                    "status": health.status.value,
                    "message": health.message,
                    "gpu_name": health.gpu_name,
                    "vram_total_gb": health.vram_total_gb,
                    "vram_free_gb": health.vram_free_gb,
                    "queue_size": health.queue_size,
                    "estimated_wait_seconds": health.estimated_wait_seconds,
                },
                "capabilities": {
                    "modes": [m.value for m in caps.modes],
                    "models": [
                        {
                            "id": model.id,
                            "name": model.name,
                            "modes": [m.value for m in model.modes],
                            "max_duration_seconds": model.max_duration_seconds,
                            "max_resolution": model.max_resolution,
                            "default_resolution": model.default_resolution,
                            "vram_required_gb": model.vram_required_gb,
                        }
                        for model in caps.models
                    ],
                    "max_concurrent_jobs": caps.max_concurrent_jobs,
                    "supports_cancellation": caps.supports_cancellation,
                    "supports_progress": caps.supports_progress,
                    "supports_cost_estimate": caps.supports_cost_estimate,
                    "deployment_mode": caps.deployment_mode,
                    "notes": caps.notes,
                },
            })

    # Fallback: if registry is empty, use legacy providers
    if not results:
        for name, cls in VIDEO_PROVIDERS.items():
            provider = cls()
            results.append({
                "name": name,
                "display_name": name.title(),
                "health": provider.health(),
                "capabilities": provider.capabilities(),
            })

    return {"providers": results}


@router.get("/video/providers/{provider_name}")
def get_provider_detail(provider_name: str):
    """Get detailed info for a specific video provider."""
    from backend.video.registry import get_video_provider_registry

    registry = get_video_provider_registry()
    provider = registry.get_provider(provider_name)

    if not provider:
        # Fallback to legacy registry
        cls = VIDEO_PROVIDERS.get(provider_name)
        if not cls:
            raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_name}")
        legacy = cls()
        return {
            "name": provider_name,
            "display_name": provider_name.title(),
            "health": legacy.health(),
            "capabilities": legacy.capabilities(),
        }

    caps = provider.capabilities()
    health = provider.health()
    return {
        "name": provider.name,
        "display_name": provider.display_name,
        "health": {
            "status": health.status.value,
            "message": health.message,
            "gpu_name": health.gpu_name,
            "vram_total_gb": health.vram_total_gb,
            "vram_free_gb": health.vram_free_gb,
            "queue_size": health.queue_size,
        },
        "capabilities": {
            "modes": [m.value for m in caps.modes],
            "models": [
                {"id": m.id, "name": m.name, "modes": [mode.value for mode in m.modes]}
                for m in caps.models
            ],
            "max_concurrent_jobs": caps.max_concurrent_jobs,
            "supports_cancellation": caps.supports_cancellation,
            "supports_cost_estimate": caps.supports_cost_estimate,
            "deployment_mode": caps.deployment_mode,
        },
    }


@router.post("/video/providers/{provider_name}/validate")
def validate_video_request(provider_name: str, data: dict, user: AuthUser = Depends(require_auth)):
    """Pre-validate a video generation request against a provider's capabilities.

    Returns validation result without executing. Fails fast before cost/execution.
    """
    from backend.video.contract import VideoGenerationRequest, VideoMode
    from backend.video.registry import get_video_provider_registry

    registry = get_video_provider_registry()
    provider = registry.get_provider(provider_name)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_name}")

    try:
        mode = VideoMode(data.get("mode", "text_to_video"))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid mode: {data.get('mode')}")

    request = VideoGenerationRequest(
        mode=mode,
        prompt=data.get("prompt", ""),
        model=data.get("model", "wan-2.1"),
        duration_seconds=float(data.get("duration_seconds", 2.0)),
        width=int(data.get("width", 832)),
        height=int(data.get("height", 480)),
    )

    error = provider.validate_request(request)
    if error:
        return {"valid": False, "error": {"code": error.code.value, "message": error.message}}
    return {"valid": True}


@router.post("/video/providers/{provider_name}/estimate")
def estimate_video_cost(provider_name: str, data: dict, user: AuthUser = Depends(require_auth)):
    """Get a cost estimate for a video generation request.

    Returns estimated cost without executing.
    """
    from backend.video.contract import VideoGenerationRequest, VideoMode
    from backend.video.registry import get_video_provider_registry

    registry = get_video_provider_registry()
    provider = registry.get_provider(provider_name)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_name}")

    try:
        mode = VideoMode(data.get("mode", "text_to_video"))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid mode: {data.get('mode')}")

    request = VideoGenerationRequest(
        mode=mode,
        prompt=data.get("prompt", ""),
        model=data.get("model", "wan-2.1"),
        duration_seconds=float(data.get("duration_seconds", 2.0)),
        fps=int(data.get("fps", 24)),
        width=int(data.get("width", 832)),
        height=int(data.get("height", 480)),
    )

    estimate = provider.estimate_cost(request)
    return {
        "estimated_cost_usd": estimate.estimated_cost_usd,
        "confidence": estimate.confidence,
        "breakdown": estimate.breakdown,
        "message": estimate.message,
    }


# =============================================================================
# Capability-Driven Provider Selection (Story 145)
# =============================================================================


@router.post("/video/select-providers")
def select_video_providers(data: dict, user: AuthUser = Depends(require_auth)):
    """Query compatible providers for a generation requirement.

    Returns all providers/models classified as compatible, degraded,
    incompatible, unavailable, or unknown — with explainable reasons.

    Includes a deterministic recommendation (versioned ranking rules).

    Body (GenerationRequirement fields):
        mode: str — "text_to_video" | "image_to_video" | "video_to_video"
        duration_seconds: float | null
        width: int | null
        height: int | null
        needs_camera_motion: bool
        needs_negative_prompt: bool
        needs_seed_control: bool
        needs_audio: bool
        needs_high_fps: bool
        deployment_preference: str — "any" | "cloud" | "local" | "self_hosted"
        privacy_level: str — "standard" | "sensitive" | "restricted"
        max_cost_usd: float | null
    """
    from backend.video.capability_selector import (
        DeploymentPreference,
        GenerationRequirement,
        PrivacyLevel,
        select_providers,
        serialize_selection_result,
    )
    from backend.video.contract import VideoMode

    try:
        mode = VideoMode(data.get("mode", "text_to_video"))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid mode: {data.get('mode')}")

    try:
        deployment = DeploymentPreference(data.get("deployment_preference", "any"))
    except ValueError:
        deployment = DeploymentPreference.ANY

    try:
        privacy = PrivacyLevel(data.get("privacy_level", "standard"))
    except ValueError:
        privacy = PrivacyLevel.STANDARD

    requirement = GenerationRequirement(
        mode=mode,
        has_input_image=bool(data.get("has_input_image")),
        has_input_video=bool(data.get("has_input_video")),
        duration_seconds=data.get("duration_seconds"),
        width=data.get("width"),
        height=data.get("height"),
        aspect_ratio=data.get("aspect_ratio"),
        needs_audio=bool(data.get("needs_audio")),
        needs_camera_motion=bool(data.get("needs_camera_motion")),
        needs_negative_prompt=bool(data.get("needs_negative_prompt")),
        needs_seed_control=bool(data.get("needs_seed_control")),
        needs_high_fps=bool(data.get("needs_high_fps")),
        deployment_preference=deployment,
        privacy_level=privacy,
        max_cost_usd=data.get("max_cost_usd"),
        max_wait_seconds=data.get("max_wait_seconds"),
        project_id=data.get("project_id"),
        talent_id=data.get("talent_id"),
    )

    result = select_providers(requirement)
    return serialize_selection_result(result)


@router.post("/video/enforce-compatibility")
def enforce_video_compatibility(data: dict, user: AuthUser = Depends(require_auth)):
    """Server-side enforcement: validates a manual provider/model selection.

    Called before dispatch to ensure the chosen provider can fulfill the
    requirement. Returns compatibility result or 422 if incompatible.

    Body:
        provider_name: str — selected provider
        model_id: str — selected model
        requirement: dict — GenerationRequirement fields (same as select-providers)
    """
    from backend.video.capability_selector import (
        DeploymentPreference,
        GenerationRequirement,
        IncompatibleProviderError,
        PrivacyLevel,
        enforce_compatibility,
        serialize_selection_result,
        SelectionResult,
    )
    from backend.video.contract import VideoMode

    provider_name = data.get("provider_name", "")
    model_id = data.get("model_id", "")
    req_data = data.get("requirement", {})

    if not provider_name or not model_id:
        raise HTTPException(status_code=422, detail="provider_name and model_id required")

    try:
        mode = VideoMode(req_data.get("mode", "text_to_video"))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid mode: {req_data.get('mode')}")

    try:
        deployment = DeploymentPreference(req_data.get("deployment_preference", "any"))
    except ValueError:
        deployment = DeploymentPreference.ANY

    try:
        privacy = PrivacyLevel(req_data.get("privacy_level", "standard"))
    except ValueError:
        privacy = PrivacyLevel.STANDARD

    requirement = GenerationRequirement(
        mode=mode,
        has_input_image=bool(req_data.get("has_input_image")),
        has_input_video=bool(req_data.get("has_input_video")),
        duration_seconds=req_data.get("duration_seconds"),
        width=req_data.get("width"),
        height=req_data.get("height"),
        needs_camera_motion=bool(req_data.get("needs_camera_motion")),
        needs_negative_prompt=bool(req_data.get("needs_negative_prompt")),
        needs_seed_control=bool(req_data.get("needs_seed_control")),
        needs_audio=bool(req_data.get("needs_audio")),
        needs_high_fps=bool(req_data.get("needs_high_fps")),
        deployment_preference=deployment,
        privacy_level=privacy,
        max_cost_usd=req_data.get("max_cost_usd"),
    )

    try:
        compat = enforce_compatibility(requirement, provider_name, model_id)
        return {
            "allowed": True,
            "compatibility": compat.compatibility.value,
            "reasons": [
                {"field": r.field, "verdict": r.verdict.value, "message": r.message}
                for r in compat.reasons
            ],
        }
    except IncompatibleProviderError as e:
        raise HTTPException(status_code=422, detail={
            "allowed": False,
            "provider_name": e.provider_name,
            "model_id": e.model_id,
            "reasons": [
                {"field": r.field, "verdict": r.verdict.value, "message": r.message}
                for r in e.reasons if r.verdict.value in ("incompatible", "unavailable")
            ],
            "message": str(e),
        })
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# Video Projects (all require auth + org scoping)
# =============================================================================


@router.get("/videos")
def list_videos(
    talent_id: str | None = None,
    status: str | None = None,
    user: AuthUser = Depends(require_auth),
):
    """List video projects scoped to the user's workspace."""
    client = get_authorized_client(user)
    if client:
        filters = {}
        if talent_id:
            filters["talent_id"] = talent_id
        if status:
            filters["status"] = status
        result = client.select("video_projects", filters=filters, order_by="created_at", desc=True)
        return result.data or []
    else:
        # Dev mode fallback
        from backend.database import supabase
        query = supabase.table("video_projects").select("*").order("created_at", desc=True)
        if talent_id:
            query = query.eq("talent_id", talent_id)
        if status:
            query = query.eq("status", status)
        try:
            return query.execute().data or []
        except Exception:
            return []


@router.post("/videos", status_code=201)
def create_video(data: dict, user: AuthUser = Depends(require_auth)):
    """Create a video project in the user's workspace."""
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")

    client = get_authorized_client_strict(user)
    record = {
        "name": data["name"],
        "description": data.get("description", ""),
        "video_type": data.get("video_type", "reel"),
        "platform": data.get("platform", "instagram"),
        "aspect_ratio": data.get("aspect_ratio", "9:16"),
        "duration_seconds": float(data.get("duration_seconds", 5.0)),
        "talent_id": data.get("talent_id"),
        "project_id": data.get("project_id"),
        "campaign_id": data.get("campaign_id"),
        "status": "draft",
    }
    result = client.insert("video_projects", record)
    return result.data[0] if result.data else record


@router.get("/videos/{video_id}")
def get_video(video_id: str, user: AuthUser = Depends(require_auth)):
    """Get a video project by ID (org-scoped)."""
    client = get_authorized_client(user)
    if client:
        try:
            result = client.select_by_id("video_projects", video_id)
            return result.data
        except AuthorizationError:
            raise HTTPException(status_code=404, detail="Video project not found")
    else:
        from backend.database import supabase
        try:
            return supabase.table("video_projects").select("*").eq("id", video_id).single().execute().data
        except Exception:
            raise HTTPException(status_code=404, detail="Video project not found")


@router.put("/videos/{video_id}")
def update_video(video_id: str, data: dict, user: AuthUser = Depends(require_auth)):
    """Update a video project (org-scoped)."""
    client = get_authorized_client_strict(user)
    data["updated_at"] = "now()"
    result = client.update("video_projects", data, record_id=video_id)
    if not result.data:
        raise HTTPException(status_code=404, detail="Video project not found")
    return result.data[0]


@router.delete("/videos/{video_id}")
def delete_video(video_id: str, user: AuthUser = Depends(require_auth)):
    """Delete a video project (org-scoped, audited)."""
    client = get_authorized_client_strict(user)
    try:
        client.delete("video_projects", video_id)
    except AuthorizationError:
        raise HTTPException(status_code=404, detail="Video project not found")

    _audit("delete_video_project", "video_project", video_id, user)
    return {"deleted": True}


# =============================================================================
# Video Shots (child of video project — validates parent ownership)
# =============================================================================


def _verify_project_ownership(video_id: str, user: AuthUser):
    """Verify the user's org owns the parent video project.

    Returns the AuthorizedClient if ownership confirmed.
    Raises 404 if project not found in user's org.
    """
    client = get_authorized_client(user)
    if client:
        try:
            client.select_by_id("video_projects", video_id)
            return client
        except AuthorizationError:
            raise HTTPException(status_code=404, detail="Video project not found")
    return None


@router.get("/videos/{video_id}/shots")
def list_shots(video_id: str, user: AuthUser = Depends(require_auth)):
    """List shots for a video project (validates project ownership)."""
    client = _verify_project_ownership(video_id, user)
    if client:
        result = client.select(
            "video_shots",
            filters={"video_project_id": video_id},
            order_by="shot_number",
            desc=False,
        )
        return result.data or []
    else:
        from backend.database import supabase
        try:
            return supabase.table("video_shots").select("*").eq("video_project_id", video_id).order("shot_number").execute().data or []
        except Exception:
            return []


@router.post("/videos/{video_id}/shots", status_code=201)
def create_shot(video_id: str, data: dict, user: AuthUser = Depends(require_auth)):
    """Create a shot in a video project (validates project ownership)."""
    client = _verify_project_ownership(video_id, user)
    if not client:
        client = get_authorized_client_strict(user)

    record = {
        "video_project_id": video_id,
        "shot_number": int(data.get("shot_number", 1)),
        "prompt": data.get("prompt", ""),
        "negative_prompt": data.get("negative_prompt", ""),
        "motion_prompt": data.get("motion_prompt", ""),
        "model": data.get("model", "wan-2.1"),
        "duration_seconds": float(data.get("duration_seconds", 3.0)),
        "fps": int(data.get("fps", 24)),
        "resolution": data.get("resolution", "1080x1920"),
        "camera_motion": data.get("camera_motion", "static"),
        "status": "planned",
    }
    result = client.insert("video_shots", record)
    return result.data[0] if result.data else record


# =============================================================================
# Generate Video Shot (paid action — auth + audit)
# =============================================================================


@router.post("/videos/{video_id}/generate")
def generate_video(video_id: str, data: dict = None, user: AuthUser = Depends(require_auth)):
    """Generate video for all planned shots (requires auth, audited as paid action)."""
    if data is None:
        data = {}

    client = _verify_project_ownership(video_id, user)
    if not client:
        client = get_authorized_client_strict(user)

    # Get planned shots for this project
    shots_result = client.select(
        "video_shots",
        filters={"video_project_id": video_id, "status": "planned"},
        order_by="shot_number",
        desc=False,
    )
    shots = shots_result.data or []

    if not shots:
        raise HTTPException(status_code=400, detail="No planned shots to generate")

    _audit("generate_video", "video_project", video_id, user, f"shots={len(shots)}")

    provider = get_video_provider(data.get("provider", "simulation"))
    results = []

    for shot in shots:
        request = VideoRequest(
            prompt=shot.get("prompt", ""),
            negative_prompt=shot.get("negative_prompt", ""),
            motion_prompt=shot.get("motion_prompt", ""),
            duration_seconds=shot.get("duration_seconds", 3.0),
            fps=shot.get("fps", 24),
            resolution=shot.get("resolution", "1080x1920"),
            model=shot.get("model", "wan-2.1"),
            camera_motion=shot.get("camera_motion", "static"),
        )

        # Mark generating
        client.update("video_shots", {"status": "generating", "updated_at": "now()"}, record_id=shot["id"])

        try:
            result = provider.submit(request)

            if result.success and result.output_bytes:
                from backend.storage import compute_checksum, generate_storage_key, upload_file

                storage_key = generate_storage_key(result.filename, "video")
                checksum = compute_checksum(result.output_bytes)
                public_url = upload_file(result.output_bytes, storage_key, result.mime_type)

                asset_data = {
                    "talent_id": None,
                    "type": "video",
                    "filename": result.filename,
                    "original_filename": result.filename,
                    "mime_type": result.mime_type,
                    "size_bytes": len(result.output_bytes),
                    "storage_provider": "backblaze_b2",
                    "storage_key": storage_key,
                    "public_url": public_url,
                    "checksum": checksum,
                    "metadata": {
                        **result.metadata,
                        "video_project_id": video_id,
                        "shot_id": shot["id"],
                    },
                    "tags": ["video", result.metadata.get("model", ""), provider.name],
                }
                asset_result = client.insert("assets", asset_data)
                asset = asset_result.data[0] if asset_result.data else {}

                client.update("video_shots", {
                    "status": "completed",
                    "output_asset_id": asset.get("id"),
                    "updated_at": "now()",
                }, record_id=shot["id"])

                results.append({"shot_id": shot["id"], "status": "completed", "asset_id": asset.get("id")})
            else:
                client.update("video_shots", {"status": "failed", "updated_at": "now()"}, record_id=shot["id"])
                results.append({"shot_id": shot["id"], "status": "failed", "error": result.error})

        except Exception as e:
            client.update("video_shots", {"status": "failed", "updated_at": "now()"}, record_id=shot["id"])
            results.append({"shot_id": shot["id"], "status": "failed", "error": str(e)})

    return {"video_project_id": video_id, "shots_processed": len(results), "results": results}


# =============================================================================
# Image-to-Video (paid action — auth + audit)
# =============================================================================


@router.post("/video/image-to-video", status_code=201)
def image_to_video(data: dict, user: AuthUser = Depends(require_auth)):
    """Generate video from a source image (requires auth, audited)."""
    if not data.get("prompt"):
        raise HTTPException(status_code=400, detail="'prompt' required")
    if not data.get("source_image"):
        raise HTTPException(status_code=400, detail="'source_image' required (filename or URL)")

    _audit("image_to_video", "generation", "i2v", user, f"model={data.get('model', 'wan-2.1')}")

    provider = get_video_provider(data.get("provider", "comfyui"))

    request = VideoRequest(
        prompt=data["prompt"],
        negative_prompt=data.get("negative_prompt", ""),
        duration_seconds=float(data.get("duration_seconds", 2.0)),
        fps=int(data.get("fps", 24)),
        resolution=data.get("resolution", "832x480"),
        model=data.get("model", "wan-2.1"),
        extra={
            "mode": "image_to_video",
            "source_image": data["source_image"],
            "denoise": float(data.get("denoise", 0.75)),
            "workflow_template": data.get("workflow_template", "wan21_i2v_simple"),
        },
    )

    result = provider.submit(request)

    if result.success:
        return {
            "status": "completed",
            "filename": result.filename,
            "mime_type": result.mime_type,
            "duration_seconds": result.duration_seconds,
            "generation_time_seconds": result.generation_time_seconds,
            "metadata": result.metadata,
        }
    else:
        raise HTTPException(status_code=500, detail=result.error or "Generation failed")


# =============================================================================
# Timeline (child of video project — validates parent ownership)
# =============================================================================


@router.get("/videos/{video_id}/timeline")
def get_timeline(video_id: str, user: AuthUser = Depends(require_auth)):
    """Get the full timeline for a video project (validates ownership)."""
    client = _verify_project_ownership(video_id, user)
    if client:
        tracks_result = client.select(
            "timeline_tracks",
            filters={"video_project_id": video_id},
            order_by="order_index",
            desc=False,
        )
        tracks = tracks_result.data or []
        # Note: timeline_clips don't have org_id — accessed via track parent
        # For full isolation, we'd need to join. For now, we validate project ownership.
        from backend.database import supabase
        for track in tracks:
            try:
                clips = supabase.table("timeline_clips").select("*").eq("track_id", track["id"]).order("start_time").execute().data or []
                track["clips"] = clips
            except Exception:
                track["clips"] = []
        return {"video_project_id": video_id, "tracks": tracks}
    else:
        from backend.database import supabase
        try:
            tracks = supabase.table("timeline_tracks").select("*").eq("video_project_id", video_id).order("order_index").execute().data or []
            for track in tracks:
                clips = supabase.table("timeline_clips").select("*").eq("track_id", track["id"]).order("start_time").execute().data or []
                track["clips"] = clips
            return {"video_project_id": video_id, "tracks": tracks}
        except Exception:
            return {"video_project_id": video_id, "tracks": []}


@router.post("/videos/{video_id}/timeline/tracks", status_code=201)
def create_track(video_id: str, data: dict, user: AuthUser = Depends(require_auth)):
    """Create a timeline track (validates project ownership)."""
    client = _verify_project_ownership(video_id, user)
    if not client:
        client = get_authorized_client_strict(user)

    record = {
        "video_project_id": video_id,
        "name": data.get("name", "Video"),
        "track_type": data.get("track_type", "video"),
        "order_index": int(data.get("order_index", 0)),
    }
    result = client.insert("timeline_tracks", record)
    return result.data[0] if result.data else record


@router.post("/videos/{video_id}/timeline/clips", status_code=201)
def create_clip(video_id: str, data: dict, user: AuthUser = Depends(require_auth)):
    """Create a timeline clip (validates project ownership)."""
    _verify_project_ownership(video_id, user)

    if not data.get("track_id"):
        raise HTTPException(status_code=400, detail="'track_id' required")

    # For clips, we insert via raw DB since timeline_clips may not be in TENANT_TABLES
    from backend.database import supabase
    record = {
        "track_id": data["track_id"],
        "asset_id": data.get("asset_id"),
        "start_time": float(data.get("start_time", 0.0)),
        "end_time": float(data.get("end_time", 3.0)),
        "duration_seconds": float(data.get("duration_seconds", 3.0)),
        "clip_type": data.get("clip_type", "video"),
        "effects": data.get("effects", []),
    }
    try:
        result = supabase.table("timeline_clips").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Render + Export (paid actions — auth + audit)
# =============================================================================


@router.post("/videos/{video_id}/render")
def render_video(video_id: str, data: dict = None, user: AuthUser = Depends(require_auth)):
    """Create a render job (requires auth, validates ownership, audited)."""
    if data is None:
        data = {}

    client = _verify_project_ownership(video_id, user)
    if not client:
        client = get_authorized_client_strict(user)

    record = {
        "video_project_id": video_id,
        "provider": data.get("provider", "simulation"),
        "status": "completed",
        "runtime_seconds": 2.5,
        "metadata": {"rendered_by": "simulation"},
    }
    result = client.insert("video_renders", record)
    _audit("render_video", "video_render", video_id, user, f"provider={data.get('provider', 'simulation')}")
    return result.data[0] if result.data else record


@router.post("/videos/{video_id}/export")
def export_video(video_id: str, data: dict = None, user: AuthUser = Depends(require_auth)):
    """Create a timeline export (requires auth, validates ownership, audited)."""
    if data is None:
        data = {}

    _verify_project_ownership(video_id, user)

    from backend.database import supabase
    record = {
        "video_project_id": video_id,
        "export_format": data.get("format", "mp4"),
        "resolution": data.get("resolution", "1080x1920"),
        "fps": int(data.get("fps", 24)),
        "status": "completed",
    }
    try:
        result = supabase.table("timeline_exports").insert(record).execute()
        _audit("export_video", "video_export", video_id, user, f"format={data.get('format', 'mp4')}")
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/video-renders")
def list_renders(video_project_id: str | None = None, user: AuthUser = Depends(require_auth)):
    """List renders scoped to user's workspace."""
    client = get_authorized_client(user)
    if client:
        filters = {}
        if video_project_id:
            filters["video_project_id"] = video_project_id
        result = client.select("video_renders", filters=filters, order_by="created_at", desc=True)
        return result.data or []
    else:
        from backend.database import supabase
        query = supabase.table("video_renders").select("*").order("created_at", desc=True)
        if video_project_id:
            query = query.eq("video_project_id", video_project_id)
        try:
            return query.execute().data or []
        except Exception:
            return []


@router.get("/video-renders/{render_id}")
def get_render(render_id: str, user: AuthUser = Depends(require_auth)):
    """Get a render by ID (org-scoped)."""
    client = get_authorized_client(user)
    if client:
        try:
            result = client.select_by_id("video_renders", render_id)
            return result.data
        except AuthorizationError:
            raise HTTPException(status_code=404, detail="Render not found")
    else:
        from backend.database import supabase
        try:
            return supabase.table("video_renders").select("*").eq("id", render_id).single().execute().data
        except Exception:
            raise HTTPException(status_code=404, detail="Render not found")
