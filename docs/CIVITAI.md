# AI Studio — Civitai Integration

> Future capability. Model discovery and metadata import from Civitai.

---

## Overview

Civitai is the largest community repository of AI models (checkpoints, LoRAs, etc.).
AI Studio will integrate with Civitai's API for model discovery, metadata import,
and (optionally) automated downloads to worker instances.

---

## API Key Setup

1. Create account at https://civitai.com
2. Go to Account Settings → API Keys
3. Generate a new key
4. Add to `.env`:
   ```
   CIVITAI_API_KEY=your-key-here
   CIVITAI_BASE_URL=https://civitai.com/api/v1
   ```

---

## Planned Features

### Phase 1: Metadata Import
- Search models by name/type/tag
- Import model metadata (name, description, images, stats)
- Link to existing local model files
- Track model versions

### Phase 2: LoRA Discovery
- Browse LoRAs by category (character, style, concept)
- Import LoRA metadata and trigger words
- Track LoRA compatibility with base models
- Rating and quality metrics

### Phase 3: Download Workflow
- Download models directly to worker instances
- Verify checksums after download
- Manage storage across multiple workers
- Track download progress in dashboard

---

## API Reference

```
GET /models       - search models
GET /models/{id}  - get model details
GET /models/{id}/versions - version history
GET /images       - model preview images
```

Requires `Authorization: Bearer {api_key}` header.

---

## Integration Points

| AI Studio Component | How Civitai Feeds It |
|---|---|
| Model Registry | Import metadata for discovered models |
| Model Expert Agent | Recommend models based on Civitai ratings |
| Worker Manager | Download models to specific workers |
| Creative DNA | Link LoRAs to talent visual identity |
| Workflow Templates | Suggest models compatible with workflows |

---

## Security

- API key stored in `.env` (never committed)
- Key is never exposed in API responses or dashboard
- Downloads happen on worker instances, not the API server
- File integrity verified via SHA-256 checksum
