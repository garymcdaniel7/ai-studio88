# Object Intelligence Engine

## Overview

The Object Intelligence Engine transforms every uploaded asset into an intelligent, reusable digital object. Instead of describing scenes from scratch, creators assemble productions using intelligent assets that the AI Brain understands automatically.

Upload once. Use forever.

## Core Concepts

### Object DNA

Every uploaded object receives an Object DNA profile containing:

- **Multi-view data**: front, back, left, right, top, bottom views
- **Geometry**: shape, dimensions, estimated scale
- **Materials**: textures, surface properties, reflection profile, shadow behavior
- **Visual details**: logos, branding, hardware, parts
- **Intelligence**: luxury score, style tags, recommended environments/lighting/cameras/poses
- **Compatibility**: characters, wardrobe, props that work with this object
- **Usage history**: track how and where the object has been used

### Product DNA

Commercial products receive an enhanced profile:

- Physical properties (geometry, materials, color palette, reflectivity)
- Branding (logos, brand identity)
- Scoring (luxury, style, lifestyle)
- Production profiles (camera, lighting, animation)
- Marketing metadata (tags, SEO keywords, variants)
- Recommendations (backgrounds, scenes, accessories, wardrobe, characters)

### Digital Twins

A Digital Twin is the canonical versioned representation of a physical object:

- Version control for physical objects (like Git for products)
- Canonical views used across all productions
- Support for future 3D formats (mesh, Gaussian Splats, NeRF, USD, glTF)
- Update a product (new colorway, new logo) and all campaigns can reference the latest version

### Virtual Try-On

Put any item on any talent:

- Clothing, shoes, watches, jewelry, glasses, bags, hats, scarves, belts
- AI understands body proportions, pose, perspective, lighting, depth
- Fabric draping, accessory placement, shadow/reflection matching
- Compare outfits side-by-side, generate seasonal wardrobes

### 360 Product Rotation

Generate interactive product views:

- 8, 12, 16, 24, 36, or 72 view angles
- Continuous rotation video
- Interactive viewer metadata
- Configurable background, lighting, resolution

### Scene DNA & Scene Composer

Reusable scene compositions:

- Assemble talent + wardrobe + products + props + background + lighting + camera + pose + mood
- Save as Scene DNA for future reuse
- The Brain generates the final production prompt
- Prompt writing becomes optional

### Material Intelligence

Understanding of 19+ material types with AI-powered recommendations:

- Optimal lighting, HDRI, camera angles
- Reflection and shadow handling
- Workflow and render settings per material
- Special handling for reflective objects (watches, jewelry, glass, chrome)

### Product Commercial Engine

One uploaded product generates multiple commercial outputs:

- Hero shots, Amazon/Shopify images, editorial, lifestyle, luxury campaign
- Social ads (Instagram, TikTok, Pinterest, YouTube)
- Billboards, website banners, email graphics
- Each output with correct resolution and background

## API Endpoints

Base path: `/api/v1/object-intelligence`

### Object DNA
| Method | Path | Description |
|--------|------|-------------|
| GET | `/object-dna` | List Object DNA profiles |
| POST | `/object-dna` | Create Object DNA |
| GET | `/object-dna/{id}` | Get specific profile |
| PUT | `/object-dna/{id}` | Update profile |
| DELETE | `/object-dna/{id}` | Delete profile |

### Product DNA
| Method | Path | Description |
|--------|------|-------------|
| GET | `/product-dna` | List Product DNA profiles |
| POST | `/product-dna` | Create Product DNA |
| GET | `/product-dna/{id}` | Get specific profile |
| PUT | `/product-dna/{id}` | Update profile |
| DELETE | `/product-dna/{id}` | Delete profile |

### Digital Twins
| Method | Path | Description |
|--------|------|-------------|
| GET | `/digital-twins` | List twins |
| POST | `/digital-twins` | Create twin |
| GET | `/digital-twins/{id}` | Get twin |
| PUT | `/digital-twins/{id}` | Update twin |
| POST | `/digital-twins/{id}/versions` | Create new version |

### Virtual Try-On
| Method | Path | Description |
|--------|------|-------------|
| GET | `/virtual-try-on` | List jobs |
| POST | `/virtual-try-on` | Create job |
| GET | `/virtual-try-on/{id}` | Get job |
| POST | `/virtual-try-on/{id}/complete` | Mark completed |

### 360 Renders
| Method | Path | Description |
|--------|------|-------------|
| GET | `/360-renders` | List renders |
| POST | `/360-renders` | Create render job |
| GET | `/360-renders/{id}` | Get render |
| PUT | `/360-renders/{id}` | Update render |

### Scene DNA
| Method | Path | Description |
|--------|------|-------------|
| GET | `/scene-dna` | List compositions |
| POST | `/scene-dna` | Create composition |
| GET | `/scene-dna/{id}` | Get composition |
| PUT | `/scene-dna/{id}` | Update composition |
| DELETE | `/scene-dna/{id}` | Delete composition |
| POST | `/scene-composer/compose` | Compose scene from assets |

### Materials
| Method | Path | Description |
|--------|------|-------------|
| GET | `/materials` | List profiles |
| POST | `/materials` | Create profile |
| GET | `/materials/{id}` | Get profile |
| GET | `/materials/{id}/recommendations` | Get render recommendations |

### Product Commercials
| Method | Path | Description |
|--------|------|-------------|
| GET | `/product-commercials/types` | List output types |
| POST | `/product-commercials/generate` | Generate commercial plan |

### Reference Data
| Method | Path | Description |
|--------|------|-------------|
| GET | `/categories` | List object categories |
| GET | `/material-types` | List material types |
| GET | `/recommend/{object_dna_id}` | Get AI recommendations |

## Database Tables

- `object_dna` — Core object profiles
- `product_dna` — Commercial product profiles
- `digital_twins` — Versioned canonical objects
- `digital_twin_versions` — Version history
- `virtual_tryon_jobs` — Try-on job queue
- `product_views_360` — 360 rotation renders
- `scene_dna` — Reusable scene compositions
- `material_profiles` — Material intelligence data

Migration: `docs/sql/018_object_intelligence.sql`

## Integration Points

- **AI Brain**: Understands all objects, recommends compositions
- **Asset Intelligence**: Visual DNA feeds into Object DNA
- **Story Engine**: Scene DNA used in story productions
- **Performance Engine**: Track which objects perform best
- **Timeline**: Scene DNA links to timeline positions
- **Publishing**: Product commercials feed publishing queue
- **Workflow Engine**: Material recommendations influence workflow selection

## Architecture

- FastAPI stores metadata only
- Heavy compute (segmentation, depth estimation, try-on rendering, 360 generation) runs on async GPU workers
- Provider adapters for future reconstruction technologies
- No tight coupling to any single AI provider

## Supported Object Categories

wardrobe, shoes, jewelry, watches, eyewear, handbags, luggage, furniture, vehicles, electronics, phones, tvs, computers, food, drinks, packaging, cosmetics, artwork, props, buildings, landmarks, rooms, locations, backgrounds, textures, lighting_references, camera_references, mood_boards, reference_photos, brand_assets, logos, product_collections

## Supported Material Types

leather, cotton, silk, chrome, glass, gold, silver, steel, carbon_fiber, plastic, wood, concrete, marble, ceramic, rubber, velvet, denim, mesh, suede
