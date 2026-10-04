"""Typed request and response schemas for the Phase 1 story API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StrictInt, model_validator

from backend.app.schemas.base import BaseSchema, StrictBaseSchema
from backend.video.adapters.thunder_h3_adapter import validate_h3_length


class StoryResponseSchema(BaseSchema):
    """Base response schema that tolerates server-managed columns added later."""

    model_config = ConfigDict(
        extra="ignore",
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    id: UUID
    org_id: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PageSchema(BaseSchema):
    """Standard paginated response envelope."""

    items: list[Any]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class UniverseCreate(StrictBaseSchema):
    """Fields accepted when creating a universe."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    genre: str | None = Field(default=None, max_length=100)
    tone: str | None = Field(default=None, max_length=100)
    setting: str | None = Field(default=None, max_length=5000)
    project_id: UUID | None = None
    rules: list[str] = Field(default_factory=list, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UniversePatch(StrictBaseSchema):
    """Fields that may be changed on an existing universe."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    genre: str | None = Field(default=None, max_length=100)
    tone: str | None = Field(default=None, max_length=100)
    setting: str | None = Field(default=None, max_length=5000)
    project_id: UUID | None = None
    rules: list[str] | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] | None = None


class UniverseResponse(StoryResponseSchema):
    """Universe returned by the story API."""

    name: str
    description: str | None = None
    genre: str | None = None
    tone: str | None = None
    setting: str | None = None
    project_id: UUID | None = None
    rules: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CharacterCreate(StrictBaseSchema):
    """Fields accepted when adding a character to a universe."""

    talent_id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    personality: str | None = Field(default=None, max_length=5000)
    goals: str | None = Field(default=None, max_length=5000)
    backstory: str | None = Field(default=None, max_length=10000)
    voice_style: str | None = Field(default=None, max_length=1000)
    wardrobe_default: str | None = Field(default=None, max_length=1000)
    relationships: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    memory: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    visual_dna: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CharacterPatch(StrictBaseSchema):
    """Fields that may be changed on an existing character."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    talent_id: UUID | None = None
    description: str | None = Field(default=None, max_length=5000)
    personality: str | None = Field(default=None, max_length=5000)
    goals: str | None = Field(default=None, max_length=5000)
    backstory: str | None = Field(default=None, max_length=10000)
    voice_style: str | None = Field(default=None, max_length=1000)
    wardrobe_default: str | None = Field(default=None, max_length=1000)
    relationships: list[dict[str, Any]] | None = Field(default=None, max_length=100)
    memory: list[dict[str, Any]] | None = Field(default=None, max_length=100)
    visual_dna: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class CharacterResponse(StoryResponseSchema):
    """Character returned by the story API."""

    universe_id: UUID
    talent_id: UUID | None = None
    name: str
    description: str | None = None
    personality: str | None = None
    goals: str | None = None
    backstory: str | None = None
    voice_style: str | None = None
    wardrobe_default: str | None = None
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    memory: list[dict[str, Any]] = Field(default_factory=list)
    visual_dna: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


EpisodeStatus = Literal["draft", "planned", "in_production", "completed", "published"]


class EpisodeCreate(StrictBaseSchema):
    """Fields accepted when adding an episode to a universe."""

    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10000)
    episode_number: int = Field(default=1, ge=1, le=10000)
    status: EpisodeStatus = "draft"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EpisodePatch(StrictBaseSchema):
    """Fields that may be changed on an existing episode."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10000)
    episode_number: int | None = Field(default=None, ge=1, le=10000)
    status: EpisodeStatus | None = None
    metadata: dict[str, Any] | None = None


class EpisodeResponse(StoryResponseSchema):
    """Episode returned by the story API."""

    universe_id: UUID
    title: str
    description: str | None = None
    episode_number: int = Field(ge=1)
    status: str
    scenes: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SceneCreate(StrictBaseSchema):
    """Fields accepted when adding a scene to an episode."""

    scene_number: int = Field(default=1, ge=1, le=10000)
    title: str | None = Field(default=None, max_length=300)
    purpose: str | None = Field(default=None, max_length=5000)
    location: str | None = Field(default=None, max_length=1000)
    time_of_day: str = Field(default="day", min_length=1, max_length=50)
    weather: str = Field(default="clear", min_length=1, max_length=100)
    mood: str | None = Field(default=None, max_length=500)
    characters: list[UUID] = Field(default_factory=list, max_length=100)
    dialogue: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    camera_style: str | None = Field(default=None, max_length=500)
    music: str | None = Field(default=None, max_length=500)
    desired_emotion: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScenePatch(StrictBaseSchema):
    """Fields that may be changed on an existing scene."""

    scene_number: int | None = Field(default=None, ge=1, le=10000)
    title: str | None = Field(default=None, max_length=300)
    purpose: str | None = Field(default=None, max_length=5000)
    location: str | None = Field(default=None, max_length=1000)
    time_of_day: str | None = Field(default=None, min_length=1, max_length=50)
    weather: str | None = Field(default=None, min_length=1, max_length=100)
    mood: str | None = Field(default=None, max_length=500)
    characters: list[UUID] | None = Field(default=None, max_length=100)
    dialogue: list[dict[str, Any]] | None = Field(default=None, max_length=100)
    camera_style: str | None = Field(default=None, max_length=500)
    music: str | None = Field(default=None, max_length=500)
    desired_emotion: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] | None = None


class SceneResponse(StoryResponseSchema):
    """Scene returned by the story API."""

    episode_id: UUID
    scene_number: int = Field(ge=1)
    title: str | None = None
    purpose: str | None = None
    location: str | None = None
    time_of_day: str
    weather: str
    mood: str | None = None
    characters: list[UUID] = Field(default_factory=list)
    dialogue: list[dict[str, Any]] = Field(default_factory=list)
    camera_style: str | None = None
    music: str | None = None
    desired_emotion: str | None = None
    shots: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ShotCreate(StrictBaseSchema):
    """Fields accepted when adding a shot to a scene."""

    shot_number: int = Field(default=1, ge=1, le=10000)
    shot_type: str = Field(default="medium", min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=10000)
    characters: list[UUID] = Field(default_factory=list, max_length=100)
    camera_movement: str | None = Field(default=None, max_length=100)
    duration_seconds: float = Field(default=3.0, gt=0, le=3600)
    dialogue: str | None = Field(default=None, max_length=10000)
    action: str | None = Field(default=None, max_length=10000)
    mood: str | None = Field(default=None, max_length=500)
    transition: str = Field(default="cut", min_length=1, max_length=50)
    generation_params: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="planned", min_length=1, max_length=50)
    asset_id: UUID | None = None
    job_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ShotPatch(StrictBaseSchema):
    """Fields that may be changed on an existing shot."""

    shot_number: int | None = Field(default=None, ge=1, le=10000)
    shot_type: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=10000)
    characters: list[UUID] | None = Field(default=None, max_length=100)
    camera_movement: str | None = Field(default=None, max_length=100)
    duration_seconds: float | None = Field(default=None, gt=0, le=3600)
    dialogue: str | None = Field(default=None, max_length=10000)
    action: str | None = Field(default=None, max_length=10000)
    mood: str | None = Field(default=None, max_length=500)
    transition: str | None = Field(default=None, min_length=1, max_length=50)
    generation_params: dict[str, Any] | None = None
    status: str | None = Field(default=None, min_length=1, max_length=50)
    asset_id: UUID | None = None
    job_id: UUID | None = None
    metadata: dict[str, Any] | None = None


class ShotWriteUpdate(StrictBaseSchema):
    """WRITE-compatible shot update payload.

    The WRITE editor calls this compatibility surface with a prompt/description,
    generation parameters, and continuity/reference metadata. Ownership fields,
    assets, jobs, and status remain server-managed.
    """

    prompt: str | None = Field(default=None, min_length=1, max_length=10000)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    generation_params: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_write_payload(self) -> ShotWriteUpdate:
        """Require an editable field and validate prompt/reference semantics."""
        if all(value is None for value in (self.prompt, self.description, self.generation_params, self.metadata)):
            raise ValueError("At least one shot field is required")
        if self.prompt is not None and self.description is not None and self.prompt != self.description:
            raise ValueError("prompt and description must match when both are provided")
        if self.generation_params and "frame_grid" in self.generation_params:
            validate_h3_length(self.generation_params["frame_grid"])
        _validate_reference_metadata(self.metadata)
        return self


class ShotPreviewRequest(StrictBaseSchema):
    """Typed preview-generation request from the WRITE editor."""

    prompt: str = Field(min_length=1, max_length=10000)
    negative_prompt: str = Field(default="", max_length=10000)
    quality: Literal["preview"]
    steps: StrictInt = 4
    height: StrictInt = 480
    frame_grid: StrictInt
    seed: int = Field(ge=0, le=2_147_483_647)
    previous_shot_id: UUID | None = None
    character_ids: list[UUID] = Field(default_factory=list, max_length=100)
    location: str | None = Field(default=None, max_length=1000)
    continuity: str = Field(default="", max_length=5000)
    reference_asset_ids: list[UUID] = Field(default_factory=list, max_length=4)
    workflow_id: str | None = Field(default=None, min_length=1, max_length=200)
    model_id: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_preview_contract(self) -> ShotPreviewRequest:
        """Reject unsupported H3 frame values and duplicate ordered references."""
        validate_h3_length(self.frame_grid)
        if self.steps != 4 or self.height != 480:
            raise ValueError("preview requests require steps=4 and height=480")
        if len(set(self.reference_asset_ids)) != len(self.reference_asset_ids):
            raise ValueError("reference_asset_ids must be unique and ordered")
        if len(set(self.character_ids)) != len(self.character_ids):
            raise ValueError("character_ids must be unique")
        return self


class PreviewGenerationResponse(StrictBaseSchema):
    """Queued preview response retaining generation provenance."""

    shot_id: UUID
    job_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    workflow_id: str | None = None
    model_id: str | None = None
    seed: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    generation_result: dict[str, Any] = Field(default_factory=dict)


def _validate_reference_metadata(metadata: dict[str, Any] | None) -> None:
    """Validate ordered reference IDs without trusting client-supplied URLs."""
    if metadata is None:
        return
    references = metadata.get("references")
    reference_asset_ids = metadata.get("reference_asset_ids")
    reference_ids: list[UUID] | None = None
    if references is not None:
        if not isinstance(references, list) or len(references) > 4:
            raise ValueError("metadata.references must contain at most four assets")
        reference_ids = []
        for reference in references:
            if not isinstance(reference, dict) or "id" not in reference:
                raise ValueError("metadata.references entries require an id")
            try:
                reference_ids.append(UUID(str(reference["id"])))
            except (TypeError, ValueError) as exc:
                raise ValueError("metadata.references contains an invalid asset id") from exc
        if len(set(reference_ids)) != len(reference_ids):
            raise ValueError("metadata.references must preserve unique asset order")
    if reference_asset_ids is not None:
        if not isinstance(reference_asset_ids, list) or len(reference_asset_ids) > 4:
            raise ValueError("metadata.reference_asset_ids must contain at most four assets")
        try:
            parsed_ids = [UUID(str(value)) for value in reference_asset_ids]
        except (TypeError, ValueError) as exc:
            raise ValueError("metadata.reference_asset_ids contains an invalid asset id") from exc
        if len(set(parsed_ids)) != len(parsed_ids):
            raise ValueError("metadata.reference_asset_ids must preserve unique asset order")
        if reference_ids is not None and parsed_ids != reference_ids:
            raise ValueError("references and reference_asset_ids must have the same order")
    continuity = metadata.get("continuity")
    if continuity is not None and (not isinstance(continuity, str) or len(continuity) > 5000):
        raise ValueError("metadata.continuity must be text of at most 5000 characters")


class ShotResponse(StoryResponseSchema):
    """Shot returned by the story API."""

    scene_id: UUID
    shot_number: int = Field(ge=1)
    shot_type: str
    description: str | None = None
    characters: list[UUID] = Field(default_factory=list)
    camera_movement: str | None = None
    duration_seconds: float = Field(gt=0)
    dialogue: str | None = None
    action: str | None = None
    mood: str | None = None
    transition: str
    generation_params: dict[str, Any] = Field(default_factory=dict)
    status: str
    asset_id: UUID | None = None
    job_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UniversePage(PageSchema):
    """Paginated universe response."""

    items: list[UniverseResponse]


class CharacterPage(PageSchema):
    """Paginated character response."""

    items: list[CharacterResponse]


class EpisodePage(PageSchema):
    """Paginated episode response."""

    items: list[EpisodeResponse]


class ScenePage(PageSchema):
    """Paginated scene response."""

    items: list[SceneResponse]


class ShotPage(PageSchema):
    """Paginated shot response."""

    items: list[ShotResponse]
