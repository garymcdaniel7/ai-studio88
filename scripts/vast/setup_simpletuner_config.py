"""Generate SimpleTuner config files for a training job.

Called via SSH on the GPU worker. Accepts JSON config on stdin, writes
SimpleTuner config files to /workspace/SimpleTuner/config/.

Usage (from backend):
    echo '{"steps": 1000, "lr": "1e-4", ...}' | ssh worker python setup_simpletuner_config.py
"""
import json
import sys
import os

# Read config from stdin
config = json.load(sys.stdin)

# Defaults
steps = config.get("steps", 1000)
lr = config.get("learning_rate", "1e-4")
rank = config.get("rank", 16)
resolution = config.get("resolution", 1024)
batch_size = config.get("batch_size", 1)
base_model = config.get("base_model", "black-forest-labs/FLUX.1-dev")
trigger_word = config.get("trigger_word", "ohwx")
optimizer = config.get("optimizer", "adamw_bf16")
scheduler = config.get("scheduler", "polynomial")
caption_method = config.get("caption_method", "filename")
dataset_dir = config.get("dataset_dir", "/workspace/training_data")
output_dir = config.get("output_dir", "/workspace/SimpleTuner/output")
job_id = config.get("job_id", "training_job")
validation_prompt = config.get("validation_prompt", f"A photo of {trigger_word}")

# Determine model family
model_family = "flux"
if "sdxl" in base_model.lower():
    model_family = "sdxl"
elif "sd-1" in base_model.lower() or "v1-5" in base_model.lower():
    model_family = "sd15"

# Write main config
main_config = {
    "--resume_from_checkpoint": "latest",
    "--data_backend_config": "config/multidatabackend.json",
    "--aspect_bucket_rounding": 2,
    "--seed": 42,
    "--minimum_image_size": 0,
    "--output_dir": output_dir,
    "--lora_type": "standard",
    "--lora_rank": rank,
    "--max_train_steps": steps,
    "--num_train_epochs": 0,
    "--checkpoint_step_interval": max(steps // 5, 100),
    "--checkpoints_total_limit": 3,
    "--tracker_project_name": f"ai-studio-{job_id}",
    "--tracker_run_name": job_id,
    "--report_to": "tensorboard",
    "--model_type": "lora",
    "--pretrained_model_name_or_path": base_model,
    "--model_family": model_family,
    "--train_batch_size": batch_size,
    "--gradient_checkpointing": "true",
    "--caption_dropout_probability": 0.1,
    "--resolution_type": "pixel_area",
    "--resolution": resolution,
    "--validation_seed": 42,
    "--validation_step_interval": max(steps // 4, 100),
    "--validation_resolution": f"{resolution}x{resolution}",
    "--validation_guidance": 3.5 if model_family == "flux" else 7.5,
    "--validation_guidance_rescale": "0.0",
    "--validation_num_inference_steps": "20" if model_family == "flux" else "30",
    "--validation_prompt": validation_prompt,
    "--mixed_precision": "bf16",
    "--optimizer": optimizer,
    "--learning_rate": lr,
    "--lr_scheduler": scheduler,
    "--lr_warmup_steps": min(100, steps // 10),
    "--validation_torch_compile": "false",
    "--disable_benchmark": "false",
}

# Write data backend config
data_backend = [
    {
        "id": f"training-{job_id}",
        "type": "local",
        "instance_data_dir": dataset_dir,
        "crop": True,
        "crop_style": "random",
        "crop_aspect": "preserve",
        "minimum_image_size": resolution // 2,
        "maximum_image_size": resolution * 2,
        "target_downsample_size": resolution,
        "resolution": resolution,
        "resolution_type": "pixel_area",
        "prepend_instance_prompt": True,
        "instance_prompt": trigger_word,
        "only_instance_prompt": False,
        "caption_strategy": caption_method,
        "cache_dir_vae": f"/workspace/SimpleTuner/cache/vae-{job_id}",
        "vae_cache_clear_each_epoch": True,
        "probability": 1.0,
        "repeats": max(1, 100 // max(1, config.get("image_count", 10))),
    },
    {
        "id": f"embeds-{job_id}",
        "dataset_type": "text_embeds",
        "default": True,
        "type": "local",
        "cache_dir": f"/workspace/SimpleTuner/cache/text-{job_id}",
    },
]

# Write files
config_dir = "/workspace/SimpleTuner/config"
os.makedirs(config_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)
os.makedirs(dataset_dir, exist_ok=True)

with open(f"{config_dir}/config.json", "w") as f:
    json.dump(main_config, f, indent=2)

with open(f"{config_dir}/multidatabackend.json", "w") as f:
    json.dump(data_backend, f, indent=2)

print(json.dumps({
    "status": "configured",
    "config_path": f"{config_dir}/config.json",
    "data_backend_path": f"{config_dir}/multidatabackend.json",
    "dataset_dir": dataset_dir,
    "output_dir": output_dir,
    "steps": steps,
    "base_model": base_model,
    "rank": rank,
}))
