-- =============================================================================
-- AI Studio: Seed initial model and template records
-- Run AFTER 006_models_and_templates.sql
-- =============================================================================

INSERT INTO models (name, family, type, provider, storage_path, version, required_vram_gb, supported_resolutions, supported_tasks, status) VALUES
('FLUX.1-dev (fp8)', 'flux', 'checkpoint', 'black-forest-labs', 'flux1-dev-fp8.safetensors', '1.0', 24.0, '["512x512","768x768","1024x1024","1536x1536"]', '["txt2img","img2img"]', 'available'),
('FLUX.1-dev (fp16)', 'flux', 'checkpoint', 'black-forest-labs', 'flux1-dev-fp16.safetensors', '1.0', 40.0, '["512x512","768x768","1024x1024","1536x1536","2048x2048"]', '["txt2img","img2img"]', 'available'),
('Stable Diffusion XL', 'sdxl', 'checkpoint', 'stability-ai', 'sd_xl_base_1.0.safetensors', '1.0', 12.0, '["512x512","768x768","1024x1024"]', '["txt2img","img2img","inpainting"]', 'available'),
('WAN Video 2.1', 'wan', 'checkpoint', 'wan', 'wan_2.1.safetensors', '2.1', 24.0, '["512x512","768x768"]', '["txt2video","img2video"]', 'available'),
('Hunyuan Video', 'hunyuan', 'checkpoint', 'tencent', 'hunyuan_video.safetensors', '1.0', 48.0, '["544x960","960x544"]', '["txt2video"]', 'available'),
('LTX Video', 'ltx', 'checkpoint', 'ltx', 'ltx_video.safetensors', '1.0', 24.0, '["512x512","768x768"]', '["txt2video","img2video"]', 'available'),
('Pony Diffusion XL', 'pony', 'checkpoint', 'community', 'ponyDiffusionV6XL.safetensors', '6.0', 12.0, '["512x512","768x768","1024x1024"]', '["txt2img"]', 'available'),
('4x-UltraSharp', 'upscaler', 'upscaler', 'community', '4x-UltraSharp.pth', '1.0', 4.0, '[]', '["upscale"]', 'available'),
('Test LoRA (Melissa)', 'flux', 'lora', 'custom', 'melissa_lora_v1.safetensors', '1.0', 0.5, '[]', '["txt2img"]', 'available');

INSERT INTO workflow_templates (name, description, category, provider, required_models, parameters, version, status) VALUES
('Flux Text-to-Image (Basic)', 'Simple txt2img with FLUX.1-dev', 'image', 'comfyui', '["flux1-dev-fp8.safetensors"]', '{"prompt":"","negative_prompt":"","width":1024,"height":1024,"steps":20,"cfg":3.5,"seed":-1}', '1.0', 'active'),
('SDXL Text-to-Image', 'Standard txt2img with SDXL', 'image', 'comfyui', '["sd_xl_base_1.0.safetensors"]', '{"prompt":"","negative_prompt":"","width":1024,"height":1024,"steps":30,"cfg":7.0,"seed":-1}', '1.0', 'active'),
('Image Upscale 4x', 'Upscale using 4x-UltraSharp', 'upscale', 'comfyui', '["4x-UltraSharp.pth"]', '{"scale_factor":4}', '1.0', 'active');
