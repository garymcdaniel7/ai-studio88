#!/usr/bin/env python3
"""Run a WAN 2.2 Remix (fp8) image-to-video job on the Thunder worker (AR video pipeline)."""
import json, urllib.request, urllib.error, time, sys, os, mimetypes

BASE = "https://do5u5dbx-8188.thundercompute.net"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"

def post(path, data, timeout=60):
    body = json.dumps(data).encode()
    req = urllib.request.Request(BASE + path, data=body, headers={"Content-Type": "application/json", "User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout).read()

def upload_image(path):
    boundary = "----hermes"+str(int(time.time()))
    with open(path, "rb") as f:
        img = f.read()
    fn = os.path.basename(path)
    ctype = mimetypes.guess_type(path)[0] or "image/png"
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{fn}\"\r\nContent-Type: {ctype}\r\n\r\n".encode(),
        img,
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n".encode(),
    ]
    req = urllib.request.Request(BASE + "/upload/image", data=b"".join(parts), headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": UA})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

# upload start frame
up = upload_image("/tmp/hermes_klein.png")
print("uploaded:", up)
img_name = up.get("name") or "hermes_klein.png"

# AR video pipeline: ARVideoI2V → SamplerARVideo → BasicGuider + BasicScheduler + RandomNoise → SamplerCustomAdvanced
workflow = {
  "1":  {"class_type": "UNETLoader", "inputs": {"unet_name": "Wan2.2_Remix_NSFW_i2v_14b_high_lighting_v2.0.safetensors", "weight_dtype": "default"}},
  "2":  {"class_type": "CLIPLoader", "inputs": {"clip_name": "nsfw_wan_umt5-xxl_fp8_scaled.safetensors", "type": "wan", "device": "default"}},
  "3":  {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
  "4":  {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": "a golden retriever puppy running through a sunlit park, grass and flowers, camera follows the dog, cinematic, high detail"}},
  "5":  {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": "blurry, distorted, low quality, watermark, text"}},
  "6":  {"class_type": "LoadImage", "inputs": {"image": img_name}},
  "7":  {"class_type": "ARVideoI2V", "inputs": {"model": ["1", 0], "vae": ["3", 0], "start_image": ["6", 0], "width": 832, "height": 480, "length": 81, "batch_size": 1}},
  "8":  {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
  "9":  {"class_type": "BasicScheduler", "inputs": {"model": ["7", 0], "scheduler": "sgm_uniform", "steps": 20, "denoise": 1.0}},
  "10": {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}},
  "11": {"class_type": "KSampler", "inputs": {"model": ["7", 0], "seed": 42, "steps": 20, "cfg": 1.0, "sampler_name": "euler", "scheduler": "sgm_uniform", "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["7", 1], "denoise": 1.0}},
  "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
  "13": {"class_type": "CreateVideo", "inputs": {"images": ["12", 0], "fps": 16, "bit_depth": 8}},
  "14": {"class_type": "SaveVideo", "inputs": {"video": ["13", 0], "filename_prefix": "hermes_wan", "format": "mp4", "codec": "auto"}},
}

try:
    resp = post("/prompt", {"prompt": workflow})
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode()[:3000])
    sys.exit(1)

if isinstance(resp, bytes):
    resp = json.loads(resp.decode())
print("submitted:", json.dumps(resp)[:200])
pid = resp.get("prompt_id")
print("prompt_id:", pid)

# poll
for i in range(180):
    time.sleep(10)
    try:
        h = json.loads(urllib.request.urlopen(urllib.request.Request(f"{BASE}/history/{pid}", headers={"User-Agent": UA}), timeout=20).read())
    except Exception as e:
        print("poll err:", e); continue
    if pid in h:
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            print("ERROR:", json.dumps(st)[:1200]); sys.exit(1)
        if st.get("completed"):
            outs = h[pid].get("outputs", {})
            print("COMPLETED. outputs:", json.dumps(outs)[:800])
            sys.exit(0)
        print(f"  ...{i*10}s status={st.get('status_str')} progress={st.get('progress', {}).get('value', '?')}/{st.get('progress', {}).get('max', '?')}")
print("TIMEOUT waiting for video")
