# Skill: Manage Model Cache

## Purpose
Upload, download, and manage AI model files in the Backblaze B2 cache.

## List Cached Models
```bash
python scripts/vast/upload_model.py --list
```

## List Known Models
```bash
python scripts/vast/download_model.py --list-known
```

## Upload a Model to B2
```bash
# Known model (downloads from HF then uploads to B2)
python scripts/vast/upload_model.py --known sdxl-turbo

# Local file
python scripts/vast/upload_model.py --file ./model.safetensors --type checkpoint

# From HuggingFace
python scripts/vast/upload_model.py --hf stabilityai/sdxl-turbo --hf-file model.safetensors --type checkpoint
```

## Download from Cache
```bash
# Smart download (B2 first, HF fallback)
python scripts/vast/download_model.py --known sdxl-turbo --dest ./models/checkpoints

# For ComfyUI directory
python scripts/vast/download_model.py --known sdxl-turbo --comfyui-dir /workspace/ComfyUI
```

## Remote Seeding (fast, uses Vast.ai worker bandwidth)
```bash
python scripts/vast/seed_cache_remote.py --models sdxl-turbo,sd15-pruned,sdxl-vae --yes
```

## Known Models Registry
Located in `backend/providers/vast/model_cache.py` → `KNOWN_MODELS` dict.
To add a new model, add an entry with: filename, model_type, hf_repo, hf_filename, size_gb.

## Important
- B2 uses list_objects_v2 (not head_object) for existence checks
- Presigned URLs for worker downloads (1 hour expiry)
- B2 region must match endpoint: us-east-005
- Storage cap may need increasing in Backblaze dashboard
