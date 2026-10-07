"""Preset Composer — constraint-aware merge of model × pipeline × LoRA presets.

Every param carries a constraint tag that determines merge behavior:
  immutable_base   — Model-level invariant. LoRA override silently dropped.
  immutable        — LoRA's value wins. Base value replaced, no negotiation.
  composable       — Freely merges. Base + LoRA override combine additively.
  conflict_if_overridden — If both set, raise conflict — user must choose.
  hard_dependency  — Requires another param to also be set (within LoRA registry).
  trigger_position — Token must appear in a specific prompt field position (submission-time).

Priority chain: immutable_base > immutable > composable
"""

from __future__ import annotations

import re

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# =============================================================================
# Constraint Tag Enum
# =============================================================================


class ConstraintTag(str, Enum):
    """Merge behavior tags for every parameter in the preset system.

    Priority (high → low): IMMUTABLE_BASE > IMMUTABLE > CONFLICT_IF_OVERRIDDEN > COMPOSABLE
    HARD_DEPENDENCY and TRIGGER_POSITION are orthogonal — checked at wire/submit time.
    """

    IMMUTABLE_BASE = "immutable_base"
    IMMUTABLE = "immutable"
    COMPOSABLE = "composable"
    CONFLICT_IF_OVERRIDDEN = "conflict_if_overridden"
    HARD_DEPENDENCY = "hard_dependency"
    TRIGGER_POSITION = "trigger_position"


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class ConstrainedParam:
    """A single parameter with its value, constraint tag, and optional metadata."""

    value: Any
    tag: ConstraintTag
    description: str = ""
    depends_on: str | None = None  # For hard_dependency: param name required
    position: int | None = None  # For trigger_position: expected token index (0-based)


@dataclass
class Preset:
    """A named preset bundle — one per model, pipeline type, or LoRA."""

    name: str
    label: str
    params: dict[str, ConstrainedParam] = field(default_factory=dict)
    requires_loras: list[str] = field(default_factory=list)  # LoRAs required by this preset


