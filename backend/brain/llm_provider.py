"""LLM Provider for AI Brain — connects to Ollama, OpenAI, or Anthropic.

The Brain uses this to power conversations, creative planning,
prompt engineering, and production advice.

Configuration:
    BRAIN_PROVIDER — ollama | openai | anthropic | openrouter
    OLLAMA_BASE_URL — http://localhost:11434 (default)
    OLLAMA_MODEL — llama3.1 (default)
    OPENAI_API_KEY — for OpenAI provider
    ANTHROPIC_API_KEY — for Anthropic provider
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os

import httpx
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)

BRAIN_PROVIDER = os.getenv("BRAIN_PROVIDER", "ollama")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

SYSTEM_PROMPT = """You are the AI Brain for AI Studio — a creative production platform.
You help with:
- Creative direction and brainstorming
- Prompt engineering for image/video generation
- Story development and scriptwriting
- Production planning and workflow optimization
- Marketing strategy and content calendars
- Technical advice on models, LoRAs, and workflows

Be creative, specific, and production-ready in your responses.
Format output clearly with bullet points, headers, and structured plans when appropriate."""

# Mode-specific system prompts
BRAIN_MODE_PROMPTS = {
    "creative": """You are the Creative Director AI for AI Studio. You brainstorm ideas, explore concepts, and push creative boundaries. Be inspiring, bold, and imaginative. Suggest unexpected angles and fresh perspectives. Always relate ideas back to visual content that can be produced.""",
    "prompt_engineer": """You are a Prompt Engineering Specialist for AI image/video generation. You optimize prompts for SDXL, Flux Dev, and WAN 2.1 models.
Rules:
- Use specific, descriptive language (not vague)
- Include technical terms: lighting (golden hour, studio), camera (85mm, wide angle), style (photorealistic, editorial)
- Add quality boosters: 8k, sharp, detailed, professional
- Structure: subject + environment + style + technical + quality
- For negative prompts: ugly, blurry, low quality, artifacts, cartoon
- Always provide both positive and negative prompts""",
    "story_assistant": """You are a Story Development AI for AI Studio. You help create:
- Series concepts and story bibles
- Character development and arcs
- Episode outlines and scene breakdowns
- Dialogue and scripts
- Continuity tracking
Think cinematically — every story element should translate to producible content (images, videos, scenes).""",
    "production_advisor": """You are a Production Operations Advisor for AI Studio. You help with:
- Workflow optimization (fewer steps, better results)
- GPU cost estimation and budget planning
- Model selection for specific tasks
- Pipeline design (image → video → voice → publish)
- Scheduling and batch processing strategy
Be practical, cost-conscious, and efficiency-focused. Give specific numbers when possible.""",
    "research": """You are a Research Assistant for AI Studio. You help find:
- Visual references and mood boards
- Trending content styles on social platforms
- Competitor analysis
- Technical documentation
- Best practices and industry standards
Be thorough, cite sources when possible, and summarize findings clearly.""",
    "image_analyzer": """You are a Visual Analysis AI for AI Studio. When given descriptions of images or visual content, you:
