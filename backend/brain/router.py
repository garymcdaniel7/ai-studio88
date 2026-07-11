"""AI Brain API Router — the primary conversational interface.

One endpoint to rule them all: POST /brain/chat
The Brain understands, plans, delegates, and responds.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.brain.memory import (
    add_message,
    create_session,
    get_conversation_history,
    get_production_memory,
    get_session,
    list_sessions,
    update_production_memory,
)
from backend.brain.planner import ExecutionPlan, create_plan
from backend.brain.registry import list_modules

router = APIRouter(prefix="/api/v1/brain", tags=["brain"])


# =============================================================================
# Chat — the primary interface
# =============================================================================


@router.post("/chat")
def brain_chat(data: dict):
    """Talk to the AI Brain.

    The primary interface to AI Studio. Send natural language and receive
    a production plan with reasoning.

    Body: {"message": "Create Melissa in Dubai", "session_id": "optional"}
    """
    message = data.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="'message' required")

    session_id = data.get("session_id")
    if not session_id:
        session = create_session()
        session_id = session.id

    # Record user message
    add_message(session_id, "user", message)

    # Build context from conversation history
    history = get_conversation_history(session_id, limit=10)
    memory = get_production_memory()
    context = {
        "history": history,
        "memory": memory,
        "talent_preference": data.get("talent_id"),
        "project_preference": data.get("project_id"),
    }

    # Create execution plan
    plan = create_plan(message, context)

    # Generate brain response
    response = _build_response(plan, message)

    # Record brain response
    add_message(session_id, "brain", response["summary"], plan_id=plan.id)

    return {
        "session_id": session_id,
        "response": response["summary"],
        "plan": {
            "id": plan.id,
            "tasks": [
                {
                    "id": t.id,
                    "name": t.name,
                    "module": t.module,
                    "action": t.action,
                    "depends_on": t.depends_on,
                    "estimated_seconds": t.estimated_seconds,
                }
                for t in plan.tasks
            ],
            "reasoning": plan.reasoning,
            "estimated_seconds": plan.estimated_total_seconds,
            "estimated_cost": plan.estimated_cost,
            "confidence": plan.confidence,
            "modules_involved": plan.modules_involved,
        },
        "recommendations": _build_recommendations(plan),
    }


def _build_response(plan: ExecutionPlan, request: str) -> dict:
    """Build a natural language response from the plan."""
    task_names = [t.name for t in plan.tasks]
    modules = plan.modules_involved

    summary = (
        f"I'll handle this with {len(plan.tasks)} steps across {len(modules)} modules "
        f"({', '.join(modules)}). "
        f"Estimated time: ~{plan.estimated_total_seconds}s. "
        f"Plan: {' → '.join(task_names[:5])}."
    )

    return {"summary": summary}


def _build_recommendations(plan: ExecutionPlan) -> list[dict]:
    """Build contextual recommendations based on the plan."""
    recs = []

    if "Generation Engine" in plan.modules_involved:
        recs.append(
            {
                "type": "model",
                "title": "Recommended: FLUX.1-dev",
                "reason": "Best photorealism for editorial content",
            }
        )

    if "Video Studio" in plan.modules_involved:
        recs.append(
            {
                "type": "video",
                "title": "Use 9:16 vertical for social",
                "reason": "Instagram/TikTok optimized format",
            }
        )

    if "Publishing Engine" in plan.modules_involved:
        recs.append(
            {
                "type": "publishing",
                "title": "Best time: Tuesday 7-9pm",
                "reason": "Historical engagement peak",
            }
        )

    return recs


# =============================================================================
# Plan
# =============================================================================


@router.post("/plan")
def brain_plan(data: dict):
    """Create a production plan without chatting.

    Body: {"request": "Create a luxury travel reel"}
    """
    request = data.get("request")
    if not request:
        raise HTTPException(status_code=400, detail="'request' required")

    plan = create_plan(request)
    return {
        "id": plan.id,
        "request": plan.request,
        "tasks": [
            {
                "id": t.id,
                "name": t.name,
                "module": t.module,
                "action": t.action,
                "status": t.status,
                "estimated_seconds": t.estimated_seconds,
            }
            for t in plan.tasks
        ],
        "reasoning": plan.reasoning,
        "estimated_total_seconds": plan.estimated_total_seconds,
        "estimated_cost": plan.estimated_cost,
        "confidence": plan.confidence,
        "modules_involved": plan.modules_involved,
    }


# =============================================================================
# Sessions
# =============================================================================


@router.get("/sessions")
def brain_sessions():
    """List all brain sessions."""
    return list_sessions()


@router.get("/sessions/{session_id}")
def brain_session_detail(session_id: str):
    """Get a session with conversation history."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": session.id,
        "messages": get_conversation_history(session_id),
        "created_at": session.created_at,
    }


