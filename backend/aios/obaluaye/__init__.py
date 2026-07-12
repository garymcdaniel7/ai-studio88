"""Obaluaye — Platform Reliability Supervisor.

Continuously monitors all services and infrastructure:
- Provider health (ComfyUI, Ollama, B2, Supabase, ElevenLabs)
- GPU worker health (SSH, VRAM, disk, temperature)
- Job queue health (stuck jobs, failed retries)
- Cost alerting (approaching budget limits)
- Auto-recovery (restart services, retry failed operations)

Obaluaye runs as a background process. It does NOT need an LLM to function.
It uses rule-based logic for health checks and retry decisions.
Optionally uses Ollama for pattern analysis when available.
"""
