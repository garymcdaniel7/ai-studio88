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
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
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
        # Try all possible Ollama URLs
        urls_to_try = [OLLAMA_BASE_URL]
        try:
            from backend.infrastructure.worker_orchestrator import get_orchestrator

            orchestrator = get_orchestrator()
            if orchestrator.session and orchestrator.session.ssh_host:
                worker_url = f"http://{orchestrator.session.ssh_host}:11434"
                if worker_url not in urls_to_try:
                    urls_to_try.append(worker_url)
        except Exception:
            pass

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
                        "url": url,
                        "source": "local" if "localhost" in url or "127.0.0.1" in url else "gpu_worker",
                    }
            except Exception:
                continue

        return {
            "provider": "ollama",
            "connected": False,
            "error": f"Not reachable at any URL: {urls_to_try}",
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


def chat(messages: list[dict], model: str | None = None, mode: str = "creative") -> str:
    """Send a chat completion request to the configured LLM provider.

    Args:
        messages: List of {"role": "user"|"assistant"|"system", "content": "..."}
        model: Override the default model
        mode: Brain mode (creative, prompt_engineer, story_assistant, production_advisor, research, image_analyzer)

    Returns:
        The assistant's response text
    """
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


def _get_provider_chain() -> list[tuple[str, callable, str]]:
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

    # If primary URL is localhost and it might fail (Vercel), also try worker
    try:
        from backend.infrastructure.worker_orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        if orchestrator.session and orchestrator.session.ssh_host:
            # Worker Ollama is accessible via SSH tunnel on localhost:11434
            # or directly at worker_ip:11434 if exposed
            worker_url = f"http://{orchestrator.session.ssh_host}:11434"
            if worker_url not in urls_to_try:
                urls_to_try.append(worker_url)
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
            last_error = LLMProviderError(f"Ollama at {url} returned {resp.status_code}: {resp.text[:200]}")
        except httpx.ConnectError:
            last_error = LLMProviderError(f"Ollama not reachable at {url}")
        except Exception as e:
            last_error = LLMProviderError(f"Ollama error at {url}: {str(e)[:100]}")

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