# =============================================================================
# Context & Memory
# =============================================================================


@router.get("/context")
def brain_context():
    """Get the Brain's current context (what it knows about)."""
    return {
        "modules": list_modules(),
        "memory": get_production_memory(),
        "active_sessions": len(list_sessions()),
    }


@router.get("/memory")
def brain_memory():
    """Get production memory (learned preferences)."""
    return get_production_memory()


@router.put("/memory")
def update_memory(data: dict):
    """Update production memory."""
    for key, value in data.items():
        update_production_memory(key, value)
    return {"updated": True, "memory": get_production_memory()}


# =============================================================================
# Modules
# =============================================================================


@router.get("/modules")
def brain_modules():
    """List all modules registered with the Brain."""
    return list_modules()


# =============================================================================
# Reasoning
# =============================================================================


@router.get("/reasoning/{plan_id}")
def get_reasoning(plan_id: str):
    """Get reasoning for a specific plan (why these steps were chosen)."""
    # In a real implementation, reasoning would be stored per-plan
    return {
        "plan_id": plan_id,
        "reasoning": "Plan created based on intent analysis, module capabilities, and production memory.",
        "factors": [
            "User request keywords",
            "Available modules and their capabilities",
            "Production memory preferences",
            "Conversation history context",
        ],
    }


# =============================================================================
# LLM Chat (Ollama / OpenAI / Anthropic)
# =============================================================================


@router.get("/health")
def brain_health():
    """Check the AI Brain's LLM provider status."""
    from backend.brain.llm_provider import get_brain_health

    return get_brain_health()


@router.post("/llm/chat")
def brain_llm_chat(data: dict):
    """Chat directly with the LLM provider (Ollama/OpenAI/Anthropic).

    Body: {"messages": [{"role": "user", "content": "..."}], "mode": "creative"}
    Optional: "model" to override default, "mode" for specialized personality
    Optional: "images" — list of base64-encoded images for multimodal analysis
    Modes: creative, prompt_engineer, script_writer, story_assistant, production_advisor, image_analyzer
    """
    from backend.brain.llm_provider import LLMProviderError, chat

    messages = data.get("messages", [])
    if not messages:
        msg = data.get("message", "")
        if not msg:
            raise HTTPException(status_code=400, detail="'messages' or 'message' required")
        messages = [{"role": "user", "content": msg}]

    model = data.get("model")
    mode = data.get("mode", "creative")
    images = data.get("images", [])  # base64 images for multimodal
    collection_id = data.get("collection_id")  # optional: scope context to collection

    # If images provided, append to the last user message for Ollama multimodal
    if images and messages:
        last_msg = messages[-1]
        if isinstance(last_msg, dict) and last_msg.get("role") == "user":
            last_msg["images"] = images

    # RAG: inject relevant context from long-term memory
    try:
        from backend.brain.rag import build_context_prompt

        user_query = messages[-1].get("content", "") if messages else ""
        memory_context = build_context_prompt(user_query, collection_id=collection_id)
        if memory_context:
            # Prepend memory context as a system message
            messages = [{"role": "system", "content": memory_context}] + messages
    except Exception:
        pass  # RAG is optional — don't break chat if it fails

    try:
        response = chat(messages, model=model, mode=mode)
        return {"response": response, "model": model or "default", "mode": mode}
    except LLMProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))


# =============================================================================
# Auto-Fix — AI-powered code diagnostics fixer
# =============================================================================


