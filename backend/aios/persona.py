"""AIOS persona loading and policy-safe prompt injection."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

SOUL_PATH = Path(__file__).with_name("AIOS_SOUL.md")
USER_PATH = Path(__file__).with_name("AIOS_USER.md")
POLICY_MARKER = "[AIOS GOVERNANCE — ALWAYS OVERRIDES PERSONA]"


@lru_cache(maxsize=1)
def load_soul() -> str:
    """Load the versioned AIOS line-producer operating doctrine."""
    return SOUL_PATH.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def load_user_soul() -> str:
    """Load the working model of the principal (who AIOS serves)."""
    try:
        return USER_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def inject_persona(system_prompt: str, governance_policy: str = "") -> str:
    """Compose a system prompt with persona context below the policy boundary.

    The explicit ordering and marker make the precedence contract inspectable:
    governance is presented as binding after the persona and is never replaced
    by persona language.
    """
    if not system_prompt.strip():
        raise ValueError("system_prompt is required")

    policy = governance_policy.strip() or (
        "Follow all applicable safety, authorization, legal, tenant-isolation, "
        "and cost policies. Do not execute a blocked or unapproved action."
    )
    user_soul = load_user_soul()
    user_block = (
        f"\n[AIOS USER — working model of the principal]\n{user_soul}\n"
        if user_soul
        else ""
    )
    return (
        f"{system_prompt.strip()}\n\n"
        "[AIOS SOUL — communication style only]\n"
        f"{load_soul()}\n"
        f"{user_block}"
        f"\n{POLICY_MARKER}\n{policy}"
    )


def render_memory_context(entries: list[dict]) -> str:
    """Render already-authorized tenant memory for prompt injection."""
    if not entries:
        return ""
    lines = ["[AIOS TENANT MEMORY — authorized workspace context]"]
    for entry in entries:
        lines.append(f"- {entry.get('key', 'memory')}: {entry.get('value', {})}")
    return "\n".join(lines)
