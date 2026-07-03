"""Object Intelligence API Router.

Object DNA, Product DNA, Digital Twins, Virtual Try-On,
360 Product Rotation, Scene Composer, Material Intelligence,
and Product Commercial Engine.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/object-intelligence", tags=["object-intelligence"])


def _db():
    from backend.database import supabase
    return supabase


# =============================================================================
# Object DNA
# =============================================================================

@router.get("/object-dna")
def list_object_dna(category: Optional[str] = None, asset_id: Optional[str] = None):
    """List all Object DNA profiles."""
    query = _db().table("object_dna").select("*").order("created_at", desc=True)
    if category:
        query = query.eq("category", category)
    if asset_id:
        query = query.eq("asset_id", asset_id)
    try:
        return query.execute().data
    except Exception:
        return []


@router.post("/object-dna", status_code=201)
def create_object_dna(data: dict):
    """Create Object DNA profile for an asset."""
    if not data.get("asset_id"):
        raise HTTPException(status_code=400, detail="'asset_id' required")
    try:
        result = _db().table("object_dna").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/object-dna/{dna_id}")
def get_object_dna(dna_id: str):
    """Get a specific Object DNA profile."""
    try:
        return _db().table("object_dna").select("*").eq("id", dna_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Object DNA not found")


@router.put("/object-dna/{dna_id}")
def update_object_dna(dna_id: str, data: dict):
    """Update an Object DNA profile."""
    data["updated_at"] = "now()"
    try:
        result = _db().table("object_dna").update(data).eq("id", dna_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/object-dna/{dna_id}")
def delete_object_dna(dna_id: str):
    """Delete an Object DNA profile."""
    try:
        _db().table("object_dna").delete().eq("id", dna_id).execute()
        return {"status": "deleted", "id": dna_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Product DNA
# =============================================================================

@router.get("/product-dna")
def list_product_dna(category: Optional[str] = None):
    """List all Product DNA profiles."""
    query = _db().table("product_dna").select("*").order("created_at", desc=True)
    if category:
        query = query.eq("product_category", category)
    try:
        return query.execute().data
    except Exception:
        return []


@router.post("/product-dna", status_code=201)
def create_product_dna(data: dict):
    """Create Product DNA profile."""
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("product_dna").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/product-dna/{product_id}")
def get_product_dna(product_id: str):
    """Get a specific Product DNA profile."""
    try:
        return _db().table("product_dna").select("*").eq("id", product_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Product DNA not found")


@router.put("/product-dna/{product_id}")
def update_product_dna(product_id: str, data: dict):
    """Update a Product DNA profile."""
    data["updated_at"] = "now()"
    try:
        result = _db().table("product_dna").update(data).eq("id", product_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/product-dna/{product_id}")
def delete_product_dna(product_id: str):
    """Delete a Product DNA profile."""
    try:
        _db().table("product_dna").delete().eq("id", product_id).execute()
        return {"status": "deleted", "id": product_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Digital Twins
# =============================================================================

@router.get("/digital-twins")
def list_digital_twins(status: Optional[str] = None):
    """List all Digital Twins."""
    query = _db().table("digital_twins").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    try:
        return query.execute().data
    except Exception:
        return []


@router.post("/digital-twins", status_code=201)
def create_digital_twin(data: dict):
    """Create a Digital Twin from an object."""
    if not data.get("object_dna_id"):
        raise HTTPException(status_code=400, detail="'object_dna_id' required")
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("digital_twins").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/digital-twins/{twin_id}")
def get_digital_twin(twin_id: str):
    """Get a specific Digital Twin."""
    try:
        return _db().table("digital_twins").select("*").eq("id", twin_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Digital Twin not found")


@router.put("/digital-twins/{twin_id}")
def update_digital_twin(twin_id: str, data: dict):
    """Update a Digital Twin."""
    data["updated_at"] = "now()"
    try:
        result = _db().table("digital_twins").update(data).eq("id", twin_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/digital-twins/{twin_id}/versions", status_code=201)
def create_twin_version(twin_id: str, data: dict):
    """Create a new version of a Digital Twin (version control for physical objects)."""
    data["digital_twin_id"] = twin_id
    try:
        result = _db().table("digital_twin_versions").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Virtual Try-On
# =============================================================================

@router.get("/virtual-try-on")
def list_tryon_jobs(status: Optional[str] = None, talent_id: Optional[str] = None):
    """List Virtual Try-On jobs."""
    query = _db().table("virtual_tryon_jobs").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    if talent_id:
        query = query.eq("talent_id", talent_id)
    try:
        return query.execute().data
    except Exception:
        return []


@router.post("/virtual-try-on", status_code=201)
def create_tryon_job(data: dict):
    """Create a Virtual Try-On job."""
    if not data.get("talent_id"):
        raise HTTPException(status_code=400, detail="'talent_id' required")
    if not any(data.get(k) for k in ("wardrobe_item_id", "accessory_id", "product_dna_id")):
        raise HTTPException(status_code=400, detail="At least one item required")
    data.setdefault("status", "pending")
    try:
        result = _db().table("virtual_tryon_jobs").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/virtual-try-on/{job_id}")
def get_tryon_job(job_id: str):
    """Get Virtual Try-On job status and result."""
    try:
        return _db().table("virtual_tryon_jobs").select("*").eq("id", job_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Try-on job not found")


@router.post("/virtual-try-on/{job_id}/complete", status_code=200)
def complete_tryon_job(job_id: str, data: dict):
    """Mark a try-on job as completed with result URL."""
    update = {"status": "completed", "result_url": data.get("result_url"), "updated_at": "now()"}
    try:
        result = _db().table("virtual_tryon_jobs").update(update).eq("id", job_id).execute()
        return result.data[0] if result.data else update
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# 360 Product Rotation
# =============================================================================

@router.get("/360-renders")
def list_360_renders(product_id: Optional[str] = None):
    """List 360-degree product rotation renders."""
    query = _db().table("product_views_360").select("*").order("created_at", desc=True)
    if product_id:
        query = query.eq("product_dna_id", product_id)
    try:
        return query.execute().data
    except Exception:
        return []


@router.post("/360-renders", status_code=201)
def create_360_render(data: dict):
    """Create a 360-degree rotation render job."""
    if not data.get("product_dna_id"):
        raise HTTPException(status_code=400, detail="'product_dna_id' required")
    data.setdefault("view_count", 12)
    data.setdefault("status", "pending")
    try:
        result = _db().table("product_views_360").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/360-renders/{render_id}")
def get_360_render(render_id: str):
    """Get a specific 360 render job."""
    try:
        return _db().table("product_views_360").select("*").eq("id", render_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="360 render not found")


@router.put("/360-renders/{render_id}")
def update_360_render(render_id: str, data: dict):
    """Update a 360 render (add frames, mark complete)."""
    data["updated_at"] = "now()"
    try:
        result = _db().table("product_views_360").update(data).eq("id", render_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Scene DNA & Scene Composer
# =============================================================================

@router.get("/scene-dna")
def list_scene_dna(category: Optional[str] = None):
    """List all Scene DNA compositions."""
    query = _db().table("scene_dna").select("*").order("created_at", desc=True)
    if category:
        query = query.eq("category", category)
    try:
        return query.execute().data
    except Exception:
        return []


@router.post("/scene-dna", status_code=201)
def create_scene_dna(data: dict):
    """Create a reusable Scene DNA composition."""
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("scene_dna").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scene-dna/{scene_id}")
def get_scene_dna(scene_id: str):
    """Get a specific Scene DNA profile."""
    try:
        return _db().table("scene_dna").select("*").eq("id", scene_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Scene DNA not found")


@router.put("/scene-dna/{scene_id}")
def update_scene_dna(scene_id: str, data: dict):
    """Update a Scene DNA composition."""
    data["updated_at"] = "now()"
    try:
        result = _db().table("scene_dna").update(data).eq("id", scene_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/scene-dna/{scene_id}")
def delete_scene_dna(scene_id: str):
    """Delete a Scene DNA composition."""
    try:
        _db().table("scene_dna").delete().eq("id", scene_id).execute()
        return {"status": "deleted", "id": scene_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scene-composer/compose", status_code=201)
def compose_scene(data: dict):
    """Compose a scene from intelligent assets.

    Accepts: talent_ids, wardrobe_ids, product_ids, prop_ids,
    background, lighting, camera, pose, mood, music, voice.
    """
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    composition = {
        "name": data["name"],
        "talent_ids": data.get("talent_ids", []),
        "wardrobe_ids": data.get("wardrobe_ids", []),
        "product_ids": data.get("product_ids", []),
        "prop_ids": data.get("prop_ids", []),
        "background": data.get("background"),
        "lighting": data.get("lighting"),
        "camera": data.get("camera"),
        "pose": data.get("pose"),
        "mood": data.get("mood"),
        "music": data.get("music"),
        "voice": data.get("voice"),
        "category": data.get("category", "general"),
        "workflow_id": data.get("workflow_id"),
        "render_settings": data.get("render_settings", {}),
    }
    try:
        result = _db().table("scene_dna").insert(composition).execute()
        return result.data[0] if result.data else composition
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Material Intelligence
# =============================================================================

@router.get("/materials")
def list_material_profiles(material_type: Optional[str] = None):
    """List material intelligence profiles."""
    query = _db().table("material_profiles").select("*").order("name")
    if material_type:
        query = query.eq("material_type", material_type)
    try:
        return query.execute().data
    except Exception:
        return []


@router.post("/materials", status_code=201)
def create_material_profile(data: dict):
    """Create a material intelligence profile."""
    if not data.get("name") or not data.get("material_type"):
        raise HTTPException(status_code=400, detail="'name' and 'material_type' required")
    try:
        result = _db().table("material_profiles").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/materials/{material_id}")
def get_material_profile(material_id: str):
    """Get a specific material profile."""
    try:
        return _db().table("material_profiles").select("*").eq("id", material_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Material profile not found")


@router.get("/materials/{material_id}/recommendations")
def get_material_recommendations(material_id: str):
    """Get AI recommendations for rendering a material."""
    try:
        mat = _db().table("material_profiles").select("*").eq("id", material_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Material not found")

    material_type = mat.get("material_type", "unknown")
    recs_map = {
        "leather": {"lighting": "warm studio", "camera": "macro 100mm", "hdri": "soft box"},
        "glass": {"lighting": "backlit gradient", "camera": "45-degree", "hdri": "bright studio"},
        "chrome": {"lighting": "strip lights", "camera": "low angle", "hdri": "dark studio"},
        "gold": {"lighting": "warm golden hour", "camera": "close-up macro", "hdri": "luxury warm"},
        "silk": {"lighting": "soft diffused", "camera": "85mm portrait", "hdri": "fashion studio"},
        "marble": {"lighting": "natural window", "camera": "wide establishing", "hdri": "architectural"},
    }
    recs = recs_map.get(material_type, {"lighting": "neutral studio", "camera": "50mm", "hdri": "even white"})
    recs["material"] = mat
    return recs


# =============================================================================
# Product Commercials
# =============================================================================

COMMERCIAL_TYPES = [
    "hero_shot", "amazon", "shopify", "white_background", "transparent",
    "editorial", "lifestyle", "luxury_campaign", "close_up", "detail_shot",
    "exploded_view", "social_ad", "instagram", "tiktok", "pinterest",
    "youtube", "billboard", "website_banner", "email_graphic",
]


@router.get("/product-commercials/types")
def list_commercial_types():
    """List all supported product commercial output types."""
    return COMMERCIAL_TYPES


@router.post("/product-commercials/generate", status_code=201)
def generate_product_commercial(data: dict):
    """Generate a product commercial plan."""
    if not data.get("product_dna_id"):
        raise HTTPException(status_code=400, detail="'product_dna_id' required")
    requested_types = data.get("output_types", ["hero_shot"])
    product_id = data["product_dna_id"]
    try:
        product = _db().table("product_dna").select("*").eq("id", product_id).single().execute().data
    except Exception:
        product = {"name": "Unknown Product", "product_category": "general"}

    res_map = {
        "instagram": "1080x1080", "tiktok": "1080x1920", "pinterest": "1000x1500",
        "youtube": "1920x1080", "billboard": "3840x2160", "amazon": "2000x2000",
        "shopify": "2048x2048", "email_graphic": "600x400", "website_banner": "1920x600",
    }
    bg_map = {
        "amazon": "pure white", "shopify": "pure white", "white_background": "pure white",
        "transparent": "transparent PNG", "editorial": "contextual lifestyle",
        "luxury_campaign": "luxury environment", "lifestyle": "natural environment",
    }
    outputs = []
    for t in requested_types:
        if t in COMMERCIAL_TYPES:
            outputs.append({
                "type": t,
                "resolution": res_map.get(t, "2048x2048"),
                "background": bg_map.get(t, "neutral studio"),
                "status": "planned",
            })
    return {"product_dna_id": product_id, "product_name": product.get("name"), "outputs": outputs}


# =============================================================================
# Categories & Recommendations
# =============================================================================

OBJECT_CATEGORIES = [
    "wardrobe", "shoes", "jewelry", "watches", "eyewear", "handbags",
    "luggage", "furniture", "vehicles", "electronics", "phones", "tvs",
    "computers", "food", "drinks", "packaging", "cosmetics", "artwork",
    "props", "buildings", "landmarks", "rooms", "locations", "backgrounds",
    "textures", "lighting_references", "camera_references", "mood_boards",
    "reference_photos", "brand_assets", "logos", "product_collections",
]

MATERIAL_TYPES = [
    "leather", "cotton", "silk", "chrome", "glass", "gold", "silver",
    "steel", "carbon_fiber", "plastic", "wood", "concrete", "marble",
    "ceramic", "rubber", "velvet", "denim", "mesh", "suede",
]


@router.get("/categories")
def list_object_categories():
    """List all supported object categories."""
    return OBJECT_CATEGORIES


@router.get("/material-types")
def list_material_types():
    """List all supported material types."""
    return MATERIAL_TYPES


@router.get("/recommend/{object_dna_id}")
def recommend_for_object(object_dna_id: str):
    """Get AI recommendations for an object based on its DNA."""
    try:
        obj = _db().table("object_dna").select("*").eq("id", object_dna_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Object DNA not found")

    category = obj.get("category", "general")
    luxury_score = obj.get("luxury_score", 0.5)

    return {
        "object_dna_id": object_dna_id,
        "category": category,
        "recommended_lighting": "golden hour warm" if luxury_score > 0.7 else "natural daylight",
        "recommended_camera": "85mm f/1.4" if category in ("jewelry", "watches") else "50mm f/2.0",
        "recommended_background": "luxury hotel" if luxury_score > 0.7 else "clean studio",
        "recommended_workflow": "luxury_product" if luxury_score > 0.7 else "standard_product",
        "recommended_pose": "editorial fashion" if category == "wardrobe" else "product display",
        "suggested_angles": ["front", "45-degree", "detail", "lifestyle"],
        "commercial_potential": COMMERCIAL_TYPES[:5] if luxury_score > 0.7 else COMMERCIAL_TYPES[:3],
    }