@router.post("/fix")
async def brain_fix(data: dict):
    """AI Auto-Fix: analyze diagnostics and generate code patches.

    Tier 1: Pattern-based instant fixes (no LLM needed)
    Tier 2: LLM-assisted fixes via Ollama/Brain
    Tier 3: Suggestions requiring user approval

    Body:
        file_path: str — path to the file with errors
        file_content: str — current file content
        diagnostics: list — [{rule, message, line, column?, severity?}]
        auto_apply: bool — if True, apply high-confidence fixes and return patched content
        tier: int — max tier to use (1=patterns only, 2=patterns+LLM, default=2)

    Returns:
        fixes: list of proposed fixes with confidence scores
        patched_content: str (if auto_apply=True and fixes exist)
        stats: {total, tier1_count, tier2_count, applied_count}
    """
    file_path = data.get("file_path", "")
    file_content = data.get("file_content", "")
    raw_diagnostics = data.get("diagnostics", [])
    auto_apply = data.get("auto_apply", False)
    max_tier = data.get("tier", 2)

    if not file_content:
        raise HTTPException(status_code=400, detail="'file_content' required")
    if not raw_diagnostics:
        raise HTTPException(status_code=400, detail="'diagnostics' required (list of errors)")

    from backend.brain.modules.code_fixer import CodeFixer, Diagnostic

    # Parse diagnostics
    diagnostics = []
    for d in raw_diagnostics:
        diagnostics.append(
            Diagnostic(
                rule=d.get("rule", d.get("ruleId", "unknown")),
                message=d.get("message", ""),
                line=d.get("line", 0),
                column=d.get("column", 0),
                severity=d.get("severity", "error"),
            )
        )

    # Set up LLM provider for Tier 2 (if available and requested)
    llm_provider = None
    if max_tier >= 2:
        try:
            from backend.brain.llm_provider import get_provider

            llm_provider = get_provider()
        except Exception:
            pass  # LLM unavailable — Tier 1 only

    fixer = CodeFixer(llm_provider=llm_provider)

    # Run fixes
    all_fixes = await fixer.fix_file(file_path, file_content, diagnostics)

    # Separate by tier
    tier1_fixes = [f for f in all_fixes if f.tier == 1]
    tier2_fixes = [f for f in all_fixes if f.tier == 2]

    # Auto-apply if requested
    patched_content = None
    applied_count = 0
    if auto_apply and all_fixes:
        high_confidence = [f for f in all_fixes if f.confidence >= 0.8]
        if high_confidence:
            patched_content = fixer.apply_fixes(file_content, high_confidence)
            applied_count = len(high_confidence)

    # Format response
    fix_dicts = []
    for f in all_fixes:
        fix_dicts.append(
            {
                "rule": f.rule,
                "line": f.line,
                "tier": f.tier,
                "fix_type": f.fix_type,
                "original": f.original.rstrip("\n"),
                "replacement": f.replacement.rstrip("\n"),
                "confidence": f.confidence,
                "explanation": f.explanation,
            }
        )

    return {
        "fixes": fix_dicts,
        "patched_content": patched_content,
        "stats": {
            "total_diagnostics": len(diagnostics),
            "total_fixes": len(all_fixes),
            "tier1_count": len(tier1_fixes),
            "tier2_count": len(tier2_fixes),
            "applied_count": applied_count,
            "unfixable_count": len(diagnostics) - len(all_fixes),
        },
    }


# =============================================================================
# Collections — Persistent conversation grouping with shared context
# =============================================================================


def _db():
    from backend.database import supabase

    return supabase


@router.get("/collections")
def list_collections():
    """List all brain collections."""
    try:
        result = (
            _db().table("brain_collections").select("*").order("created_at", desc=True).execute()
        )
        return result.data or []
    except Exception:
        return []


@router.post("/collections", status_code=201)
def create_collection(data: dict):
    """Create a new collection."""
    record = {
        "name": data.get("name", "New Collection"),
        "color": data.get("color", "#7c3aed"),
        "talent_id": data.get("talent_id"),
        "description": data.get("description", ""),
    }
    try:
        result = _db().table("brain_collections").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/collections/{collection_id}")
