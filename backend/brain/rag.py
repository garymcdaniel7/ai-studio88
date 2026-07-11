"""RAG (Retrieval Augmented Generation) — Long-term AI Brain memory.

Architecture:
1. When a conversation has meaningful content → chunk and embed
2. Embeddings stored in Supabase pgvector (brain_embeddings table)
3. On each new Brain message → search for relevant context
4. Inject relevant context into system prompt

Embedding model: Ollama's nomic-embed-text (768 dimensions, runs locally)
Fallback: simple keyword matching if embeddings unavailable
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")


def get_embedding(text: str) -> list[float] | None:
    """Generate an embedding vector for the given text using Ollama.

    Returns a 768-dimensional vector or None if unavailable.
    """
    try:
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": EMBEDDING_MODEL, "input": text},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
        return None
    except Exception as e:
        logger.warning(f"Embedding failed: {e}")
        return None


def chunk_conversation(messages: list[dict], max_chunk_size: int = 500) -> list[str]:
    """Split a conversation into meaningful chunks for embedding.

    Groups messages into chunks of ~500 chars, preserving context.
    """
    chunks = []
    current_chunk = ""

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if not content:
            continue

        line = f"{role}: {content}"

        if len(current_chunk) + len(line) > max_chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = line
        else:
            current_chunk += "\n" + line if current_chunk else line

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def embed_conversation(
    conversation_id: str,
    messages: list[dict],
    collection_id: str | None = None,
) -> int:
    """Embed a conversation's chunks and store in Supabase.

    Returns the number of chunks stored.
    """
    from backend.database import supabase

    chunks = chunk_conversation(messages)
    if not chunks:
        return 0

    stored = 0
    for chunk in chunks:
        embedding = get_embedding(chunk)
        if embedding is None:
            continue

        try:
            supabase.table("brain_embeddings").insert({
                "conversation_id": conversation_id,
                "collection_id": collection_id,
                "content": chunk,
                "embedding": embedding,
                "source_type": "conversation",
                "metadata": {"chunk_length": len(chunk)},
            }).execute()
            stored += 1
        except Exception as e:
            logger.warning(f"Failed to store embedding: {e}")

    return stored


def embed_text(
    text: str,
    source_type: str = "note",
    collection_id: str | None = None,
    metadata: dict | None = None,
) -> bool:
    """Embed a single piece of text (talent DNA, prompt, note).

    Returns True if stored successfully.
    """
    from backend.database import supabase

    embedding = get_embedding(text)
    if embedding is None:
        return False

    try:
        supabase.table("brain_embeddings").insert({
            "collection_id": collection_id,
            "content": text,
            "embedding": embedding,
            "source_type": source_type,
            "metadata": metadata or {},
        }).execute()
        return True
    except Exception as e:
        logger.warning(f"Failed to store text embedding: {e}")
        return False


def search_context(
    query: str,
    max_results: int = 5,
    threshold: float = 0.7,
    collection_id: str | None = None,
) -> list[dict]:
    """Search for relevant context using vector similarity.

    Returns list of {content, source_type, similarity, metadata}
    """
    from backend.database import supabase

    query_embedding = get_embedding(query)
    if query_embedding is None:
        return []

    try:
        # Use the match_brain_embeddings function
        result = supabase.rpc("match_brain_embeddings", {
            "query_embedding": query_embedding,
            "match_threshold": threshold,
            "match_count": max_results,
        }).execute()
        return result.data or []
    except Exception as e:
        logger.warning(f"Vector search failed: {e}")
        # Fallback: simple text search
        return _fallback_search(query, max_results)


def _fallback_search(query: str, max_results: int = 5) -> list[dict]:
    """Fallback search using text matching (no vectors needed)."""
    from backend.database import supabase

    try:
        # Search conversations by content
        result = supabase.table("brain_conversations").select(
            "title,summary,messages"
        ).order("updated_at", desc=True).limit(max_results).execute()

        matches = []
        query_lower = query.lower()
        for conv in (result.data or []):
            summary = conv.get("summary", "")
            title = conv.get("title", "")
            if query_lower in summary.lower() or query_lower in title.lower():
                matches.append({
                    "content": summary or title,
                    "source_type": "conversation",
                    "similarity": 0.5,
                    "metadata": {},
                })
        return matches[:max_results]
    except Exception:
        return []


def build_context_prompt(query: str, collection_id: str | None = None) -> str:
    """Build a context string to inject into the Brain's system prompt.

    Searches for relevant past conversations and returns formatted context.
    """
    results = search_context(query, max_results=3, collection_id=collection_id)

    if not results:
        return ""

    context_parts = ["[Memory — relevant context from past conversations]"]
    for r in results:
        content = r.get("content", "")[:300]
        source = r.get("source_type", "")
        similarity = r.get("similarity", 0)
        context_parts.append(f"- ({source}, relevance: {similarity:.0%}) {content}")

    return "\n".join(context_parts)
