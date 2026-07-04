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
from typing import AsyncGenerator, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BRAIN_PROVIDER = os.getenv("BRAIN_PROVIDER", "ollama")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
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
    """Check if the configured Brain LLM provider is accessible."""
    if BRAIN_PROVIDER == "ollama":
        try:
            resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                return {
                    "provider": "ollama",
                    "connected": True,
                    "model": OLLAMA_MODEL,
                    "available_models": model_names[:5],
                    "url": OLLAMA_BASE_URL,
                }
            return {"provider": "ollama", "connected": False, "error": f"HTTP {resp.status_code}"}
        except httpx.ConnectError:
            return {"provider": "ollama", "connected": False, "error": f"Not reachable at {OLLAMA_BASE_URL}"}
        except Exception as e:
            return {"provider": "ollama", "connected": False, "error": str(e)[:100]}

    elif BRAIN_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            return {"provider": "openai", "connected": False, "error": "OPENAI_API_KEY not set"}
        return {"provider": "openai", "connected": True, "model": OPENAI_MODEL}

    elif BRAIN_PROVIDER == "anthropic":
        if not ANTHROPIC_API_KEY:
            return {"provider": "anthropic", "connected": False, "error": "ANTHROPIC_API_KEY not set"}
        return {"provider": "anthropic", "connected": True, "model": ANTHROPIC_MODEL}

    return {"provider": BRAIN_PROVIDER, "connected": False, "error": "Unknown provider"}


def chat(messages: list[dict], model: Optional[str] = None, mode: str = "creative") -> str:
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

    if BRAIN_PROVIDER == "ollama":
        return _chat_ollama(messages, model or OLLAMA_MODEL)
    elif BRAIN_PROVIDER == "openai":
        return _chat_openai(messages, model or OPENAI_MODEL)
    elif BRAIN_PROVIDER == "anthropic":
        return _chat_anthropic(messages, model or ANTHROPIC_MODEL)
    else:
        raise LLMProviderError(f"Unknown provider: {BRAIN_PROVIDER}")


def _chat_ollama(messages: list[dict], model: str) -> str:
    """Chat via Ollama API."""
    try:
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
            timeout=120,
        )
        if resp.status_code == 200:
            return resp.json().get("message", {}).get("content", "")
        raise LLMProviderError(f"Ollama returned {resp.status_code}: {resp.text[:200]}")
    except httpx.ConnectError:
        raise LLMProviderError(f"Ollama not reachable at {OLLAMA_BASE_URL}. Is it running?")


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
