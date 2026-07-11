"""LoRA Injector — Injects LoraLoader nodes into ComfyUI workflows.

Given a workflow JSON and a list of LoRA configs, this module:
1. Finds the model loader node (CheckpointLoaderSimple or UNETLoader)
2. Inserts a LoraLoader node between the model loader and the sampler
3. Chains multiple LoRAs if needed

This enables using trained LoRAs (identity, style) in generation without
manually editing workflow templates.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any


def inject_loras(
    workflow: dict[str, Any],
    loras: list[dict],
) -> dict[str, Any]:
    """Inject LoRA loader nodes into a ComfyUI workflow.

    Args:
        workflow: The ComfyUI workflow JSON (API format, node-keyed dict)
        loras: List of LoRA configs, each with:
            - filename: str (e.g. "my_lora.safetensors")
            - strength_model: float (0.0-2.0, default 1.0)
            - strength_clip: float (0.0-2.0, default 1.0)

    Returns:
        Modified workflow with LoraLoader nodes inserted.
    """
    if not loras:
        return workflow

    wf = copy.deepcopy(workflow)

    # Find the checkpoint/model loader node
    model_node_id = None
    model_output_idx = 0
    clip_output_idx = 1

    for node_id, node in wf.items():
        class_type = node.get("class_type", "")
        if class_type in ("CheckpointLoaderSimple", "CheckpointLoader", "UNETLoader"):
            model_node_id = node_id
            break

    if not model_node_id:
        # Can't inject without a model loader — return as-is
        return wf

    # Find nodes that reference the model loader's MODEL output
    # These need to be rewired to point to the last LoRA node instead
    consumers = []
    for node_id, node in wf.items():
        inputs = node.get("inputs", {})
        for input_key, input_val in inputs.items():
            if isinstance(input_val, list) and len(input_val) == 2:
                if str(input_val[0]) == str(model_node_id):
                    consumers.append((node_id, input_key, input_val[1]))

    # Insert LoRA chain
    prev_model_source = [model_node_id, model_output_idx]
    prev_clip_source = [model_node_id, clip_output_idx]

    for lora_config in loras:
        lora_node_id = f"lora_{uuid.uuid4().hex[:8]}"
        lora_node = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora_config.get("filename", ""),
                "strength_model": lora_config.get("strength_model", 1.0),
                "strength_clip": lora_config.get("strength_clip", 1.0),
                "model": prev_model_source,
                "clip": prev_clip_source,
            },
        }
        wf[lora_node_id] = lora_node
        prev_model_source = [lora_node_id, 0]
        prev_clip_source = [lora_node_id, 1]

    # Rewire consumers to point to the last LoRA node
    for node_id, input_key, output_idx in consumers:
        if output_idx == model_output_idx:
            wf[node_id]["inputs"][input_key] = prev_model_source
        elif output_idx == clip_output_idx:
            wf[node_id]["inputs"][input_key] = prev_clip_source

    return wf


def build_lora_config_for_talent(talent_id: str) -> list[dict]:
    """Build the LoRA config list for a talent (identity + always-on style LoRAs).

    Queries the talent_loras table and lora_versions for this talent,
    returning configs ready for inject_loras().
    """
    try:
        from backend.database import supabase

        configs = []

        # Identity LoRAs from lora_versions
        lora_versions = (
            supabase.table("lora_versions")
            .select("*")
            .eq("talent_id", talent_id)
            .eq("status", "active")
            .execute()
            .data
            or []
        )

        for lv in lora_versions:
            model_id = lv.get("model_id")
            if model_id:
                model = (
                    supabase.table("models")
                    .select("storage_path")
                    .eq("id", model_id)
                    .single()
                    .execute()
                    .data
                )
                if model and model.get("storage_path"):
                    filename = model["storage_path"].split("/")[-1]
                    configs.append(
                        {
                            "filename": filename,
                            "strength_model": lv.get("recommended_strength", 0.7),
                            "strength_clip": lv.get("recommended_strength", 0.7),
                            "type": "identity",
                        }
                    )

        # Always-on style LoRAs from talent_loras
        style_loras = (
            supabase.table("talent_loras")
            .select("*")
            .eq("talent_id", talent_id)
            .eq("always_on", True)
            .execute()
            .data
            or []
        )

        for sl in style_loras:
            model_id = sl.get("model_id")
            if model_id:
                model = (
                    supabase.table("models")
                    .select("storage_path")
                    .eq("id", model_id)
                    .single()
                    .execute()
                    .data
                )
                if model and model.get("storage_path"):
                    filename = model["storage_path"].split("/")[-1]
                    configs.append(
                        {
                            "filename": filename,
                            "strength_model": sl.get("strength", 0.7),
                            "strength_clip": sl.get("strength", 0.7),
                            "type": "style",
                        }
                    )

        return configs
    except Exception:
        return []