- Describe composition, lighting, color palette, mood
- Suggest improvements for better quality
- Recommend camera angles, lens choices, post-processing
- Extract style elements that could be replicated
- Identify what makes the image effective or ineffective
Think like a professional photographer and creative director.""",
}


def get_system_prompt(mode: str = "creative") -> str:
    """Get the system prompt for a specific Brain mode."""
    return BRAIN_MODE_PROMPTS.get(mode, SYSTEM_PROMPT)


class LLMProviderError(Exception):
    """Raised when LLM provider fails."""


def get_brain_health() -> dict:
    """Check if the configured Brain LLM provider is accessible.

    Also reports available fallback providers.
    """
    primary_health = _check_provider_health(BRAIN_PROVIDER)
    if BRAIN_PROVIDER == "ollama":
        try:
            from app.core.config import get_settings
            from app.providers.ollama_config import configuration_from_settings

            ollama = configuration_from_settings(get_settings())
            primary_health.update(
                {
                    "enabled": ollama.enabled,
                    "mode": ollama.mode,
                    "privacy_mode": ollama.privacy_mode,
                    "warning": ollama.warning,
                    "endpoint_exposed": False,
                }
            )
        except Exception:
            # Health must remain safe and useful even during degraded startup.
            primary_health.setdefault("endpoint_exposed", False)

    # Check fallbacks
    fallbacks = []
    if BRAIN_PROVIDER != "openai" and OPENAI_API_KEY:
        fallbacks.append({"provider": "openai", "available": True, "model": OPENAI_MODEL})
    if BRAIN_PROVIDER != "anthropic" and ANTHROPIC_API_KEY:
        fallbacks.append({"provider": "anthropic", "available": True, "model": ANTHROPIC_MODEL})
    if BRAIN_PROVIDER != "ollama":
        ollama_ok = _check_provider_health("ollama").get("connected", False)
        fallbacks.append({"provider": "ollama", "available": ollama_ok, "model": OLLAMA_MODEL})

    primary_health["fallbacks"] = fallbacks
    primary_health["auto_fallback"] = len(fallbacks) > 0
    return primary_health


def _check_provider_health(provider: str) -> dict:
    """Check health of a specific provider."""
    if provider == "ollama":
        # Try all possible Ollama URLs (only localhost and explicit WORKER_API_URL)
        urls_to_try = [OLLAMA_BASE_URL]
        # Only add worker URL if WORKER_API_URL is explicitly set (not SSH host)
        worker_api_url = os.getenv("WORKER_API_URL", "")
        if worker_api_url:
            urls_to_try.append(f"{worker_api_url.rstrip('/')}")  # Worker API proxies Ollama

        for url in urls_to_try:
            try:
                resp = httpx.get(f"{url}/api/tags", timeout=5)
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    model_names = [m.get("name", "") for m in models]
                    return {
                        "provider": "ollama",
                        "connected": True,
                        "model": OLLAMA_MODEL,
                        "available_models": model_names[:5],
                        "source": "local" if "localhost" in url or "127.0.0.1" in url else "gpu_worker",
                        "endpoint_exposed": False,
                    }
            except Exception:
                continue

        return {
            "provider": "ollama",
            "connected": False,
            "error": "Ollama is unavailable",
            "endpoint_exposed": False,
        }

    elif provider == "openai":
        if not OPENAI_API_KEY:
            return {"provider": "openai", "connected": False, "error": "OPENAI_API_KEY not set"}
        return {"provider": "openai", "connected": True, "model": OPENAI_MODEL}

    elif provider == "anthropic":
        if not ANTHROPIC_API_KEY:
            return {
                "provider": "anthropic",
                "connected": False,
                "error": "ANTHROPIC_API_KEY not set",
            }
        return {"provider": "anthropic", "connected": True, "model": ANTHROPIC_MODEL}

    return {"provider": provider, "connected": False, "error": "Unknown provider"}


def chat(
    messages: list[dict],
    model: str | None = None,
    mode: str = "creative",
    images: list[str] | None = None,
    *,
    org_id: str | None = None,
    actor: str | None = None,
    idempotency_key: str | None = None,
) -> str:
    """Send a chat completion request to the configured LLM provider.

    Args:
        messages: List of {"role": "user"|"assistant"|"system", "content": "..."}
        model: Override the default model
        mode: Brain mode (creative, prompt_engineer, story_assistant, production_advisor, research, image_analyzer)
        images: List of base64-encoded images for vision analysis

    Returns:
        The assistant's response text
    """
    # Authenticated Brain requests use the tenant-bound BYO orchestration
    # boundary. Legacy callers without trusted tenant context retain the
    # compatibility chain below and cannot select a tenant or credential.
    if org_id:
        return _chat_via_byo(
            messages,
            model=model,
            actor=actor or "brain",
            org_id=org_id,
            idempotency_key=idempotency_key,
        )

    # Auto-switch to vision model when images are attached
    if images and not model:
        model = _get_vision_model()
        if mode == "image_analyzer" or not any(m.get("role") == "system" for m in messages):
            # Add image analysis system prompt
            messages = [{"role": "system", "content": "You are an expert image analyzer. Describe what you see in detail: composition, lighting, colors, subjects, mood, style. Suggest improvements for AI generation."}] + [m for m in messages if m.get("role") != "system"]

    # Inject images into the last user message (Ollama format)
    if images:
        for i, msg in enumerate(messages):
            if msg.get("role") == "user" and i == len(messages) - 1:
                messages[i] = {**msg, "images": images}
                break

    # Prepend system prompt based on mode if not already present
    system_prompt = get_system_prompt(mode)
    if not messages or messages[0].get("role") != "system":
        messages = [{"role": "system", "content": system_prompt}] + messages

    # Build provider chain: primary + fallbacks
    providers = _get_provider_chain()

    last_error = None
    for provider_name, provider_fn, provider_model in providers:
        try:
            return provider_fn(messages, model or provider_model)
        except LLMProviderError as e:
            last_error = e
            logger.warning(f"Brain provider '{provider_name}' failed: {e}. Trying next...")
            continue
        except Exception as e:
            last_error = LLMProviderError(str(e))
            logger.warning(f"Brain provider '{provider_name}' error: {e}. Trying next...")
            continue

    raise last_error or LLMProviderError("All LLM providers failed")




def _chat_via_byo(
    messages: list[dict],
    *,
    model: str | None,
    actor: str,
    org_id: str,
    idempotency_key: str | None,
) -> str:
    """Complete an authenticated Brain turn through tenant BYO routing."""
    from app.core.config import get_settings
    from app.providers.byo import build_default_registry
    from app.services.provider_orchestration import BYOProviderOrchestrator

    prompt = "\n".join(
        f"{message.get('role', 'user')}: {message.get('content', '')}"
        for message in messages
    )
    stable_key = idempotency_key or hashlib.sha256(prompt.encode()).hexdigest()
    settings = get_settings()
    registry = build_default_registry(settings=settings)
    orchestrator = BYOProviderOrchestrator(org_id=org_id, registry=registry)

    async def dispatch() -> str:
        result = await orchestrator.dispatch_brain_completion(
            prompt,
            model=model or "llama3.1:8b",
            actor=actor,
            idempotency_key=stable_key,
        )
        output = result.result.output
        if isinstance(output, dict):
            if isinstance(output.get("response"), str):
                return output["response"]
            choices = output.get("choices")
            if isinstance(choices, list) and choices:
                message = choices[0].get("message", {})
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    return message["content"]
            candidates = output.get("candidates")
            if isinstance(candidates, list) and candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", []) if isinstance(content, dict) else []
                if parts and isinstance(parts[0].get("text"), str):
                    return parts[0]["text"]
        if isinstance(output, str):
            return output
        raise LLMProviderError("Provider returned no completion content")

    try:
        return asyncio.run(dispatch())
    except LLMProviderError:
        raise
    except Exception as exc:
        # Provider orchestration errors are already classified and secret-free;
        # do not leak provider bodies, URLs, or credentials through Brain errors.
        raise LLMProviderError("Brain provider orchestration failed") from exc


VISION_MODELS = ["llava:7b", "llava:13b", "llama3.2-vision:11b", "bakllava:7b"]


def _get_vision_model() -> str:
    """Get the best available vision model from Ollama."""
    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if resp.status_code == 200:
            available = [m.get("name", "") for m in resp.json().get("models", [])]
            for vm in VISION_MODELS:
                if vm in available or vm.split(":")[0] in " ".join(available):
                    return vm
    except Exception:
        pass
    # Default to llava (will error if not pulled, but that's informative)
    return "llava:7b"


def _get_provider_chain() -> list[tuple[str, callable, str]]:
    """Build ordered provider chain: primary first, then available fallbacks."""
    """Build ordered provider chain: primary first, then available fallbacks."""
    chain = []

    # Primary provider always first
    if BRAIN_PROVIDER == "ollama":
        chain.append(("ollama", _chat_ollama, OLLAMA_MODEL))
    elif BRAIN_PROVIDER == "openai":
        chain.append(("openai", _chat_openai, OPENAI_MODEL))
    elif BRAIN_PROVIDER == "anthropic":
        chain.append(("anthropic", _chat_anthropic, ANTHROPIC_MODEL))

    # Add fallbacks (only if API keys are configured)
    if BRAIN_PROVIDER != "openai" and OPENAI_API_KEY:
        chain.append(("openai", _chat_openai, OPENAI_MODEL))
    if BRAIN_PROVIDER != "anthropic" and ANTHROPIC_API_KEY:
        chain.append(("anthropic", _chat_anthropic, ANTHROPIC_MODEL))
    if BRAIN_PROVIDER != "ollama" and OLLAMA_BASE_URL:
        chain.append(("ollama", _chat_ollama, OLLAMA_MODEL))

    return chain


def _chat_ollama(messages: list[dict], model: str) -> str:
    """Chat via Ollama API.

    Tries the configured OLLAMA_BASE_URL first.
    If that fails and a GPU worker is active, tries the worker's Ollama via tunnel.
    """
    urls_to_try = [OLLAMA_BASE_URL]

    # If primary URL is localhost and it might fail (Vercel), also try worker API
    try:
        from backend.infrastructure.worker_api_client import get_worker_client

        _ = get_worker_client()
    except Exception:
        pass

    last_error = None
    for url in urls_to_try:
        try:
            resp = httpx.post(
                f"{url}/api/chat",
                json={"model": model, "messages": messages, "stream": False},
                timeout=120,
            )
            if resp.status_code == 200:
                return resp.json().get("message", {}).get("content", "")
            last_error = LLMProviderError("Ollama request failed")
        except httpx.ConnectError:
            last_error = LLMProviderError("Ollama is unavailable")
        except Exception:
            last_error = LLMProviderError("Ollama request failed")

    raise last_error or LLMProviderError("Ollama not reachable at any configured URL")


def _chat_openai(messages: list[dict], model: str) -> str:
    """Chat via OpenAI API."""
    if not OPENAI_API_KEY:
        raise LLMProviderError("OPENAI_API_KEY not configured")
    try:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": model, "messages": messages},
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        raise LLMProviderError(f"OpenAI returned {resp.status_code}: {resp.text[:200]}")
    except httpx.ConnectError:
        raise LLMProviderError("Cannot reach OpenAI API")


def _chat_anthropic(messages: list[dict], model: str) -> str:
    """Chat via Anthropic API."""
    if not ANTHROPIC_API_KEY:
        raise LLMProviderError("ANTHROPIC_API_KEY not configured")

    # Anthropic uses a different format — system is separate
    system = ""
    chat_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system = msg["content"]
        else:
            chat_messages.append(msg)

    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "system": system,
                "messages": chat_messages,
                "max_tokens": 4096,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            content = resp.json().get("content", [])
            return content[0]["text"] if content else ""
        raise LLMProviderError(f"Anthropic returned {resp.status_code}: {resp.text[:200]}")
    except httpx.ConnectError:
        raise LLMProviderError("Cannot reach Anthropic API")
