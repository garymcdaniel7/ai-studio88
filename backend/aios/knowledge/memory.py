"""Enhanced Memory Retrieval Pipeline — multi-source context injection.

Pulls relevant context from ALL memory domains before each LLM call:
1. Session context (last N messages in this conversation)
2. Talent DNA (if talent context active)
3. Project DNA (if project context active)
4. RAG: vector search for relevant past conversations
5. Workflow DNA: successful configs for similar requests
6. Relationships: linked talents/objects for multi-entity context

The assembled context is injected into the system prompt,
giving the LLM maximum relevant information for its response.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _db():
    from backend.database import supabase
    return supabase


def retrieve_context(
    query: str,
    talent_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
    mode: str = "creative",
    max_context_chars: int = 4000,
) -> str:
    """Retrieve and assemble all relevant context for a request.

    Returns a formatted context string to inject into the system prompt.
    Stays within max_context_chars to avoid blowing context window.
    """
    sections: list[str] = []
    chars_used = 0

    # 1. Talent DNA
    if talent_id:
        talent_ctx = _get_talent_context(talent_id)
        if talent_ctx and chars_used + len(talent_ctx) < max_context_chars:
            sections.append(talent_ctx)
            chars_used += len(talent_ctx)

    # 2. Talent Relationships (linked entities)
    if talent_id:
        rel_ctx = _get_relationship_context(talent_id)
        if rel_ctx and chars_used + len(rel_ctx) < max_context_chars:
            sections.append(rel_ctx)
            chars_used += len(rel_ctx)

    # 3. Workflow DNA (recommended configs for similar requests)
    workflow_ctx = _get_workflow_context(query, talent_id)
    if workflow_ctx and chars_used + len(workflow_ctx) < max_context_chars:
        sections.append(workflow_ctx)
        chars_used += len(workflow_ctx)

    # 4. RAG: semantic search for relevant past conversations
    rag_ctx = _get_rag_context(query)
    if rag_ctx and chars_used + len(rag_ctx) < max_context_chars:
        sections.append(rag_ctx)
        chars_used += len(rag_ctx)

    # 5. Project context
    if project_id:
        project_ctx = _get_project_context(project_id)
        if project_ctx and chars_used + len(project_ctx) < max_context_chars:
            sections.append(project_ctx)
            chars_used += len(project_ctx)

    if not sections:
        return ""

    return "\n\n".join(sections)


def _get_talent_context(talent_id: str) -> str | None:
    """Load talent profile + creative DNA as context."""
    try:
        talent = _db().table("talent").select(
            "name,bio,default_style,visual_style,best_for,persona,trigger_words,negative_prompt"
        ).eq("id", talent_id).single().execute().data

        if not talent:
            return None

        lines = [f"[Active Talent: {talent.get('name', 'Unknown')}]"]
        if talent.get("bio"):
            lines.append(f"Bio: {talent['bio'][:150]}")
        if talent.get("visual_style"):
            lines.append(f"Visual Style: {talent['visual_style']}")
        if talent.get("best_for"):
            lines.append(f"Best For: {talent['best_for']}")
        if talent.get("persona"):
            lines.append(f"Persona: {talent['persona']}")
        if talent.get("trigger_words"):
            lines.append(f"LoRA Trigger: {talent['trigger_words']}")
        if talent.get("negative_prompt"):
            lines.append(f"Avoid: {talent['negative_prompt']}")

        # Creative DNA preferences
        try:
            dna = _db().table("creative_dna").select("preferred_styles,avoided_styles,prompt_rules,negative_prompt_rules").eq("talent_id", talent_id).execute().data
            if dna:
                d = dna[0]
                if d.get("preferred_styles"):
                    lines.append(f"Preferred Styles: {', '.join(d['preferred_styles'][:5])}")
                if d.get("avoided_styles"):
                    lines.append(f"Avoided Styles: {', '.join(d['avoided_styles'][:5])}")
        except Exception:
            pass

        return "\n".join(lines)
    except Exception:
        return None


def _get_relationship_context(talent_id: str) -> str | None:
    """Load talent relationships for multi-entity generation context."""
    try:
        rels = _db().table("talent_relationships").select("related_talent_id,relationship_type,notes").eq("talent_id", talent_id).limit(5).execute().data or []

        if not rels:
            return None

        lines = ["[Talent Relationships]"]
        for r in rels:
            # Get related talent name
            try:
                related = _db().table("talent").select("name,default_style").eq("id", r["related_talent_id"]).single().execute().data
                if related:
                    lines.append(f"- {r.get('relationship_type', 'associated')}: {related['name']} ({related.get('default_style', '')})")
            except Exception:
                pass

        return "\n".join(lines) if len(lines) > 1 else None
    except Exception:
        return None


def _get_workflow_context(query: str, talent_id: str | None) -> str | None:
    """Get recommended workflow config from Workflow DNA."""
    try:
        from backend.aios.knowledge.workflow_dna import recommend_workflow

        # Infer content type from query
        q = query.lower()
        content_type = "image"
        if any(w in q for w in ["video", "clip", "animate"]):
            content_type = "video"
        elif any(w in q for w in ["voice", "speak", "narrate"]):
            content_type = "voice"

        recommendations = recommend_workflow(
            content_type=content_type,
            talent_id=talent_id,
            limit=1,
        )

        if not recommendations:
            return None

        rec = recommendations[0]
        lines = [f"[Recommended Workflow: {rec.get('name', '')}]"]
        lines.append(f"Model: {rec.get('checkpoint', '')}")
        lines.append(f"Quality Score: {rec.get('quality_score', 0)}/5")
        if rec.get("loras"):
            lines.append(f"LoRAs: {len(rec['loras'])} configured")
        lines.append(f"Settings: {rec.get('steps', 20)} steps, CFG {rec.get('cfg', 7.0)}")

        return "\n".join(lines)
    except Exception:
        return None


def _get_rag_context(query: str) -> str | None:
    """Retrieve relevant past conversations via vector search."""
    try:
        from backend.brain.rag import build_context_prompt

        ctx = build_context_prompt(query)
        return ctx if ctx else None
    except Exception:
        return None


def _get_project_context(project_id: str) -> str | None:
    """Load project details for context."""
    try:
        project = _db().table("projects").select("name,description,brand_guidelines").eq("id", project_id).single().execute().data
        if not project:
            return None

        lines = [f"[Active Project: {project.get('name', '')}]"]
        if project.get("description"):
            lines.append(f"Description: {project['description'][:200]}")
        if project.get("brand_guidelines"):
            lines.append(f"Brand: {str(project['brand_guidelines'])[:200]}")

        return "\n".join(lines)
    except Exception:
        return None