@dataclass
class MergeResult:
    """Result of merging two or more presets."""

    params: dict[str, Any]  # Resolved parameter values
    conflicts: list[Conflict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    dropped_overrides: list[str] = field(default_factory=list)  # Silently dropped by immutable_base
    hard_dependency_blocked: bool = False  # True if a hard dependency is missing


@dataclass
class Conflict:
    """A conflict that requires user resolution."""

    param: str
    base_value: Any
    lora_value: Any
    description: str


# =============================================================================
# MODEL PRESETS — production-validated (@ai-studio)
# =============================================================================

MODEL_PRESETS: dict[str, Preset] = {
    # ------------------------------------------------------------------
    # Krea 2 — PRIMARY photoreal NSFW stills
    # ------------------------------------------------------------------
    "krea2_nsfw": Preset(
        name="krea2_nsfw",
        label="Krea 2 NSFW",
        params={
            "steps": ConstrainedParam(12, ConstraintTag.COMPOSABLE, "Standard Krea 2 step count"),
            "cfg": ConstrainedParam(1.0, ConstraintTag.COMPOSABLE, "CFG scale"),
            "sampler_name": ConstrainedParam("exp_heun_2_x0_sde", ConstraintTag.IMMUTABLE_BASE,
                                             "Krea 2 homofidelis: only exp_heun produces correct results"),
            "scheduler": ConstrainedParam("linear_quadratic", ConstraintTag.IMMUTABLE_BASE,
                                          "Krea 2 homofidelis: linear_quadratic required"),
            "clip_encoder": ConstrainedParam("qwen3vl_4b_fp8_scaled", ConstraintTag.IMMUTABLE_BASE,
                                             "Krea 2: Qwen3VL 4B encoder required"),
            "encoder_type": ConstrainedParam("krea2", ConstraintTag.IMMUTABLE_BASE,
                                             "Krea 2: krea2 encoder type required"),
            "trigger_token": ConstrainedParam("CBUNCT", ConstraintTag.TRIGGER_POSITION,
                                              "Krea 2: CBUNCT trigger must be first token",
                                              position=0),
            "prompt_style": ConstrainedParam("natural_language_photo_brief", ConstraintTag.COMPOSABLE,
                                             "Natural-language photo briefs, NOT tag lists"),
        },
    ),
    # ------------------------------------------------------------------
    # FLUX.2 Klein 9B — img2img edits, face detail passes
    # ------------------------------------------------------------------
    "klein_9b": Preset(
        name="klein_9b",
        label="FLUX.2 Klein 9B",
        params={
            "steps": ConstrainedParam(10, ConstraintTag.IMMUTABLE_BASE,
                                      "Klein 9B: 10 steps max. NEVER 24-step dpmpp (mush bug)"),
            "cfg": ConstrainedParam(1.0, ConstraintTag.COMPOSABLE, "CFG scale"),
            "sampler_name": ConstrainedParam("euler", ConstraintTag.IMMUTABLE_BASE,
                                             "Klein 9B: euler only. NEVER dpmpp (mush bug)"),
            "scheduler": ConstrainedParam("simple", ConstraintTag.IMMUTABLE_BASE,
                                          "Klein 9B: simple scheduler required"),
            "clip_encoder": ConstrainedParam("qwen_3_8b_fp8mixed", ConstraintTag.IMMUTABLE_BASE,
                                             "Klein: Qwen3 8B encoder required"),
            "encoder_type": ConstrainedParam("flux2", ConstraintTag.IMMUTABLE_BASE,
                                             "Klein: flux2 encoder type required"),
            "precision": ConstrainedParam("fp8", ConstraintTag.IMMUTABLE_BASE,
                                          "Klein: fp8 (9.57GB) renders sharp. bf16 (18GB) renders soft mush"),
        },
    ),
    # ------------------------------------------------------------------
    # Klein 4B — backup/lighter lane
    # ------------------------------------------------------------------
    "klein_4b": Preset(
        name="klein_4b",
        label="FLUX.2 Klein 4B",
        params={
            "steps": ConstrainedParam(10, ConstraintTag.IMMUTABLE_BASE,
                                      "Same encoder rules as 9B"),
            "cfg": ConstrainedParam(1.0, ConstraintTag.COMPOSABLE),
            "sampler_name": ConstrainedParam("euler", ConstraintTag.IMMUTABLE_BASE),
            "scheduler": ConstrainedParam("simple", ConstraintTag.IMMUTABLE_BASE),
            "clip_encoder": ConstrainedParam("qwen_3_8b_fp8mixed", ConstraintTag.IMMUTABLE_BASE),
            "encoder_type": ConstrainedParam("flux2", ConstraintTag.IMMUTABLE_BASE),
        },
    ),
    # ------------------------------------------------------------------
    # H3 MiniMax — Turbo (fast iteration lane)
    # ------------------------------------------------------------------
    "h3_turbo": Preset(
        name="h3_turbo",
        label="H3 MiniMax Turbo",
        requires_loras=["lightx2v_turbo_4step", "lightx2v_turbo_8step"],
        params={
            "steps": ConstrainedParam(4, ConstraintTag.COMPOSABLE, "Turbo: 4 steps with LightX2V Turbo LoRA"),
            "cfg": ConstrainedParam(1.0, ConstraintTag.IMMUTABLE_BASE,
                                    "H3 Turbo: cfg 1.0 required. NEVER cfg 4.5 (psychedelic glitch)"),
            "shift_video": ConstrainedParam(1.0, ConstraintTag.IMMUTABLE_BASE,
                                            "H3 Turbo: shift_video 1.0 required. NEVER 6.0 (glitch garbage)"),
            "shift_audio": ConstrainedParam(1.0, ConstraintTag.IMMUTABLE_BASE,
                                            "H3 Turbo: shift_audio 1.0 required"),
            "clip_encoder": ConstrainedParam("qwen3vl_32b_minimax_h3_nvfp4_awq", ConstraintTag.IMMUTABLE_BASE,
                                             "H3: Qwen3VL 32B encoder required"),
            "encoder_type": ConstrainedParam("minimax", ConstraintTag.IMMUTABLE_BASE),
            "frame_count_grid": ConstrainedParam("17k+5", ConstraintTag.IMMUTABLE_BASE,
                                                 "H3 frame count MUST be on 17k+5 grid: 226/243/260/277"),
            "valid_frame_counts": ConstrainedParam([226, 243, 260, 277], ConstraintTag.IMMUTABLE_BASE),
            "sampler_name": ConstrainedParam("res_multistep", ConstraintTag.IMMUTABLE_BASE),
            "scheduler": ConstrainedParam("simple", ConstraintTag.IMMUTABLE_BASE),
        },
    ),
    # ------------------------------------------------------------------
    # H3 MiniMax — Full FL2VA (I2V, general video)
    # ------------------------------------------------------------------
    "h3_full_fl2va": Preset(
        name="h3_full_fl2va",
        label="H3 MiniMax FL2VA",
        params={
            "steps": ConstrainedParam(8, ConstraintTag.COMPOSABLE, "Full: 8 steps standard"),
            "cfg": ConstrainedParam(1.0, ConstraintTag.COMPOSABLE),
            "shift_video": ConstrainedParam(6.0, ConstraintTag.IMMUTABLE_BASE,
                                            "H3 FL2VA: shift_video 6.0 for non-turbo"),
            "shift_audio": ConstrainedParam(3.0, ConstraintTag.IMMUTABLE_BASE,
                                            "H3 FL2VA: shift_audio 3.0 for non-turbo"),
            "clip_encoder": ConstrainedParam("qwen3vl_32b_minimax_h3_nvfp4_awq", ConstraintTag.IMMUTABLE_BASE),
            "encoder_type": ConstrainedParam("minimax", ConstraintTag.IMMUTABLE_BASE),
            "frame_count_grid": ConstrainedParam("17k+5", ConstraintTag.IMMUTABLE_BASE),
            "valid_frame_counts": ConstrainedParam([226, 243, 260, 277], ConstraintTag.IMMUTABLE_BASE),
            "sampler_name": ConstrainedParam("res_multistep", ConstraintTag.IMMUTABLE_BASE),
            "scheduler": ConstrainedParam("simple", ConstraintTag.IMMUTABLE_BASE),
        },
    ),
    # ------------------------------------------------------------------
    # H3 MiniMax — Full Ref2VA (multi-reference identity lock)
    # ------------------------------------------------------------------
    "h3_full_ref2va": Preset(
        name="h3_full_ref2va",
        label="H3 MiniMax Ref2VA",
        params={
            "steps": ConstrainedParam(8, ConstraintTag.COMPOSABLE),
            "cfg": ConstrainedParam(1.0, ConstraintTag.COMPOSABLE),
            "shift_video": ConstrainedParam(12.0, ConstraintTag.IMMUTABLE_BASE,
                                            "H3 Ref2VA: shift_video 12.0. Old shift 1.0 produces blobs"),
            "shift_audio": ConstrainedParam(3.0, ConstraintTag.IMMUTABLE_BASE),
            "clip_encoder": ConstrainedParam("qwen3vl_32b_minimax_h3_nvfp4_awq", ConstraintTag.IMMUTABLE_BASE),
            "encoder_type": ConstrainedParam("minimax", ConstraintTag.IMMUTABLE_BASE),
            "frame_count_grid": ConstrainedParam("17k+5", ConstraintTag.IMMUTABLE_BASE),
            "valid_frame_counts": ConstrainedParam([226, 243, 260, 277], ConstraintTag.IMMUTABLE_BASE),
            "sampler_name": ConstrainedParam("res_multistep", ConstraintTag.IMMUTABLE_BASE),
            "scheduler": ConstrainedParam("simple", ConstraintTag.IMMUTABLE_BASE),
        },
    ),
    # ------------------------------------------------------------------
    # H3 MiniMax — SparseRef15 (identity consistency winner)
    # ------------------------------------------------------------------
    "h3_sparseref15": Preset(
        name="h3_sparseref15",
        label="H3 SparseRef15",
        requires_loras=["joker141_motion_repair", "male_anatomy_v2_02_ep4"],
        params={
            "steps": ConstrainedParam(8, ConstraintTag.COMPOSABLE),
            "cfg": ConstrainedParam(1.0, ConstraintTag.COMPOSABLE),
            "shift_video": ConstrainedParam(12.0, ConstraintTag.IMMUTABLE_BASE,
                                            "SparseRef15: shift_video 12.0 for Ref2VA mode"),
            "shift_audio": ConstrainedParam(3.0, ConstraintTag.IMMUTABLE_BASE),
            "clip_encoder": ConstrainedParam("qwen3vl_32b_minimax_h3_nvfp4_awq", ConstraintTag.IMMUTABLE_BASE),
            "encoder_type": ConstrainedParam("minimax", ConstraintTag.IMMUTABLE_BASE),
            "frame_count_grid": ConstrainedParam("17k+5", ConstraintTag.IMMUTABLE_BASE),
            "valid_frame_counts": ConstrainedParam([226, 243, 260, 277], ConstraintTag.IMMUTABLE_BASE),
            "sampler_name": ConstrainedParam("res_multistep", ConstraintTag.IMMUTABLE_BASE),
            "scheduler": ConstrainedParam("simple", ConstraintTag.IMMUTABLE_BASE),
        },
    ),
    # ------------------------------------------------------------------
    # Wan 2.2 Remix — LoRA lane, fast iteration
    # ------------------------------------------------------------------
    "wan_2_2_remix": Preset(
        name="wan_2_2_remix",
        label="Wan 2.2 Remix 14B",
        params={
            "steps": ConstrainedParam(8, ConstraintTag.COMPOSABLE,
                                      "Wan: 4+4 steps with Lightning LoRAs"),
            "cfg": ConstrainedParam(1.0, ConstraintTag.COMPOSABLE),
            "clip_encoder": ConstrainedParam("shared_clip", ConstraintTag.IMMUTABLE_BASE,
                                             "Wan: uses shared CLIP for LoRA lane"),
            "resolution": ConstrainedParam("480x832_or_832x480", ConstraintTag.IMMUTABLE_BASE,
                                           "Wan: 480×832 or 832×480 only"),
            "sampler_name": ConstrainedParam("res_multistep", ConstraintTag.IMMUTABLE_BASE),
            "scheduler": ConstrainedParam("simple", ConstraintTag.IMMUTABLE_BASE),
        },
    ),
}

# =============================================================================
# PIPELINE TYPE PRESETS — creative direction
# =============================================================================

PIPELINE_PRESETS: dict[str, Preset] = {
    "nsfw": Preset(
        name="nsfw",
        label="NSFW",
        params={
            "pipeline_type": ConstrainedParam("nsfw", ConstraintTag.IMMUTABLE,
                                              "Pipeline type: adult content"),
            "anatomy_description": ConstrainedParam("explicit", ConstraintTag.COMPOSABLE,
                                                    "Explicit anatomy description required"),
            "anti_plastic_clauses": ConstrainedParam(True, ConstraintTag.IMMUTABLE,
                                                     "H3 smooths faces — anti-plastic clauses MANDATORY (pipeline-level requirement, not model invariant)"),
            "anti_plastic_prompt": ConstrainedParam(
                "realistic skin texture with visible pores, natural skin grain, no plastic skin, no waxy skin, no CGI skin, no beauty filter",
                ConstraintTag.COMPOSABLE,
            ),
        },
    ),
    "cinematic": Preset(
        name="cinematic",
        label="Cinematic",
        params={
            "pipeline_type": ConstrainedParam("cinematic", ConstraintTag.IMMUTABLE),
            "aspect_ratio": ConstrainedParam("21:9", ConstraintTag.COMPOSABLE),
            "camera_movement": ConstrainedParam("one_slow_move", ConstraintTag.COMPOSABLE),
            "lighting": ConstrainedParam("cinematic", ConstraintTag.COMPOSABLE),
        },
    ),
    "portrait": Preset(
        name="portrait",
        label="Portrait",
        params={
            "pipeline_type": ConstrainedParam("portrait", ConstraintTag.IMMUTABLE),
            "aspect_ratio": ConstrainedParam("9:16", ConstraintTag.COMPOSABLE),
            "composition": ConstrainedParam("headshot_to_three_quarter", ConstraintTag.COMPOSABLE),
        },
    ),
}

# =============================================================================
# LoRA PRESETS — production-validated with constraint tags
# =============================================================================

LORA_PRESETS: dict[str, Preset] = {
    # Krea 2 LoRAs
    "krea2_uncut_penis_coachbate_v1": Preset(
        name="krea2_uncut_penis_coachbate_v1",
        label="CoachBate Uncut v1 (Krea 2)",
        params={
            "trigger_token": ConstrainedParam("CBUNCT", ConstraintTag.IMMUTABLE,
                                              "CBUNCT gate: trigger token is required",
                                              position=0),
            "injection_point": ConstrainedParam("krea2_text_encoder", ConstraintTag.IMMUTABLE,
                                                "Krea 2: ONLY krea2_text_encoder injection point"),
            "model_compatibility": ConstrainedParam(["krea2_nsfw"], ConstraintTag.IMMUTABLE_BASE,
                                                    "CBUNCT v1: Krea 2 only"),
        },
    ),
    # Klein LoRAs
    "coachbate_penis_v2": Preset(
        name="coachbate_penis_v2",
        label="CoachBate Penis v2 (Klein)",
        params={
            "trigger_token": ConstrainedParam("p3n15", ConstraintTag.IMMUTABLE,
                                              "Klein trigger token: p3n15"),
            "strength": ConstrainedParam(0.75, ConstraintTag.IMMUTABLE_BASE,
                                         "HARD CAP: 0.75 MAX. Higher values cause artifacts"),
            "injection_point": ConstrainedParam("flux2_text_encoder", ConstraintTag.IMMUTABLE),
            "model_compatibility": ConstrainedParam(["klein_9b", "klein_4b"], ConstraintTag.IMMUTABLE_BASE),
        },
    ),
    "klein_unchained_v2": Preset(
        name="klein_unchained_v2",
        label="KLEIN-Unchained-V2",
        params={
            "strength": ConstrainedParam(0.8, ConstraintTag.COMPOSABLE),
            "model_compatibility": ConstrainedParam(["klein_9b", "klein_4b"], ConstraintTag.IMMUTABLE_BASE),
        },
    ),
    "mystic2realism": Preset(
        name="mystic2realism",
        label="Mystic2Realism",
        params={
            "requires_vae_encoding": ConstrainedParam(True, ConstraintTag.IMMUTABLE_BASE,
                                                      "Mystic2Realism: requires explicit VAE encoding"),
            "strength": ConstrainedParam(0.7, ConstraintTag.COMPOSABLE),
            "model_compatibility": ConstrainedParam(["klein_9b", "klein_4b"], ConstraintTag.IMMUTABLE_BASE),
        },
    ),
    "detail_slider": Preset(
        name="detail_slider",
        label="Detail-Slider",
        params={
            "strength": ConstrainedParam(0.5, ConstraintTag.COMPOSABLE,
                                         "Detail-Slider: lower strength for subtle effect"),
            "model_compatibility": ConstrainedParam(["klein_9b", "klein_4b"], ConstraintTag.IMMUTABLE_BASE),
        },
    ),
    # H3 LoRAs
    "joker141_motion_repair": Preset(
        name="joker141_motion_repair",
        label="JOKER141 Motion-Repair",
        params={
            "load_order": ConstrainedParam(1, ConstraintTag.IMMUTABLE,
                                           "JOKER141 MUST load FIRST (load_order: 1)"),
            "strength": ConstrainedParam(0.9, ConstraintTag.COMPOSABLE),
            "model_compatibility": ConstrainedParam(
                ["h3_turbo", "h3_full_fl2va", "h3_full_ref2va", "h3_sparseref15"],
                ConstraintTag.IMMUTABLE_BASE,
            ),
        },
    ),
    "male_anatomy_v2_02_ep4": Preset(
        name="male_anatomy_v2_02_ep4",
        label="Male_Anatomy v2.02 ep4",
        params={
            "load_order": ConstrainedParam(2, ConstraintTag.IMMUTABLE,
                                           "Male_Anatomy MUST load SECOND (load_order: 2)"),
            "strength": ConstrainedParam(0.75, ConstraintTag.COMPOSABLE),
            "model_compatibility": ConstrainedParam(
                ["h3_turbo", "h3_full_fl2va", "h3_full_ref2va", "h3_sparseref15"],
                ConstraintTag.IMMUTABLE_BASE,
            ),
            "load_order_depends_on": ConstrainedParam(True, ConstraintTag.HARD_DEPENDENCY,
                             "Requires JOKER141 motion repair to load first",
                             depends_on="joker141_motion_repair"),
        },
    ),
    "lightx2v_turbo_4step": Preset(
        name="lightx2v_turbo_4step",
        label="LightX2V Turbo 4-step",
        params={
            "steps": ConstrainedParam(4, ConstraintTag.IMMUTABLE,
                                      "Turbo LoRA: forces 4-step"),
            "model_compatibility": ConstrainedParam(["h3_turbo"], ConstraintTag.IMMUTABLE_BASE,
                                                    "LightX2V Turbo: H3 Turbo only"),
        },
    ),
    "lightx2v_turbo_8step": Preset(
        name="lightx2v_turbo_8step",
        label="LightX2V Turbo 8-step",
        params={
            "steps": ConstrainedParam(8, ConstraintTag.IMMUTABLE,
                                      "Turbo LoRA: forces 8-step"),
            "model_compatibility": ConstrainedParam(["h3_turbo"], ConstraintTag.IMMUTABLE_BASE),
        },
    ),
    "coachbate_uncut_v2": Preset(
        name="coachbate_uncut_v2",
        label="CoachBate Uncut v2 (H3)",
        params={
            "model_compatibility": ConstrainedParam(
                ["h3_turbo", "h3_full_fl2va", "h3_full_ref2va", "h3_sparseref15"],
                ConstraintTag.IMMUTABLE_BASE,
            ),
        },
    ),
}

# =============================================================================
# RESOLVER — merge logic with priority enforcement
# =============================================================================

# Priority order for tag resolution
_TAG_PRIORITY = {
    ConstraintTag.IMMUTABLE_BASE: 0,  # Highest — model-level invariant
    ConstraintTag.IMMUTABLE: 1,       # LoRA's override
    ConstraintTag.CONFLICT_IF_OVERRIDDEN: 2,
    ConstraintTag.COMPOSABLE: 3,      # Lowest — freely merges
}


def _tag_priority(tag: ConstraintTag) -> int:
    """Return numeric priority for a constraint tag (lower = higher priority)."""
    return _TAG_PRIORITY.get(tag, 99)


def merge_presets(
    model_name: str,
    pipeline_name: str | None = None,
    lora_names: list[str] | None = None,
) -> MergeResult:
    """Merge model preset + optional pipeline type + optional LoRA presets.

    Priority chain: immutable_base > immutable > composable
    hard_dependency and trigger_position are flagged but not resolved here.

    Args:
        model_name: Key into MODEL_PRESETS.
        pipeline_name: Optional key into PIPELINE_PRESETS.
        lora_names: Optional list of keys into LORA_PRESETS.

    Returns:
        MergeResult with resolved params, conflicts, warnings, and dropped overrides.
    """
    result = MergeResult(params={})

    # Guard: validate lora_names format
    if lora_names is not None:
        for name in lora_names:
            if not re.match(r'^[\w\-\.]+$', name):
                raise ValueError(
                    f"Invalid LoRA name '{name}'. "
                    "LoRA names must only contain "
                    "alphanumeric characters, hyphens, underscores, and dots."
                )

    # 1. Load model preset (required)
    model_preset = MODEL_PRESETS.get(model_name)
    if not model_preset:
        result.warnings.append(f"Unknown model preset: {model_name}")
        return result

    # 2. Load pipeline preset (optional)
    pipeline_preset = PIPELINE_PRESETS.get(pipeline_name) if pipeline_name else None

    # 3. Load LoRA presets (optional)
    lora_presets: list[Preset] = []
    for name in lora_names or []:
        preset = LORA_PRESETS.get(name)
        if preset:
            lora_presets.append(preset)
        else:
            result.warnings.append(f"Unknown LoRA preset: {name}")

    # 4. Check model-LoRA compatibility
    for lp in lora_presets:
        compat = lp.params.get("model_compatibility")
        if compat and compat.value and model_name not in compat.value:
            result.warnings.append(
                f"LoRA '{lp.label}' is not compatible with model '{model_preset.label}'. "
                f"Compatible models: {compat.value}"
            )

    # 5. Check required LoRAs
    for required_lora in model_preset.requires_loras:
        if required_lora not in (lora_names or []):
            result.warnings.append(
                f"Model '{model_preset.label}' requires LoRA '{required_lora}' "
                f"but it was not selected"
            )

    # 6. Check hard_dependencies within LoRA registry
    for lp in lora_presets:
        for param_name, cp in lp.params.items():
            if cp.tag == ConstraintTag.HARD_DEPENDENCY and cp.depends_on:
                # Check that the depended-on LoRA is in the selection
                dep_name = cp.depends_on
                dep_found = any(dep_name == dp.name for dp in lora_presets)
                if not dep_found:
                    result.hard_dependency_blocked = True
                    result.warnings.append(
                        f"LoRA '{lp.label}' requires '{dep_name}' "
                        f"({cp.description}) but it is not loaded"
                    )

    # 7. Merge params: base model → pipeline → LoRA (with priority enforcement)
    # Start with model preset params
    for param_name, cp in model_preset.params.items():
        result.params[param_name] = cp.value

    # Overlay pipeline preset params
    if pipeline_preset:
        for param_name, cp in pipeline_preset.params.items():
            existing_tag = _get_tag(param_name, model_preset, pipeline_preset, lora_presets)
            if existing_tag == ConstraintTag.IMMUTABLE_BASE:
                result.dropped_overrides.append(
                    f"Pipeline '{pipeline_preset.label}' param '{param_name}' "
                    f"silently dropped — model preset has immutable_base"
                )
            elif param_name not in result.params:
                result.params[param_name] = cp.value
            else:
                # Pipeline provides default but model wins on conflict
                pass  # Model preset already set it

    # Overlay LoRA preset params (lowest priority, checked against all)
    for lp in lora_presets:
        for param_name, cp in lp.params.items():
            if cp.tag == ConstraintTag.HARD_DEPENDENCY or cp.tag == ConstraintTag.TRIGGER_POSITION:
                # These are checked elsewhere, not merged
                continue

            existing_value = result.params.get(param_name)
            if existing_value is not None:
                existing_tag = _resolve_existing_tag(param_name, model_preset, pipeline_preset, lora_presets)

                if existing_tag == ConstraintTag.IMMUTABLE_BASE:
                    # Silently drop — model-level invariant wins
                    result.dropped_overrides.append(
                        f"LoRA '{lp.label}' param '{param_name}={cp.value}' "
                        f"silently dropped — model preset has immutable_base"
                    )
                elif existing_tag == ConstraintTag.CONFLICT_IF_OVERRIDDEN:
                    # Raise conflict
                    result.conflicts.append(Conflict(
                        param=param_name,
                        base_value=existing_value,
                        lora_value=cp.value,
                        description=f"LoRA '{lp.label}' overrides '{param_name}' "
                                    f"from {existing_value} to {cp.value} — user must choose",
                    ))
                elif existing_tag == ConstraintTag.IMMUTABLE:
                    # LoRA's value wins if the LoRA setting itself is immutable
                    result.params[param_name] = cp.value
                elif cp.tag == ConstraintTag.IMMUTABLE:
                    # LoRA declares this param immutable — LoRA's value wins
                    result.params[param_name] = cp.value
                else:
                    # Both composable — merge (base value kept, LoRA provides hint)
                    result.params[param_name] = cp.value
            else:
                result.params[param_name] = cp.value

    # 8. Collect trigger_position warnings for submission-time check
    for lp in lora_presets:
        for param_name, cp in lp.params.items():
            if cp.tag == ConstraintTag.TRIGGER_POSITION and cp.position is not None:
                result.warnings.append(
                    f"[SUBMISSION-TIME] '{cp.value}' trigger must be at token position {cp.position} "
                    f"in prompt field '{param_name}'"
                )

    return result


def _get_tag(
    param_name: str,
    model_preset: Preset,
    pipeline_preset: Preset | None,
    lora_presets: list[Preset],
) -> ConstraintTag | None:
    """Resolve the constraint tag for a param across all preset layers."""
    # Model preset has highest priority
    if param_name in model_preset.params:
        return model_preset.params[param_name].tag
    # Then pipeline
    if pipeline_preset and param_name in pipeline_preset.params:
        return pipeline_preset.params[param_name].tag
    # Then LoRAs
    for lp in lora_presets:
        if param_name in lp.params:
            return lp.params[param_name].tag
    return None


def _resolve_existing_tag(
    param_name: str,
    model_preset: Preset,
    pipeline_preset: Preset | None,
    lora_presets: list[Preset],
) -> ConstraintTag | None:
    """Resolve the effective tag for a param already in the merged result."""
    # Model wins
    if param_name in model_preset.params:
        return model_preset.params[param_name].tag
    # Then pipeline
    if pipeline_preset and param_name in pipeline_preset.params:
        return pipeline_preset.params[param_name].tag
    # Then LoRAs (in order, first wins)
    for lp in lora_presets:
        if param_name in lp.params:
            return lp.params[param_name].tag
    return None


def validate_trigger_positions(
    prompt_fields: dict[str, str],
    model_name: str,
    lora_names: list[str] | None = None,
) -> list[str]:
    """Validate trigger_position constraints at submission time.

    Args:
        prompt_fields: Dict of prompt field name → prompt text.
        model_name: Key into MODEL_PRESETS.
        lora_names: Optional list of LoRA keys.

    Returns:
        List of validation warnings (empty if all pass).
    """
    warnings: list[str] = []

    # Check model preset trigger positions
    model_preset = MODEL_PRESETS.get(model_name)
    if model_preset:
        for param_name, cp in model_preset.params.items():
            if cp.tag == ConstraintTag.TRIGGER_POSITION and cp.position is not None:
                field_text = prompt_fields.get(param_name, "")
                tokens = field_text.split()
                if not tokens or tokens[cp.position] != str(cp.value):
                    warnings.append(
                        f"'{cp.value}' trigger must be at token position {cp.position} "
                        f"in '{param_name}'. Your prompt starts with: "
                        f"'{tokens[0] if tokens else '(empty)'}'"
                    )

    # Check LoRA trigger positions
    for name in lora_names or []:
        lp = LORA_PRESETS.get(name)
        if lp:
            for param_name, cp in lp.params.items():
                if cp.tag == ConstraintTag.TRIGGER_POSITION and cp.position is not None:
                    field_text = prompt_fields.get(param_name, "")
                    tokens = field_text.split()
                    if not tokens or tokens[cp.position] != str(cp.value):
                        warnings.append(
                            f"LoRA '{lp.label}': '{cp.value}' trigger must be at "
                            f"token position {cp.position} in '{param_name}'. "
                            f"Your prompt starts with: '{tokens[0] if tokens else '(empty)'}'"
                        )

    return warnings
