# Skill: Train a LoRA

## Purpose

Train a LoRA model for a talent through the full lifecycle.

## Steps

```bash
# 1. Create dataset
curl -X POST http://localhost:8000/api/v1/training/datasets \
  -d '{"name":"Melissa v2","talent_id":"d2349ed1-...","description":"20 portrait shots"}'

# 2. Add images (from existing assets)
curl -X POST http://localhost:8000/api/v1/training/datasets/{dataset_id}/images \
  -d '{"asset_id":"asset-uuid-here","caption":"melissa_char, portrait"}'

# 3. Auto-caption all images
curl -X POST http://localhost:8000/api/v1/training/datasets/{dataset_id}/caption \
  -d '{"trigger_word":"melissa_char"}'

# 4. Edit a caption manually
curl -X PUT http://localhost:8000/api/v1/training/images/{image_id}/caption \
  -d '{"caption":"melissa_char, luxury portrait, golden hour, editorial"}'

# 5. Start training
curl -X POST http://localhost:8000/api/v1/training/jobs \
  -d '{"dataset_id":"...","config":{"steps":1000,"rank":16,"learning_rate":0.0001,"trigger_words":["melissa_char"]}}'

# 6. View LoRA versions
curl http://localhost:8000/api/v1/loras

# 7. Evaluate
curl -X POST http://localhost:8000/api/v1/loras/{lora_id}/evaluate \
  -d '{"rating":4,"identity_score":0.85,"realism_score":0.8,"notes":"Good likeness"}'

# 8. Promote as talent default
curl -X POST http://localhost:8000/api/v1/loras/{lora_id}/promote
```

## Training config options

| Field | Default | Description |
|---|---|---|
| base_model | flux1-dev-fp8 | Checkpoint to fine-tune |
| resolution | 512 | Training resolution |
| rank | 16 | LoRA rank (4-128) |
| steps | 1000 | Training steps |
| learning_rate | 1e-4 | LR |
| trigger_words | [] | Words that activate the LoRA |

## On completion

LoRA file → B2 → Asset → Model → LoRA Version → linked to talent
