# AI Studio — Asset Intelligence Engine & Scene Composer

> Priority 10. Intelligent, reusable production assets.

---

## Overview

Every uploaded asset becomes intelligent. The system understands not just what
an asset IS, but how, when, where, and why it should be used. Assets are permanent
building blocks reusable across every production.

```
Upload → Visual DNA → Relationships → Collections → Scene Composition → Generation
```

---

## Visual DNA

Every asset receives Visual DNA:
- category, subcategory, style, brand, material
- color palette, texture, luxury/casual/formal scores
- season, occasion, indoor/outdoor compatibility
- recommended pairings (wardrobe, backgrounds, cameras, poses, lighting)

---

## Key Systems

| System | Purpose |
|---|---|
| Visual DNA | Asset self-understanding |
| Collections | User-organized groups |
| Relationships | How assets relate (matches, complements) |
| Wardrobes | Reusable outfit collections per talent |
| Outfits | Specific assembled looks |
| Scene Templates | Reusable compositions |
| Camera Presets | Lens, movement, framing |
| Lighting Presets | Setup, mood, temperature |
| Pose Presets | Body angle, head, hands, emotion |
| Smart Recommendations | AI suggests matching assets |
| Visual Search | Semantic asset discovery |

---

## 28 Asset Categories

wardrobe, accessories, shoes, jewelry, eyewear, hairstyles, makeup,
furniture, electronics, vehicles, food, drinks, products, props,
buildings, landmarks, backgrounds, textures, lighting_presets,
camera_presets, composition_templates, reference_images, mood_boards,
color_palettes, brand_assets, logos, custom

---

## Scene Composer

Drag-and-drop composition:
```
Talent + Wardrobe + Hairstyle + Accessories + Background + Furniture +
Products + Lighting + Camera + Pose + Mood → Generate
```
No prompt writing required.

---

## API Endpoints (25+)

| Category | Endpoints |
|---|---|
| Visual DNA | CRUD per asset |
| Collections | CRUD + items |
| Relationships | Create + query per asset |
| Wardrobes | CRUD + outfits |
| Scene Templates | CRUD |
| Camera Presets | List + create |
| Lighting Presets | List + create |
| Pose Presets | List + create |
| Recommendations | Smart matching per asset |
| Categories | List all |
| Search | Semantic visual search |

---

## Database Tables (11 new)

`visual_dna`, `asset_collections`, `collection_items`, `asset_relationships`,
`wardrobes`, `outfits`, `scene_templates`, `camera_presets`, `lighting_presets`, `pose_presets`

See `docs/sql/015_asset_intelligence.sql`.

---

## Brain Integration

When the Brain plans a production, it automatically:
- Recommends matching wardrobe from collections
- Suggests backgrounds based on Visual DNA
- Picks lighting presets for mood
- Selects camera presets for composition
- Recommends poses from the library
- Maintains continuity of assets across scenes

---

## Files

| File | Purpose |
|---|---|
| `backend/asset_intelligence/__init__.py` | Package |
| `backend/asset_intelligence/router.py` | 25+ API endpoints |
| `docs/sql/015_asset_intelligence.sql` | 11 database tables |
| `docs/ASSET_INTELLIGENCE.md` | This documentation |