def update_collection(collection_id: str, data: dict):
    """Update a collection (name, color, talent link)."""
    try:
        result = _db().table("brain_collections").update(data).eq("id", collection_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/collections/{collection_id}")
def delete_collection(collection_id: str):
    """Delete a collection (conversations remain, just unlinked)."""
    try:
        _db().table("brain_collections").delete().eq("id", collection_id).execute()
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Conversations — Persistent chat storage
# =============================================================================


@router.get("/conversations")
def list_conversations(collection_id: str = None, limit: int = 50):
    """List conversations, optionally filtered by collection."""
    try:
        query = (
            _db()
            .table("brain_conversations")
            .select("id,title,mode,message_count,collection_id,talent_id,created_at,updated_at")
            .order("updated_at", desc=True)
            .limit(limit)
        )
        if collection_id:
            query = query.eq("collection_id", collection_id)
        result = query.execute()
        return result.data or []
    except Exception:
        return []


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    """Get a conversation with full messages."""
    try:
        result = (
            _db()
            .table("brain_conversations")
            .select("*")
            .eq("id", conversation_id)
            .single()
            .execute()
        )
        return result.data
    except Exception:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.post("/conversations", status_code=201)
def create_conversation(data: dict):
    """Create or save a conversation."""
    record = {
        "title": data.get("title", "New Conversation"),
        "mode": data.get("mode", "creative"),
        "messages": data.get("messages", []),
        "message_count": len(data.get("messages", [])),
        "collection_id": data.get("collection_id"),
        "talent_id": data.get("talent_id"),
        "summary": data.get("summary", ""),
    }
    # If ID provided, upsert
    if data.get("id"):
        record["id"] = data["id"]
    try:
        result = _db().table("brain_conversations").upsert(record, on_conflict="id").execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/conversations/{conversation_id}")
def update_conversation(conversation_id: str, data: dict):
    """Update conversation (add messages, change collection, etc.)."""
    update = {}
    if "messages" in data:
        update["messages"] = data["messages"]
        update["message_count"] = len(data["messages"])
    if "title" in data:
        update["title"] = data["title"]
    if "collection_id" in data:
        update["collection_id"] = data["collection_id"]
    if "talent_id" in data:
        update["talent_id"] = data["talent_id"]
    if "summary" in data:
        update["summary"] = data["summary"]
    update["updated_at"] = "now()"

    try:
        result = (
            _db().table("brain_conversations").update(update).eq("id", conversation_id).execute()
        )
        return result.data[0] if result.data else update
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    try:
        _db().table("brain_conversations").delete().eq("id", conversation_id).execute()
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{collection_id}/context")
def get_collection_context(collection_id: str):
    """Get the shared context for a collection.

    Returns summaries of all conversations in the collection,
    plus any linked Talent creative DNA. Used by the Brain to
    maintain context across conversations in the same collection.
    """
    try:
        # Get collection info
        col = (
            _db().table("brain_collections").select("*").eq("id", collection_id).single().execute()
        )
        collection = col.data or {}

        # Get all conversations in this collection
        convs = (
            _db()
            .table("brain_conversations")
            .select("title,summary,mode,message_count")
            .eq("collection_id", collection_id)
            .order("updated_at", desc=True)
            .limit(10)
            .execute()
        )
        conversations = convs.data or []

        # Get linked talent creative DNA
        talent_context = ""
        talent_id = collection.get("talent_id")
        if talent_id:
            try:
                talent = (
                    _db()
                    .table("talent")
                    .select("name,bio,visual_style,best_for,persona")
                    .eq("id", talent_id)
                    .single()
                    .execute()
                )
                t = talent.data or {}
                talent_context = f"Talent: {t.get('name', '')}. Bio: {t.get('bio', '')}. Style: {t.get('visual_style', '')}. Best for: {t.get('best_for', '')}. Persona: {t.get('persona', '')}."
            except Exception:
                pass

        # Build context string
        context_parts = []
        if talent_context:
            context_parts.append(f"[Creative DNA] {talent_context}")
        for conv in conversations:
            if conv.get("summary"):
                context_parts.append(f"[{conv.get('title', 'Chat')}] {conv['summary']}")

        return {
            "collection": collection,
            "conversations": conversations,
            "talent_context": talent_context,
            "combined_context": "\n".join(context_parts),
            "context_length": len("\n".join(context_parts)),
        }
    except Exception as e:
        return {"error": str(e), "combined_context": ""}


# =============================================================================
# RAG — Embedding and context retrieval
# =============================================================================


@router.post("/embed/{conversation_id}")
def embed_conversation_endpoint(conversation_id: str):
    """Embed a conversation's content for RAG retrieval.

    Call this after a meaningful conversation to store it in long-term memory.
    The AI Brain will automatically retrieve relevant context in future chats.
    """
    from backend.brain.rag import embed_conversation

    try:
        conv = (
            _db()
            .table("brain_conversations")
            .select("messages,collection_id")
            .eq("id", conversation_id)
            .single()
            .execute()
        )
        if not conv.data:
            raise HTTPException(status_code=404, detail="Conversation not found")

        messages = conv.data.get("messages", [])
        collection_id = conv.data.get("collection_id")

        stored = embed_conversation(conversation_id, messages, collection_id)
        return {"embedded": True, "chunks_stored": stored, "conversation_id": conversation_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/embed/text")
def embed_text_endpoint(data: dict):
    """Embed arbitrary text into the Brain's memory.

    Use for: talent creative DNA, important prompts, notes, references.
    """
    from backend.brain.rag import embed_text

    text = data.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="'text' required")

    success = embed_text(
        text=text,
        source_type=data.get("source_type", "note"),
        collection_id=data.get("collection_id"),
        metadata=data.get("metadata"),
    )
    return {"embedded": success, "text_length": len(text)}


@router.post("/search")
def search_memory(data: dict):
    """Search the Brain's long-term memory.

    Returns relevant context chunks ranked by similarity.
    """
    from backend.brain.rag import search_context

    query = data.get("query", "")
    if not query:
        raise HTTPException(status_code=400, detail="'query' required")

    results = search_context(
        query=query,
        max_results=data.get("max_results", 5),
        threshold=data.get("threshold", 0.6),
        collection_id=data.get("collection_id"),
    )
    return {"results": results, "query": query, "count": len(results)}
