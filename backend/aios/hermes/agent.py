"""Hermes Agent wrapper for AI Studio.

Creates a configured Hermes AIAgent instance with:
- AI Studio-specific system prompt (knows about our platform)
- Custom tools disabled (terminal restricted for safety)
- Ollama as default provider (local, free)
- Memory enabled (learns over time)
- Quiet mode (no CLI output)

The Hermes agent is used for:
1. Complex tasks requiring multi-step tool use
2. Proactive orchestration (background skill execution)
3. Self-improving workflows (Hermes creates skills automatically)
4. Deep analysis (code review, UAT, research)
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# AI Studio system prompt for Hermes
AIOS_HERMES_PROMPT = """You are the AI Studio Intelligence Agent (powered by Hermes).

You are embedded inside AI Studio — a creative AI content production platform.
Your role is proactive orchestration and self-improvement.

PLATFORM CONTEXT:
- AI Studio generates images (ComfyUI: Flux Dev, SDXL), videos (WAN 2.1), voice (MOSS-TTS, ElevenLabs)
- LoRA training for custom AI talent (identity models)
- Multi-GPU fleet management (Vast.ai, RunPod)
- Social publishing (Instagram, TikTok, YouTube)
- Knowledge graph connecting talent DNA, workflows, models, assets

YOUR CAPABILITIES:
- Execute multi-step generation pipelines
- Learn from successful operations (create reusable skills)
- Remember user preferences across sessions
- Analyze code and suggest improvements
- Monitor platform health and fix issues
- Research new models, techniques, and best practices

ERROR HANDLING (CRITICAL):
When ANY tool call fails or returns an error:
1. IMMEDIATELY report the error to the user clearly: "⚠️ [tool_name] failed: [error]"
2. Diagnose WHY it failed based on your platform knowledge
3. Suggest a specific fix the user can take
4. If the error is a service being down, call check_platform_health to verify
5. If auto-fixable, offer to call diagnose_service to attempt repair
6. Never silently swallow errors — always surface them

Common failures and what to tell the user:
- "ComfyUI not reachable" → GPU worker may be off or tunnel dropped. Suggest checking Admin → Ise.
- "Model not found" → model needs to be loaded from B2. Suggest Fleet → Model Placement → Load.
- "Ollama broken pipe" → Ollama crashed (memory). Suggest: restart with 'ollama serve'.
- "No worker available" → no GPU active. Suggest: Admin → Fleet → launch or check Vast.ai.
- "Timeout" → generation taking too long. May be model loading. Wait and retry.
- "Budget exhausted" → daily spend limit hit. Suggest increasing in Fleet Settings.

Always tell the user:
- What went wrong (specific error)
- Why it likely happened (root cause)
- How to fix it (actionable step)
- Whether you can fix it automatically

YOUR RULES:
- Never execute destructive actions without explicit approval
- Always log decisions for audit
- Prefer local/cheap resources (Ollama, Vast.ai) over expensive ones
- Learn from every interaction — create skills when you solve novel problems
- Be proactive: suggest optimizations, pre-warm resources, prevent issues
- ALWAYS report errors clearly — never hide failures from the user

AVAILABLE INFORMATION:
- Backend API at http://localhost:8000
- AIOS Gateway at http://localhost:8000/aios/v1/
- Worker API at http://localhost:7860 (when GPU active)
- Supabase for persistent data
- Backblaze B2 for model/asset storage
"""


def get_hermes_agent(
    model: str | None = None,
    skip_memory: bool = False,
    enabled_toolsets: list[str] | None = None,
    disabled_toolsets: list[str] | None = None,
    system_prompt: str | None = None,
    include_aistudio_tools: bool = True,
):
    """Create a configured Hermes AIAgent for AI Studio.

    Args:
        model: LLM model (default: uses OLLAMA_MODEL or OpenRouter)
        skip_memory: If True, don't load/save persistent memory
        enabled_toolsets: Whitelist specific tools
        disabled_toolsets: Blacklist specific tools
        system_prompt: Custom system prompt (overrides default)
        include_aistudio_tools: Include AI Studio tools (generation, training, etc.)

    Returns:
        AIAgent instance ready to use
    """
    try:
        from run_agent import AIAgent
    except ImportError:
        logger.error("hermes-agent not installed. Run: uv pip install hermes-agent")
        return None

    # Determine model
    if not model:
        # Try Ollama first (local, free)
        ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = f"ollama/{ollama_model}"
        base_url = f"{ollama_url}/v1"

        # If Ollama not available, try OpenRouter/OpenAI
        if os.getenv("OPENROUTER_API_KEY"):
            model = "nousresearch/hermes-3-llama-3.1-8b"
            base_url = None  # Use default OpenRouter
        elif os.getenv("OPENAI_API_KEY"):
            model = "gpt-4o"
            base_url = None
    else:
        base_url = None

    # Safety: disable terminal by default (prevents uncontrolled system access)
    if disabled_toolsets is None:
        disabled_toolsets = ["terminal"]  # Restrict by default

    try:
        agent = AIAgent(
            model=model,
            quiet_mode=True,
            skip_memory=skip_memory,
            skip_context_files=True,
            ephemeral_system_prompt=system_prompt or AIOS_HERMES_PROMPT,
            disabled_toolsets=disabled_toolsets,
            enabled_toolsets=enabled_toolsets,
            max_iterations=30,  # Limit to prevent runaway
            base_url=base_url,
        )
        return agent
    except Exception as e:
        logger.error(f"Failed to create Hermes agent: {e}")
        return None


def hermes_chat(message: str, model: str | None = None, skip_memory: bool = False) -> str:
    """Quick one-shot chat with Hermes.

    Creates an agent, sends a message, returns the response.
    Memory is preserved by default (Hermes learns from each interaction).
    """
    agent = get_hermes_agent(model=model, skip_memory=skip_memory)
    if not agent:
        return "Hermes agent not available. Ensure hermes-agent is installed."

    try:
        response = agent.chat(message)
        return response
    except Exception as e:
        logger.error(f"Hermes chat failed: {e}")
        return f"Hermes error: {str(e)[:200]}"


def hermes_task(
    message: str,
    system_prompt: str | None = None,
    model: str | None = None,
    enabled_toolsets: list[str] | None = None,
) -> dict:
    """Run a complex task through Hermes with full tool access.

    Returns the full conversation result (response + message history).
    """
    agent = get_hermes_agent(
        model=model,
        system_prompt=system_prompt,
        enabled_toolsets=enabled_toolsets,
        disabled_toolsets=None if enabled_toolsets else ["terminal"],
    )
    if not agent:
        return {"error": "Hermes agent not available"}

    try:
        result = agent.run_conversation(user_message=message)
        return {
            "response": result.get("final_response", ""),
            "messages": len(result.get("messages", [])),
            "success": True,
        }
    except Exception as e:
        return {"error": str(e)[:300], "success": False}
