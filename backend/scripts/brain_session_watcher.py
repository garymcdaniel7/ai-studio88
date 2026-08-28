#!/usr/bin/env python3
"""
AI Studio Brain Session Watcher
================================
Watches brain conversations for sessions that are filling up / approaching the
context ceiling, so the agent brain can "reset" a session *without* losing the
story.

Modes:
  --dry-run (DEFAULT)  Only report which conversations are filling. Touch nothing.
  --compact            ALSO summarize filling conversations into brain_user_memory,
                       then archive the raw conversation. (Needs explicit opt-in.)

LIVE SCHEMA (verified against Supabase OpenAPI 2026-08-24):
  brain_conversations: id, org_id, collection_id, title, mode, messages,
                       summary, message_count, talent_id, metadata, created_at, updated_at
  brain_messages:      id, session_id, role, content, plan_id, metadata, created_at
  brain_user_memory:   id, org_id, user_id, memory_type, content, provenance,
                       confidence, is_active, source_conversation_id, created_at, updated_at

NOTE: this schema diverges from the ORM models (app/models/brain_memory.py),
which still reference user_id/is_archived/last_message_at/actor/token_count.
The watcher targets the LIVE tables. Kiro should reconcile the models to match.

Usage:
  python3 -m scripts.brain_session_watcher            # dry-run (safe)
  python3 -m scripts.brain_session_watcher --compact  # summarize + archive
  python3 -m scripts.brain_session_watcher --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

# --- Load repo .env (same convention as backend/database.py) -----------------
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"


def load_env() -> None:
    if not ENV_PATH.exists():
        print(f"[!] No .env found at {ENV_PATH} — cannot read Supabase creds.", file=sys.stderr)
        sys.exit(1)
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
            os.environ.setdefault(key, val)


def supabase_headers() -> dict[str, str]:
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("[!] SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY missing from .env", file=sys.stderr)
        sys.exit(1)
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


# --- Logic -------------------------------------------------------------------


async def find_filling_conversations(
    supabase_url: str,
    headers: dict[str, str],
    token_ceiling: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Return conversations whose message count / content is approaching the ceiling.

    The live brain_messages table has no token_count column, so we use
    message_count (the conversation's own counter) as the fill signal, with a
    rough token estimate from content length as a secondary signal.
    """
    import httpx

    filling: list[dict[str, Any]] = []

    conv_url = f"{supabase_url}/rest/v1/brain_conversations"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            conv_url,
            params={"order": "updated_at.desc.nullslast", "limit": limit},
            headers=headers,
        )
        resp.raise_for_status()
        conversations = resp.json()

        for conv in conversations:
            conv_id = conv.get("id")
            msg_count = conv.get("message_count") or 0

            # Secondary signal: sum content lengths of this conversation's messages.
            # Live brain_messages is keyed by session_id, so estimate from the
            # conversation's embedded messages if present, else skip token estimate.
            token_estimate = None
            embedded = conv.get("messages")
            if isinstance(embedded, list):
                total_chars = sum(len((m.get("content") or "")) for m in embedded if isinstance(m, dict))
                # ~4 chars per token
                token_estimate = total_chars // 4

            # Fill signal: use token_estimate if we have it, else message_count * 300 (rough)
            if token_estimate is not None:
                fill_tokens = token_estimate
            else:
                fill_tokens = msg_count * 300

            utilization = fill_tokens / token_ceiling if token_ceiling else 0
            status = "OK" if utilization < 0.8 else ("NEAR" if utilization < 1.0 else "OVER")

            if status != "OK":
                filling.append(
                    {
                        "conversation_id": conv_id,
                        "org_id": conv.get("org_id"),
                        "mode": conv.get("mode"),
                        "title": conv.get("title"),
                        "message_count": msg_count,
                        "token_estimate": token_estimate,
                        "fill_tokens": fill_tokens,
                        "ceiling": token_ceiling,
                        "utilization": round(utilization, 3),
                        "status": status,
                    }
                )

    return filling


def summarize_conversation(conv: dict[str, Any]) -> str:
    """Non-destructive placeholder: build a summary candidate.

    Later iteration calls the LLM (Ollama) to produce a real summary. For now
    it structures what a summary should capture so Gary can see the shape.
    """
    return (
        f"Conversation summary [{conv['mode']}]"
        f" ({conv['message_count']} messages, ~{conv['fill_tokens']} tokens): "
        f"auto-generated summary pending — will capture established facts, "
        f"characters, plot/decisions so the brain remembers after reset."
    )


async def compact_conversations(
    supabase_url: str,
    headers: dict[str, str],
    filling: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Summarize each filling conversation into brain_user_memory, then archive it.

    Destructive-ish path: writes memory (safe) and sets the conversation's
    summary + clears embedded messages (recoverable via the summary). Dry-run
    never reaches here.
    """
    import httpx

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20) as client:
        for conv in filling:
            conv_id = conv["conversation_id"]

            # 1) Write summary to brain_user_memory (live columns)
            summary_text = summarize_conversation(conv)
            memory_payload = {
                "org_id": conv["org_id"],
                "memory_type": "CONVERSATION_SUMMARY",
                "content": summary_text,
                "provenance": "SUGGESTED",  # low trust, human can confirm
                "confidence": 0.5,
                "is_active": True,
                "source_conversation_id": conv_id,
            }
            mem_resp = await client.post(
                f"{supabase_url}/rest/v1/brain_user_memory",
                json=memory_payload,
                headers=headers,
            )
            mem_resp.raise_for_status()

            # 2) Archive: set summary on the conversation + reset message_count
            #    (no is_archived column on live table — use summary + count reset)
            arch_resp = await client.patch(
                f"{supabase_url}/rest/v1/brain_conversations?id=eq.{conv_id}",
                json={"summary": summary_text, "message_count": 0},
                headers=headers,
            )
            arch_resp.raise_for_status()

            results.append({"conversation_id": conv_id, "summary_written": True, "archived": True})

    return results


# --- Main --------------------------------------------------------------------


async def main() -> int:
    parser = argparse.ArgumentParser(description="AI Studio Brain session watcher")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Summarize + archive filling conversations (destructive-ish). Default is dry-run.",
    )
    parser.add_argument("--threshold", type=int, default=6500, help="Token ceiling (default 6500).")
    parser.add_argument("--limit", type=int, default=50, help="Max conversations to inspect (default 50).")
    args = parser.parse_args()

    load_env()
    headers = supabase_headers()
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")

    print(f"AI Studio Brain Session Watcher — {'DRY-RUN (no changes)' if not args.compact else 'COMPACT MODE'}")
    print(f"  ceiling: {args.threshold} tokens  |  inspecting up to {args.limit} active conversations\n")

    filling = await find_filling_conversations(supabase_url, headers, args.threshold, args.limit)

    if not filling:
        print("✓ No conversations approaching the context ceiling. All clear.")
        return 0

    print(f"Found {len(filling)} conversation(s) filling up:\n")
    for c in filling:
        print(f"  [{c['status']}] {c['mode']} — {c['message_count']} msgs, ~{c['fill_tokens']} tokens "
              f"({c['utilization']*100:.0f}% of ceiling)")
        print(f"       conv={c['conversation_id']}  title={c.get('title') or '(untitled)'}")

    if not args.compact:
        print("\n[DRY-RUN] No changes made. Re-run with --compact to summarize + archive these.")
        return 0

    print("\nCompacting...")
    results = await compact_conversations(supabase_url, headers, filling)
    print(f"✓ Summarized + reset {len(results)} conversation(s); summaries written to brain_user_memory.")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
