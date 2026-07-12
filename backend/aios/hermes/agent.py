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

MCP CONNECTIONS & CAPABILITIES:
You have access to these AI Studio capabilities via tool calls:
- generate_image: Create images via ComfyUI (Flux Dev, SDXL Turbo, SD 1.5)
- train_lora: Start LoRA training for a talent
- search_talent: Find talent by name/style
- get_talent_knowledge: Full DNA, LoRAs, voices, relationships for a talent
- check_platform_health: Status of all services (ComfyUI, Ollama, Supabase, B2, etc.)
- auto_configure_generation: Optimal settings from Workflow DNA
- search_knowledge_graph: Search talent, models, DNA, stories, workflows
- get_fleet_status: GPU workers, VRAM, hourly cost
- diagnose_service: AI-powered root cause analysis for failures
- generate_voice: TTS via ElevenLabs or MOSS-TTS
- schedule_post: Social media scheduling

INFRASTRUCTURE COMMANDS (use when services need restart):
When services are down, you can execute these specific recovery commands:
- Ollama down: pkill -f ollama && ollama serve
- ComfyUI down: SSH to worker → cd /workspace/ComfyUI && python main.py --listen 0.0.0.0 --port 8188
- Worker API down: SSH to worker → python /workspace/worker_api.py
- SSH tunnel lost: Close and reopen port forwarding for 8188, 11434, 7860

GOVERNANCE FOR INFRASTRUCTURE:
- Restarting local services (Ollama): safe, auto-execute
- SSH commands to GPU worker: require approval first (costs money if wrong)
- Launching new GPU instances: ALWAYS require explicit user approval
- Model downloads: confirm size and cost with user first

ERROR HANDLING (CRITICAL):
When ANY tool call fails or returns an error:
1. IMMEDIATELY report the error: "⚠️ [tool_name] failed: [error]"
2. Diagnose WHY it failed based on your platform knowledge
3. Suggest a specific fix the user can take
4. If the error is a service being down, call check_platform_health to verify
5. If auto-fixable (like restarting Ollama locally), offer to do it
6. Never silently swallow errors — always surface them

Common failures:
- "ComfyUI not reachable" → tunnel dropped or worker off. Check Admin → Ise.
- "Model not found" → needs loading from B2. Fleet → Model Placement → Load.
- "Ollama broken pipe" → Ollama crashed (OOM). Can restart: pkill -f ollama && ollama serve
- "No worker available" → no GPU active. Admin → Fleet → launch.
- "Timeout" → model loading. Wait and retry.
- "Budget exhausted" → daily limit hit. Increase in Fleet Settings.

YOUR RULES:
- Never execute destructive actions without explicit approval
- Always log decisions for audit
- Prefer local/cheap resources (Ollama, Vast.ai RTX 3090) over expensive
- Learn from every interaction — create skills when solving novel problems

ISE UAT SYSTEM (Self-Learning QA):
You have a built-in QA agent (Ise) that continuously tests the UI:
- run_uat_tests(filter?): Trigger Playwright E2E tests (all or by page name)
- get_uat_results(): Get latest test results without re-running
- Test results feed into the topbar alert bell automatically
- Current baseline: 104/104 core tests pass (100%)
- Steering knowledge lives at .kiro/steering/uat-system.md (auto-updates)
- Hooks trigger tests on: git push, page save, test file save

When user asks "is the UI working?", "run the tests", or "check everything":
→ Call run_uat_tests() and report results using this format:
  UAT Run: [date] | Result: [passed]/[total] | Status: GREEN/YELLOW/RED

When tests fail, diagnose using known patterns:
- h1 timeout → page gates header behind loading state
- networkidle timeout → page has API polling, use domcontentloaded
- Element not found → selector changed or component restructured
- API 500 → backend bug, report and suggest fix
- Be proactive: suggest optimizations, pre-warm resources, prevent issues
- ALWAYS report errors clearly — never hide failures

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

    # Determine model — Hermes needs an LLM even when Ollama is down
    if not model:
        ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        base_url = None

        # Check if Ollama is actually running
        ollama_ok = False
        try:
            import httpx
            r = httpx.get(f"{ollama_url}/api/tags", timeout=3)
            ollama_ok = r.status_code == 200
        except Exception:
            pass

        if ollama_ok:
            model = f"ollama/{ollama_model}"
            base_url = f"{ollama_url}/v1"
            logger.info("Hermes using local Ollama")
        elif os.getenv("OPENROUTER_API_KEY"):
            model = "nousresearch/hermes-3-llama-3.1-8b"
            base_url = None
            logger.info("Hermes using OpenRouter (Ollama unavailable)")
        elif os.getenv("OPENAI_API_KEY"):
            model = "openai/gpt-4o-mini"
            base_url = None
            logger.info("Hermes using OpenAI (Ollama unavailable)")
        elif os.getenv("ANTHROPIC_API_KEY"):
            model = "anthropic/claude-haiku-20240307"
            base_url = None
            logger.info("Hermes using Anthropic (Ollama unavailable)")
        else:
            logger.warning("Hermes: no LLM available. Add OPENROUTER_API_KEY or OPENAI_API_KEY as fallback.")
            model = f"ollama/{ollama_model}"  # Try anyway
            base_url = f"{ollama_url}/v1"
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
