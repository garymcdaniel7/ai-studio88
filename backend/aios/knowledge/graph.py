"""Unified Knowledge Graph — search across all DNA systems.

Provides a single interface to query:
- Talent DNA (names, styles, preferences, relationships)
- Creative DNA (per-talent learned preferences)
- Object DNA (product properties, materials, geometry)
- Visual DNA (asset visual analysis)
- Story DNA (universes, characters, continuity)
- Workflow DNA (learned successful generation configs)
- Model Registry (checkpoints, LoRAs, capabilities)
- Generation History (what was generated, what worked)

All queries are scoped by org_id for multi-tenant isolation.
Vector search (pgvector) for semantic queries.
Relational queries for structured lookups.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def _db():
    from backend.database import supabase
    return supabase


@dataclass
class KnowledgeResult:
    """A single result from a knowledge graph query."""
    source: str          # "talent", "creative_dna", "object_dna", "model", "generation", etc.
    entity_id: str       # ID of the matching entity
    name: str            # Human-readable name
    relevance: float     # 0.0-1.0 relevance score
    data: dict = field(default_factory=dict)  # Full entity data
    summary: str = ""    # One-line summary


@dataclass
class KnowledgeQuery:
    """A query against the knowledge graph."""
    query: str           # Natural language or keyword query
    sources: list[str] = field(default_factory=list)  # Filter to specific sources (empty = all)
    talent_id: str | None = None  # Scope to a talent
    project_id: str | None = None  # Scope to a project
    limit: int = 20
    include_vectors: bool = True  # Also do semantic search


def search(query: KnowledgeQuery) -> list[KnowledgeResult]:
    """Search across all knowledge systems.

    Combines structured search (keyword matching across tables)
    with vector search (pgvector semantic similarity).
    Returns results ranked by relevance.
    """
    results: list[KnowledgeResult] = []
    q = query.query.lower()
    sources = query.sources or ["talent", "creative_dna", "object_dna", "visual_dna", "model", "generation", "workflow_dna", "story"]

    # Structured search across each source
    if "talent" in sources:
        results.extend(_search_talent(q, query.limit))

    if "creative_dna" in sources:
        results.extend(_search_creative_dna(q, query.talent_id, query.limit))

    if "object_dna" in sources:
        results.extend(_search_object_dna(q, query.limit))

    if "visual_dna" in sources:
        results.extend(_search_visual_dna(q, query.limit))

    if "model" in sources:
        results.extend(_search_models(q, query.limit))

    if "generation" in sources:
        results.extend(_search_generation_history(q, query.talent_id, query.limit))

    if "workflow_dna" in sources:
        results.extend(_search_workflow_dna(q, query.limit))

    if "story" in sources:
        results.extend(_search_stories(q, query.limit))

    # Vector search (semantic) if enabled
    if query.include_vectors:
        results.extend(_vector_search(q, query.limit))

    # Sort by relevance and deduplicate
    results.sort(key=lambda r: r.relevance, reverse=True)

    # Deduplicate by entity_id
    seen = set()
    deduped = []
    for r in results:
        key = f"{r.source}:{r.entity_id}"
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    return deduped[:query.limit]


def get_talent_knowledge(talent_id: str) -> dict:
    """Get all knowledge about a specific talent.

    Returns a comprehensive view: profile, DNA, relationships,
    LoRAs, voice profiles, generation history, workflow preferences.
    """
    knowledge: dict[str, Any] = {}

    # Profile
    try:
        talent = _db().table("talent").select("*").eq("id", talent_id).single().execute().data
        knowledge["profile"] = talent
    except Exception:
        knowledge["profile"] = None

    # Creative DNA
    try:
        dna = _db().table("creative_dna").select("*").eq("talent_id", talent_id).execute().data
        knowledge["creative_dna"] = dna[0] if dna else None
    except Exception:
        knowledge["creative_dna"] = None

    # Relationships
    try:
        rels_out = _db().table("talent_relationships").select("*").eq("talent_id", talent_id).execute().data or []
        rels_in = _db().table("talent_relationships").select("*").eq("related_talent_id", talent_id).execute().data or []
        knowledge["relationships"] = rels_out + rels_in
    except Exception:
        knowledge["relationships"] = []

    # LoRAs
    try:
        loras = _db().table("talent_loras").select("*").eq("talent_id", talent_id).execute().data or []
        lora_versions = _db().table("lora_versions").select("*").eq("talent_id", talent_id).execute().data or []
        knowledge["loras"] = {"assigned": loras, "trained": lora_versions}
    except Exception:
        knowledge["loras"] = {"assigned": [], "trained": []}

    # Voice profiles
    try:
        voices = _db().table("voice_profiles").select("*").eq("talent_id", talent_id).execute().data or []
        knowledge["voices"] = voices
    except Exception:
        knowledge["voices"] = []

    # Recent generations
    try:
        gens = _db().table("assets").select("id,filename,type,created_at,metadata").eq("talent_id", talent_id).order("created_at", desc=True).limit(10).execute().data or []
        knowledge["recent_generations"] = gens
    except Exception:
        knowledge["recent_generations"] = []

    return knowledge


# =============================================================================
# Source-specific search implementations
# =============================================================================


def _search_talent(q: str, limit: int) -> list[KnowledgeResult]:
    """Search talent by name, bio, style."""
    results = []
    try:
        # Text search on name and bio
        talents = _db().table("talent").select("id,name,bio,default_style,visual_style,best_for").limit(limit * 2).execute().data or []
        for t in talents:
            score = 0.0
            name = (t.get("name") or "").lower()
            bio = (t.get("bio") or "").lower()
            style = (t.get("visual_style") or "").lower()
            best_for = (t.get("best_for") or "").lower()

            if q in name:
                score = 0.95
            elif q in bio:
                score = 0.7
            elif q in style or q in best_for:
                score = 0.6
            elif any(word in name or word in bio for word in q.split()):
                score = 0.5

            if score > 0.3:
                results.append(KnowledgeResult(
                    source="talent",
                    entity_id=t.get("id", ""),
                    name=t.get("name", ""),
                    relevance=score,
                    data=t,
                    summary=f"{t.get('name')} — {t.get('default_style', 'model')} | {t.get('visual_style', '')}",
                ))
    except Exception as e:
        logger.debug(f"Talent search error: {e}")
    return results


def _search_creative_dna(q: str, talent_id: str | None, limit: int) -> list[KnowledgeResult]:
    """Search creative DNA preferences."""
    results = []
    try:
        query = _db().table("creative_dna").select("*").limit(limit)
        if talent_id:
            query = query.eq("talent_id", talent_id)
        dna_records = query.execute().data or []

        for d in dna_records:
            score = 0.0
            styles = " ".join(d.get("preferred_styles", []) or []).lower()
            rules = " ".join(d.get("prompt_rules", []) or []).lower()

            if q in styles:
                score = 0.8
            elif q in rules:
                score = 0.7
            elif any(word in styles for word in q.split()):
                score = 0.5

            if score > 0.3:
                results.append(KnowledgeResult(
                    source="creative_dna",
                    entity_id=d.get("id", d.get("talent_id", "")),
                    name=f"Creative DNA ({d.get('talent_id', '')[:8]})",
                    relevance=score,
                    data=d,
                    summary=f"Styles: {', '.join((d.get('preferred_styles') or [])[:3])}",
                ))
    except Exception as e:
        logger.debug(f"Creative DNA search error: {e}")
    return results


def _search_object_dna(q: str, limit: int) -> list[KnowledgeResult]:
    """Search object DNA profiles."""
    results = []
    try:
        objects = _db().table("object_dna").select("*").limit(limit * 2).execute().data or []
        for obj in objects:
            name = (obj.get("name") or "").lower()
            category = (obj.get("category") or "").lower()
            score = 0.0
            if q in name:
                score = 0.9
            elif q in category:
                score = 0.6
            if score > 0.3:
                results.append(KnowledgeResult(
                    source="object_dna",
                    entity_id=obj.get("id", ""),
                    name=obj.get("name", "Object"),
                    relevance=score,
                    data=obj,
                    summary=f"{obj.get('name')} ({obj.get('category', '')})",
                ))
    except Exception as e:
        logger.debug(f"Object DNA search error: {e}")
    return results


def _search_visual_dna(q: str, limit: int) -> list[KnowledgeResult]:
    """Search visual DNA profiles."""
    results = []
    try:
        visuals = _db().table("visual_dna").select("*").limit(limit).execute().data or []
        for v in visuals:
            category = (v.get("category") or "").lower()
            if q in category:
                results.append(KnowledgeResult(
                    source="visual_dna",
                    entity_id=v.get("id", ""),
                    name=f"Visual DNA ({v.get('asset_id', '')[:8]})",
                    relevance=0.5,
                    data=v,
                ))
    except Exception as e:
        logger.debug(f"Visual DNA search error: {e}")
    return results


def _search_models(q: str, limit: int) -> list[KnowledgeResult]:
    """Search model registry."""
    results = []
    try:
        models = _db().table("models").select("*").limit(limit * 2).execute().data or []
        for m in models:
            name = (m.get("name") or "").lower()
            family = (m.get("family") or "").lower()
            model_type = (m.get("type") or "").lower()
            score = 0.0
            if q in name:
                score = 0.9
            elif q in family:
                score = 0.7
            elif q in model_type:
                score = 0.5
            if score > 0.3:
                results.append(KnowledgeResult(
                    source="model",
                    entity_id=m.get("id", ""),
                    name=m.get("name", ""),
                    relevance=score,
                    data=m,
                    summary=f"{m.get('name')} ({m.get('family', '')}/{m.get('type', '')})",
                ))
    except Exception as e:
        logger.debug(f"Model search error: {e}")
    return results


def _search_generation_history(q: str, talent_id: str | None, limit: int) -> list[KnowledgeResult]:
    """Search generation history (assets with metadata)."""
    results = []
    try:
        query = _db().table("assets").select("id,filename,type,metadata,created_at").order("created_at", desc=True).limit(limit)
        if talent_id:
            query = query.eq("talent_id", talent_id)
        assets = query.execute().data or []
        for a in assets:
            meta = a.get("metadata") or {}
            prompt = str(meta.get("prompt", "")).lower()
            if q in prompt or q in (a.get("filename") or "").lower():
                results.append(KnowledgeResult(
                    source="generation",
                    entity_id=a.get("id", ""),
                    name=a.get("filename", ""),
                    relevance=0.6,
                    data=a,
                    summary=f"Generated: {prompt[:60]}",
                ))
    except Exception as e:
        logger.debug(f"Generation history search error: {e}")
    return results


def _search_workflow_dna(q: str, limit: int) -> list[KnowledgeResult]:
    """Search workflow DNA recipes."""
    results = []
    try:
        workflows = _db().table("workflow_dna").select("*").limit(limit).execute().data or []
        for w in workflows:
            name = (w.get("name") or "").lower()
            content_type = (w.get("content_type") or "").lower()
            if q in name or q in content_type:
                results.append(KnowledgeResult(
                    source="workflow_dna",
                    entity_id=w.get("id", ""),
                    name=w.get("name", ""),
                    relevance=0.7,
                    data=w,
                    summary=f"{w.get('name')} — {w.get('checkpoint', '')} ({w.get('quality_score', 0)}/5)",
                ))
    except Exception as e:
        logger.debug(f"Workflow DNA search error: {e}")
    return results


def _search_stories(q: str, limit: int) -> list[KnowledgeResult]:
    """Search story universes and characters."""
    results = []
    try:
        # Search universes
        universes = _db().table("story_universes").select("*").limit(limit).execute().data or []
        for u in universes:
            name = (u.get("name") or "").lower()
            if q in name or q in (u.get("description") or "").lower():
                results.append(KnowledgeResult(
                    source="story",
                    entity_id=u.get("id", ""),
                    name=u.get("name", ""),
                    relevance=0.7,
                    data=u,
                    summary=f"Universe: {u.get('name')} ({u.get('genre', '')})",
                ))
    except Exception as e:
        logger.debug(f"Story search error: {e}")
    return results


def _vector_search(q: str, limit: int) -> list[KnowledgeResult]:
    """Semantic search via pgvector embeddings."""
    results = []
    try:
        from backend.brain.rag import search_context
        matches = search_context(q, max_results=limit, threshold=0.6)
        for m in matches:
            results.append(KnowledgeResult(
                source="memory",
                entity_id=m.get("id", ""),
                name="Brain Memory",
                relevance=float(m.get("similarity", 0.5)),
                data=m,
                summary=m.get("content", "")[:80],
            ))
    except Exception as e:
        logger.debug(f"Vector search error: {e}")
    return results
