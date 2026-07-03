"""Asset Intelligence API Router.

Visual DNA, wardrobes, outfits, collections, scene templates,
camera/lighting/pose presets, relationships, and recommendations.
"""
from __future__ import annotations

import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/asset-intelligence", tags=["asset-intelligence"])


def _db():
    from backend.database import supabase
    return supabase


# =============================================================================
# Visual DNA
# =============================================================================

@router.get("/visual-dna")
def list_visual_dna(category: Optional[str] = None):
    query = _db().table("visual_dna").select("*").order("created_at", desc=True)
    if category: query = query.eq("category", category)
    try: return query.execute().data
    except Exception: return []

@router.post("/visual-dna", status_code=201)
def create_visual_dna(data: dict):
    if not data.get("asset_id"):
        raise HTTPException(status_code=400, detail="'asset_id' required")
    try:
        result = _db().table("visual_dna").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/visual-dna/{asset_id}")
def get_visual_dna(asset_id: str):
    try: return _db().table("visual_dna").select("*").eq("asset_id", asset_id).single().execute().data
    except Exception: raise HTTPException(status_code=404, detail="Visual DNA not found")

@router.put("/visual-dna/{dna_id}")
def update_visual_dna(dna_id: str, data: dict):
    data["updated_at"] = "now()"
    try:
        result = _db().table("visual_dna").update(data).eq("id", dna_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Collections
# =============================================================================

@router.get("/collections")
def list_collections(collection_type: Optional[str] = None):
    query = _db().table("asset_collections").select("*").order("name")
    if collection_type: query = query.eq("collection_type", collection_type)
    try: return query.execute().data
    except Exception: return []

@router.post("/collections", status_code=201)
def create_collection(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("asset_collections").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collections/{collection_id}/items", status_code=201)
def add_to_collection(collection_id: str, data: dict):
    if not data.get("asset_id"):
        raise HTTPException(status_code=400, detail="'asset_id' required")
    record = {"collection_id": collection_id, "asset_id": data["asset_id"], "sort_order": int(data.get("sort_order", 0))}
    try:
        result = _db().table("collection_items").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/collections/{collection_id}/items")
def list_collection_items(collection_id: str):
    try: return _db().table("collection_items").select("*").eq("collection_id", collection_id).order("sort_order").execute().data
    except Exception: return []


# =============================================================================
# Asset Relationships
# =============================================================================

@router.get("/relationships/{asset_id}")
def get_relationships(asset_id: str):
    try:
        a = _db().table("asset_relationships").select("*").eq("asset_a_id", asset_id).execute().data or []
        b = _db().table("asset_relationships").select("*").eq("asset_b_id", asset_id).execute().data or []
        return a + b
    except Exception: return []

@router.post("/relationships", status_code=201)
def create_relationship(data: dict):
    if not data.get("asset_a_id") or not data.get("asset_b_id"):
        raise HTTPException(status_code=400, detail="'asset_a_id' and 'asset_b_id' required")
    record = {
        "asset_a_id": data["asset_a_id"],
        "asset_b_id": data["asset_b_id"],
        "relationship_type": data.get("relationship_type", "matches"),
        "strength": float(data.get("strength", 0.8)),
    }
    try:
        result = _db().table("asset_relationships").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Wardrobes & Outfits
# =============================================================================

@router.get("/wardrobes")
def list_wardrobes(talent_id: Optional[str] = None):
    query = _db().table("wardrobes").select("*").order("name")
    if talent_id: query = query.eq("talent_id", talent_id)
    try: return query.execute().data
    except Exception: return []

@router.post("/wardrobes", status_code=201)
def create_wardrobe(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("wardrobes").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/wardrobes/{wardrobe_id}/outfits")
def list_outfits(wardrobe_id: str):
    try: return _db().table("outfits").select("*").eq("wardrobe_id", wardrobe_id).order("name").execute().data
    except Exception: return []

@router.post("/outfits", status_code=201)
def create_outfit(data: dict):
    if not data.get("name") or not data.get("wardrobe_id"):
        raise HTTPException(status_code=400, detail="'name' and 'wardrobe_id' required")
    try:
        result = _db().table("outfits").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Scene Templates
# =============================================================================

@router.get("/scene-templates")
def list_scene_templates(category: Optional[str] = None):
    query = _db().table("scene_templates").select("*").order("name")
    if category: query = query.eq("category", category)
    try: return query.execute().data
    except Exception: return []

@router.post("/scene-templates", status_code=201)
def create_scene_template(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("scene_templates").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/scene-templates/{template_id}")
def get_scene_template(template_id: str):
    try: return _db().table("scene_templates").select("*").eq("id", template_id).single().execute().data
    except Exception: raise HTTPException(status_code=404, detail="Template not found")


# =============================================================================
# Camera / Lighting / Pose Presets
# =============================================================================

@router.get("/camera-presets")
def list_camera_presets():
    try: return _db().table("camera_presets").select("*").order("name").execute().data
    except Exception: return []

@router.post("/camera-presets", status_code=201)
def create_camera_preset(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("camera_presets").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/lighting-presets")
def list_lighting_presets():
    try: return _db().table("lighting_presets").select("*").order("name").execute().data
    except Exception: return []

@router.post("/lighting-presets", status_code=201)
def create_lighting_preset(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("lighting_presets").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pose-presets")
def list_pose_presets():
    try: return _db().table("pose_presets").select("*").order("name").execute().data
    except Exception: return []

@router.post("/pose-presets", status_code=201)
def create_pose_preset(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("pose_presets").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Smart Recommendations
# =============================================================================

@router.get("/recommend/{asset_id}")
def recommend_for_asset(asset_id: str):
    """Get smart recommendations for an asset based on Visual DNA and relationships.

    Returns matching wardrobes, backgrounds, lighting, cameras, and poses.
    """
    # Get Visual DNA
    try:
        dna = _db().table("visual_dna").select("*").eq("asset_id", asset_id).single().execute().data
    except Exception:
        dna = {}

    # Get relationships
    try:
        rels = _db().table("asset_relationships").select("*").eq("asset_a_id", asset_id).execute().data or []
    except Exception:
        rels = []

    category = dna.get("category", "general") if dna else "general"
    luxury = dna.get("luxury_score", 0.5) if dna else 0.5

    # Simulated recommendations based on Visual DNA
    recommendations = {
        "wardrobe": "luxury evening" if luxury > 0.7 else "smart casual",
        "lighting": "golden hour" if luxury > 0.7 else "natural daylight",
        "camera": "85mm portrait lens" if category == "wardrobe" else "35mm wide",
        "background": "luxury hotel lobby" if luxury > 0.7 else "modern studio",
        "pose": "fashion editorial" if luxury > 0.7 else "natural candid",
        "mood": "elegant" if luxury > 0.7 else "relaxed",
        "related_assets": len(rels),
        "visual_dna": dna,
    }
    return recommendations


# =============================================================================
# Categories
# =============================================================================

ASSET_CATEGORIES = [
    "wardrobe", "accessories", "shoes", "jewelry", "eyewear", "hairstyles",
    "makeup", "furniture", "electronics", "vehicles", "food", "drinks",
    "products", "props", "buildings", "landmarks", "backgrounds", "textures",
    "lighting_presets", "camera_presets", "composition_templates", "reference_images",
    "mood_boards", "color_palettes", "brand_assets", "logos", "custom",
]

@router.get("/categories")
def list_categories():
    """List all supported asset categories."""
    return ASSET_CATEGORIES


# =============================================================================
# Visual Search (simulated)
# =============================================================================

@router.get("/search")
def visual_search(q: str = ""):
    """Search assets by description (simulated semantic search)."""
    if not q:
        return {"results": [], "query": ""}

    # In production this would use embeddings / vector search
    # For now, search by category keywords
    q_lower = q.lower()
    matching_categories = [c for c in ASSET_CATEGORIES if any(w in q_lower for w in c.split("_"))]

    return {
        "query": q,
        "matched_categories": matching_categories,
        "results": [],  # Would contain actual asset matches with vector search
        "suggestion": f"Upload assets in categories: {', '.join(matching_categories[:3])}" if matching_categories else "Try different keywords",
    }
