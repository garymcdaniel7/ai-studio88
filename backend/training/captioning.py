"""Training image captioning — auto-generate captions for LoRA training datasets.

Supports multiple captioning backends:
- Simulated (default): Template-based captions with trigger words
- LLM (Ollama): Use local LLM to describe images
- Vision API (future): BLIP-2, Florence-2, LLaVA via GPU worker

Good captions are critical for LoRA quality. Each caption should:
- Include the trigger word
- Describe the subject, pose, lighting, background
- Be 50-150 tokens long
- Avoid generic descriptions
"""

from __future__ import annotations

import os


def generate_caption(
    image_url: str,
    trigger_word: str = "aistudio_character",
    style: str = "detailed",
    backend: str = "simulation",
) -> str:
    """Generate a caption for a training image.

    Args:
        image_url: URL or path to the image
        trigger_word: LoRA trigger word to include
        style: "detailed" | "simple" | "tag_based"
        backend: "simulation" | "ollama" | "blip"

    Returns:
        Generated caption string
    """
    if backend == "ollama":
        return _caption_with_ollama(image_url, trigger_word)
    elif backend == "blip":
        return _caption_with_vision_model(image_url, trigger_word)
    else:
        return _caption_simulated(trigger_word, style)


def _caption_simulated(trigger_word: str, style: str) -> str:
    """Generate a template-based caption (no AI needed)."""
    if style == "tag_based":
        return (
            f"{trigger_word}, portrait, high quality, professional photo, "
            f"studio lighting, sharp focus, detailed"
        )
    elif style == "simple":
        return f"a photo of {trigger_word}, professional quality"
    else:
        return (
            f"{trigger_word}, professional portrait photography, "
            f"high resolution, sharp focus, natural lighting, "
            f"detailed face and features, studio quality, "
            f"clean background, professional pose"
        )


def _caption_with_ollama(image_url: str, trigger_word: str) -> str:
    """Use local Ollama (llava or llama3.2-vision) to caption an image."""
    import httpx

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")

    try:
        # Use llava or llama3.2-vision for image description
        resp = httpx.post(
            f"{ollama_url}/api/generate",
            json={
                "model": "llava",
                "prompt": (
                    f"Describe this image in detail for AI training. "
                    f"Start with the word '{trigger_word}'. "
                    f"Include: subject appearance, pose, lighting, background, "
                    f"clothing, mood."
                ),
                "images": [image_url] if image_url.startswith("http") else [],
                "stream": False,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json().get("response", _caption_simulated(trigger_word, "detailed"))
    except Exception:
        pass

    return _caption_simulated(trigger_word, "detailed")


def _caption_with_vision_model(image_url: str, trigger_word: str) -> str:
    """Use BLIP-2 or Florence-2 on GPU worker for captioning (future)."""
    # This would SSH to the GPU worker and run a vision model
    # For now, fall back to simulation
    return _caption_simulated(trigger_word, "detailed")
