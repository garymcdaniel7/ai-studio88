"""Application service for the typed, tenant-scoped story API."""

from __future__ import annotations

from typing import Any

from backend.generation_jobs import SubmissionError, submit_generation
from backend.story_engine.repository import StoryRepository


class StoryGenerationError(RuntimeError):
    """Raised when a preview cannot be queued safely."""


PREVIEW_ESTIMATED_COST_USD = 0.0


class StoryService:
    """Coordinate story operations while keeping the router free of persistence logic."""

    def __init__(self, repository: StoryRepository) -> None:
        """Initialize the service with a story repository."""
        self.repository = repository

    def list_universes(self, org_id: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """List universes for the authenticated organization."""
        return self.repository.list_universes(org_id, limit, offset)

    def create_universe(self, data: Any, org_id: str) -> dict[str, Any]:
        """Create a universe for the authenticated organization."""
        return self.repository.create_universe(data, org_id)

    def get_universe(self, universe_id: str, org_id: str) -> dict[str, Any]:
        """Get an organization-owned universe."""
        return self.repository.get_universe(universe_id, org_id)

    def update_universe(self, universe_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Update an organization-owned universe."""
        return self.repository.update_universe(universe_id, data, org_id)

    def delete_universe(self, universe_id: str, org_id: str) -> None:
        """Delete an organization-owned universe."""
        self.repository.delete_universe(universe_id, org_id)

    def list_characters(self, universe_id: str, org_id: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """List characters under an owned universe."""
        return self.repository.list_characters(universe_id, org_id, limit, offset)

    def create_character(self, universe_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Create a character under an owned universe."""
        return self.repository.create_character(universe_id, data, org_id)

    def update_character(self, character_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Update an organization-owned character."""
        return self.repository.update_character(character_id, data, org_id)

    def delete_character(self, character_id: str, org_id: str) -> None:
        """Delete an organization-owned character."""
        self.repository.delete_character(character_id, org_id)

    def list_episodes(self, universe_id: str, org_id: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """List episodes under an owned universe."""
        return self.repository.list_episodes(universe_id, org_id, limit, offset)

    def create_episode(self, universe_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Create an episode under an owned universe."""
        return self.repository.create_episode(universe_id, data, org_id)

    def get_episode(self, episode_id: str, org_id: str) -> dict[str, Any]:
        """Get an organization-owned episode."""
        return self.repository.get_episode(episode_id, org_id)

    def update_episode(self, episode_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Update an organization-owned episode."""
        return self.repository.update_episode(episode_id, data, org_id)

    def delete_episode(self, episode_id: str, org_id: str) -> None:
        """Delete an organization-owned episode."""
        self.repository.delete_episode(episode_id, org_id)

    def list_scenes(self, episode_id: str, org_id: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """List scenes under an owned episode."""
        return self.repository.list_scenes(episode_id, org_id, limit, offset)

    def create_scene(self, episode_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Create a scene under an owned episode."""
        return self.repository.create_scene(episode_id, data, org_id)

    def update_scene(self, scene_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Update an organization-owned scene."""
        return self.repository.update_scene(scene_id, data, org_id)

    def delete_scene(self, scene_id: str, org_id: str) -> None:
        """Delete an organization-owned scene."""
        self.repository.delete_scene(scene_id, org_id)

    def list_shots(self, scene_id: str, org_id: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """List shots under an owned scene."""
        return self.repository.list_shots(scene_id, org_id, limit, offset)

    def create_shot(self, scene_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Create a shot under an owned scene."""
        return self.repository.create_shot(scene_id, data, org_id)

    def update_shot(self, shot_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Update an organization-owned shot."""
        return self.repository.update_shot(shot_id, data, org_id)

    def update_shot_write(self, shot_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Persist the WRITE editor's typed shot fields for one tenant."""
        return self.repository.update_shot_write(shot_id, data, org_id)

    def generate_shot_preview(
        self, shot_id: str, request: Any, org_id: str, user_id: str
    ) -> dict[str, Any]:
        """Validate context and enqueue a cost-recorded preview asynchronously."""
        self.repository.validate_preview_context(shot_id, request, org_id)
        model_id = request.model_id or "h3-preview"
        workflow_id = request.workflow_id or "h3-preview"
        provenance = {
            "shot_id": shot_id,
            "workflow_id": workflow_id,
            "model_id": model_id,
            "seed": request.seed,
            "quality": request.quality,
            "steps": request.steps,
            "height": request.height,
            "frame_grid": request.frame_grid,
            "previous_shot_id": str(request.previous_shot_id) if request.previous_shot_id else None,
            "character_ids": [str(value) for value in request.character_ids],
            "location": request.location,
            "continuity": request.continuity,
            "reference_asset_ids": [str(value) for value in request.reference_asset_ids],
            "estimated_cost_usd": PREVIEW_ESTIMATED_COST_USD,
        }
        try:
            job = submit_generation(
                org_id=org_id,
                user_id=user_id,
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                model=model_id,
                width=768,
                height=request.height,
                steps=request.steps,
                seed=request.seed,
                estimated_cost_usd=PREVIEW_ESTIMATED_COST_USD,
                idempotency_key=f"shot-preview:{org_id}:{shot_id}:{request.seed}",
            )
        except SubmissionError as exc:
            raise StoryGenerationError("Preview generation could not be queued") from exc
        job.effective_settings = provenance
        return {
            "shot_id": shot_id,
            "job_id": job.id,
            "status": job.state.value,
            "workflow_id": workflow_id,
            "model_id": model_id,
            "seed": request.seed,
            "estimated_cost_usd": PREVIEW_ESTIMATED_COST_USD,
            "generation_result": {
                "job_id": job.id,
                "status": job.state.value,
                "workflow_id": workflow_id,
                "model_id": model_id,
                "seed": request.seed,
            },
        }

    def delete_shot(self, shot_id: str, org_id: str) -> None:
        """Delete an organization-owned shot."""
        self.repository.delete_shot(shot_id, org_id)
