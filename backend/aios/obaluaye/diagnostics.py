"""Ise/Obaluaye Diagnostics — LLM-powered failure analysis and auto-fix.

When Ise detects a service is DOWN or DEGRADED:
1. Gather context (error message, service type, recent logs)
2. Ask the LLM to diagnose the root cause
3. LLM suggests a fix command or action
4. If auto-fixable: queue for approval or execute (depending on governance)
5. If not: present the diagnosis and suggestion to the user

Uses whatever LLM is available (Ollama preferred for speed/privacy).
Falls back to rule-based suggestions if no LLM available.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


DIAGNOSIS_PROMPT = """You are Ise, the reliability agent for AI Studio (a creative AI platform).

A service health check just failed. Analyze the error and provide:
1. ROOT CAUSE: What's most likely wrong (1 sentence)
2. FIX: The exact command or action to fix it (be specific)
3. PREVENTION: How to prevent this in the future (1 sentence)

Keep responses short and actionable. No fluff.

Service: {service}
Error: {error}
Context: {context}
"""

RULE_BASED_FIXES: dict[str, dict] = {
    "comfyui": {
        "Connection refused": {
            "diagnosis": "ComfyUI is not running on the GPU worker.",
            "fix": "SSH to worker and start ComfyUI: cd /workspace/ComfyUI && python main.py --listen 0.0.0.0 --port 8188",
            "fix_action": "start_comfyui",
            "auto_fixable": True,
        },
        "timeout": {
            "diagnosis": "ComfyUI is running but not responding (likely loading a model or out of VRAM).",
            "fix": "Wait 30 seconds and retry. If persistent, restart ComfyUI on the worker.",
            "fix_action": "restart_comfyui",
            "auto_fixable": True,
        },
    },
    "ollama": {
        "Not reachable": {
            "diagnosis": "Ollama is not running locally. The SSH tunnel to GPU worker may not be open.",
            "fix": "Run 'ollama serve' locally, or open SSH tunnel: ssh -L 11434:127.0.0.1:11434 root@worker",
            "fix_action": "start_ollama",
            "auto_fixable": True,
        },
        "model.*not found": {
            "diagnosis": "The configured model is not pulled in Ollama.",
            "fix": "Run: ollama pull llama3.1:8b",
            "fix_action": "pull_model",
            "auto_fixable": True,
        },
    },
    "worker_api": {
        "unreachable": {
            "diagnosis": "Worker HTTP API (port 7860) is not running on the GPU instance.",
            "fix": "SSH to worker and start the API: cd /workspace/ai-studio88 && python -m worker.api",
            "fix_action": "start_worker_api",
            "auto_fixable": True,
        },
        "No worker configured": {
            "diagnosis": "No GPU worker is currently active.",
            "fix": "Launch a GPU worker from Admin → Fleet, or set WORKER_API_URL in environment.",
            "fix_action": "launch_worker",
            "auto_fixable": False,
        },
    },
    "supabase": {
        "timeout": {
            "diagnosis": "Supabase is not responding. May be a network issue or the free tier is rate-limited.",
            "fix": "Check internet connection. If persistent, check Supabase dashboard for outages.",
            "fix_action": None,
            "auto_fixable": False,
        },
    },
    "elevenlabs": {
        "not set": {
            "diagnosis": "ElevenLabs API key is not configured.",
            "fix": "Add ELEVENLABS_API_KEY to your .env file. Get a key from elevenlabs.io/settings",
            "fix_action": None,
            "auto_fixable": False,
        },
    },
}


async def diagnose_failure(service: str, error: str, context: dict | None = None) -> dict:
    """Diagnose a service failure using LLM + rule-based knowledge.

    Returns:
        {
            diagnosis: str — what's wrong
            fix: str — how to fix it
            fix_action: str | None — action code (for auto-fix)
            auto_fixable: bool — can Ise fix this automatically?
            source: "llm" | "rules" — how the diagnosis was made
        }
    """
    # Try rule-based first (fast, always available)
    rule_result = _rule_based_diagnosis(service, error)

    # Try LLM enhancement (adds more context and reasoning)
    llm_result = await _llm_diagnosis(service, error, context)

    if llm_result:
        # Merge: LLM diagnosis + rule-based fix action
        return {
            "diagnosis": llm_result.get("diagnosis", rule_result["diagnosis"]),
            "fix": llm_result.get("fix", rule_result["fix"]),
            "fix_action": rule_result.get("fix_action"),
            "auto_fixable": rule_result.get("auto_fixable", False),
            "prevention": llm_result.get("prevention", ""),
            "source": "llm",
        }

    return {**rule_result, "source": "rules"}


async def attempt_auto_fix(fix_action: str, service: str) -> dict:
    """Attempt to automatically fix a service issue.

    Only executes pre-defined safe actions. Destructive actions require approval.

    Returns: {success: bool, message: str, output: str}
    """
    import os
    import subprocess

    if fix_action == "start_comfyui":
        return await _ssh_fix(
            "cd /workspace/ComfyUI && setsid python main.py --listen 0.0.0.0 --port 8188 </dev/null > /tmp/comfyui.log 2>&1 & disown && echo STARTED"
        )

    elif fix_action == "restart_comfyui":
        return await _ssh_fix(
            "pkill -f 'python main.py.*8188' 2>/dev/null; sleep 2; "
            "cd /workspace/ComfyUI && setsid python main.py --listen 0.0.0.0 --port 8188 </dev/null > /tmp/comfyui.log 2>&1 & disown && echo RESTARTED"
        )

    elif fix_action == "start_ollama":
        # Try local first
        try:
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"success": True, "message": "Ollama serve started locally", "output": ""}
        except FileNotFoundError:
            return {"success": False, "message": "Ollama not installed locally. Install from ollama.ai", "output": ""}

    elif fix_action == "pull_model":
        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        try:
            result = subprocess.run(["ollama", "pull", model], capture_output=True, text=True, timeout=300)
            return {"success": result.returncode == 0, "message": f"Pulled {model}", "output": result.stdout[:200]}
        except Exception as e:
            return {"success": False, "message": str(e), "output": ""}

    elif fix_action == "start_worker_api":
        return await _ssh_fix(
            "cd /workspace/ai-studio88 && pip install fastapi uvicorn httpx 2>/dev/null; "
            "nohup python -m worker.api > /tmp/worker_api.log 2>&1 & echo STARTED"
        )

    return {"success": False, "message": f"Unknown fix action: {fix_action}", "output": ""}


# =============================================================================
# Internal
# =============================================================================


def _rule_based_diagnosis(service: str, error: str) -> dict:
    """Fast rule-based diagnosis from known patterns."""
    service_rules = RULE_BASED_FIXES.get(service, {})
    error_lower = error.lower()

    for pattern, fix_info in service_rules.items():
        if pattern.lower() in error_lower:
            return {
                "diagnosis": fix_info["diagnosis"],
                "fix": fix_info["fix"],
                "fix_action": fix_info.get("fix_action"),
                "auto_fixable": fix_info.get("auto_fixable", False),
            }

    # Generic fallback
    return {
        "diagnosis": f"{service} is experiencing an issue: {error[:100]}",
        "fix": f"Check the {service} service logs and configuration.",
        "fix_action": None,
        "auto_fixable": False,
    }


async def _llm_diagnosis(service: str, error: str, context: dict | None = None) -> dict | None:
    """Use LLM to diagnose the failure with more detail."""
    try:
        from backend.aios.provider_router import route_request, RoutingContext

        prompt = DIAGNOSIS_PROMPT.format(
            service=service,
            error=error,
            context=str(context or {})[:300],
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Diagnose this {service} failure: {error}"},
        ]

        routing_ctx = RoutingContext(
            mode="production_advisor",
            message_length=len(error),
            session_message_count=0,
        )

        response, provider, model = route_request(messages, routing_ctx)

        # Parse structured response
        result = {"diagnosis": "", "fix": "", "prevention": ""}
        lines = response.strip().split("\n")
        for line in lines:
            line_lower = line.lower()
            if "root cause" in line_lower or "diagnosis" in line_lower:
                result["diagnosis"] = line.split(":", 1)[-1].strip() if ":" in line else line
            elif "fix" in line_lower:
                result["fix"] = line.split(":", 1)[-1].strip() if ":" in line else line
            elif "prevent" in line_lower:
                result["prevention"] = line.split(":", 1)[-1].strip() if ":" in line else line

        # If parsing failed, use the full response as diagnosis
        if not result["diagnosis"]:
            result["diagnosis"] = response[:200]

        return result

    except Exception as e:
        logger.debug(f"LLM diagnosis failed: {e}")
        return None


async def _ssh_fix(command: str) -> dict:
    """Execute a fix command on the GPU worker via SSH."""
    import os
    import subprocess

    try:
        from backend.infrastructure.worker_orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        session = orchestrator.session

        if not session or not session.ssh_host:
            return {"success": False, "message": "No active GPU worker to SSH into", "output": ""}

        ssh_key = os.path.expanduser(os.getenv("VASTAI_SSH_KEY_PATH", "~/.ssh/id_ed25519"))
        ssh_host = session.ssh_host
        ssh_port = str(session.ssh_port)

        ssh_cmd = [
            "ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=10", "-i", ssh_key, "-p", ssh_port,
            f"root@{ssh_host}", command,
        ]

        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
        output = (result.stdout + result.stderr).strip()
        success = "STARTED" in output or "RESTARTED" in output or result.returncode == 0

        return {"success": success, "message": "Command executed on worker", "output": output[:300]}

    except Exception as e:
        return {"success": False, "message": f"SSH fix failed: {str(e)[:100]}", "output": ""}
