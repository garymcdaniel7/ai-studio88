"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { Image as ImageIcon, Film, Music, Mic, FileText, Sparkles, Wand2, Loader2, ChevronDown, Settings2 } from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ModelOption { id: string; name: string; desc: string; vram: string; badge: string; }
interface LoraOption { id: string; name: string; trigger_words?: string; strength?: number; }

export default function CreatePage() {
  const [activeTab, setActiveTab] = useState<"image" | "video" | "audio" | "production">("image");
  const [prompt, setPrompt] = useState("");
  const [favoritePrompts, setFavoritePrompts] = useState<{text: string; savedAt: string}[]>([]);
  const [showFavorites, setShowFavorites] = useState(false);
  const [selectedModel, setSelectedModel] = useState("sdxl-turbo");
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<{image_base64?: string; filename?: string; generation_time?: number; error?: string; saved_to?: string; estimated_cost?: number} | null>(null);

  // Advanced panel
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [selectedLora, setSelectedLora] = useState("");
  const [loraStrength, setLoraStrength] = useState(0.7);
  const [activeLoras, setActiveLoras] = useState<{id: string; name: string; strength: number}[]>([]);
  const [controlType, setControlType] = useState("none");
  const [controlImageFile, setControlImageFile] = useState<File | null>(null);
  const [controlImagePreview, setControlImagePreview] = useState<string | null>(null);
  const [controlStrength, setControlStrength] = useState(0.7);
  const controlImageRef = useRef<HTMLInputElement>(null);
  const [negativePrompt, setNegativePrompt] = useState("");
  const [steps, setSteps] = useState(20);
  const [cfg, setCfg] = useState(7.5);
  const [seed, setSeed] = useState(-1);
  const [width, setWidth] = useState(1024);
  const [height, setHeight] = useState(1024);
  const [availableLoras, setAvailableLoras] = useState<LoraOption[]>([]);

  // Preset packs
  const [presets, setPresets] = useState<Record<string, unknown>[]>([]);
  const [presetFilter, setPresetFilter] = useState("image");

  // Generation history
  const [generationHistory, setGenerationHistory] = useState<Record<string, unknown>[]>([]);
  const [workerVram, setWorkerVram] = useState<number | null>(null);

  // Voice state
  const [voiceText, setVoiceText] = useState("");
  const [voiceLoading, setVoiceLoading] = useState(false);
  const [voiceResult, setVoiceResult] = useState<string | null>(null);

  // Music state
  const [musicPrompt, setMusicPrompt] = useState("");
  const [musicDuration, setMusicDuration] = useState("30");
  const [musicMood, setMusicMood] = useState("cinematic");
  const [musicLoading, setMusicLoading] = useState(false);
  const [musicResult, setMusicResult] = useState<string | null>(null);

  // Video state
  const [videoPrompt, setVideoPrompt] = useState("");
  const [videoLoading, setVideoLoading] = useState(false);
  const [videoResult, setVideoResult] = useState<string | null>(null);
  const [selectedVideoModel, setSelectedVideoModel] = useState("wan2.2-5b");
  const [videoDownloadUrl, setVideoDownloadUrl] = useState<string | null>(null);
  const [videoDuration, setVideoDuration] = useState("2");

  // Video from Image state
  const [videoImageFile, setVideoImageFile] = useState<File | null>(null);
  const [videoImagePreview, setVideoImagePreview] = useState<string | null>(null);
  const [videoImageLoading, setVideoImageLoading] = useState(false);
  const [videoImageResult, setVideoImageResult] = useState<string | null>(null);
  const [videoMotionPrompt, setVideoMotionPrompt] = useState("");
  const videoImageInputRef = useRef<HTMLInputElement>(null);
  const [gpuReadyModels, setGpuReadyModels] = useState<Set<string>>(new Set(["sdxl-turbo"]));

  const [imageModelList, setImageModelList] = useState<ModelOption[]>([
    { id: "flux2-dev", name: "Flux 2 Dev", desc: "Best quality, 32B params, up to 4MP", vram: "24GB+", badge: "New" },
    { id: "flux2-klein", name: "Flux 2 Klein", desc: "Fast 4B model, 4 steps, great quality", vram: "12GB", badge: "Fast" },
    { id: "sdxl-turbo", name: "SDXL Turbo", desc: "1 step, 512x512, instant", vram: "8GB", badge: "" },
    { id: "flux-dev", name: "Flux Dev (v1)", desc: "High quality, 1024x1024, 20 steps", vram: "32GB", badge: "" },
    { id: "sd15", name: "SD 1.5", desc: "Classic, versatile, 512x512", vram: "6GB", badge: "" },
  ]);
  const [videoModelList, setVideoModelList] = useState<ModelOption[]>([
    { id: "wan-2.1-t2v", name: "WAN 2.1 (Text-to-Video)", desc: "14B parameter, 2s clips at 24fps", vram: "80GB+", badge: "New" },
    { id: "wan-2.1-i2v", name: "WAN 2.1 (Image-to-Video)", desc: "Animate any image into video", vram: "80GB+", badge: "" },
  ]);

  // Load favorite prompts from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem("favorite_prompts");
      if (saved) setFavoritePrompts(JSON.parse(saved));
    } catch {}
  }, []);

  function saveFavorite() {
    if (!prompt.trim()) return;
    const updated = [{ text: prompt.trim(), savedAt: new Date().toISOString() }, ...favoritePrompts.filter((f) => f.text !== prompt.trim())].slice(0, 50);
    setFavoritePrompts(updated);
    localStorage.setItem("favorite_prompts", JSON.stringify(updated));
  }

  function removeFavorite(text: string) {
    const updated = favoritePrompts.filter((f) => f.text !== text);
    setFavoritePrompts(updated);
    localStorage.setItem("favorite_prompts", JSON.stringify(updated));
  }

  // Fetch models + LoRAs from API
  useEffect(() => {
    fetch(`${API_BASE}/api/v1/generation/available-models`)
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          const images = data.filter((m: Record<string, unknown>) => m.type !== "video" && !String(m.id || m.name || "").includes("wan"));
          const videos = data.filter((m: Record<string, unknown>) => m.type === "video" || String(m.id || m.name || "").includes("wan"));
          if (images.length > 0) setImageModelList(images.map((m: Record<string, unknown>) => ({ id: String(m.id || m.name), name: String(m.name || m.id), desc: String(m.description || m.desc || ""), vram: String(m.required_vram_gb ? m.required_vram_gb + "GB" : m.vram || ""), badge: String(m.badge || "") })));
          if (videos.length > 0) setVideoModelList(videos.map((m: Record<string, unknown>) => ({ id: String(m.id || m.name), name: String(m.name || m.id), desc: String(m.description || m.desc || ""), vram: String(m.required_vram_gb ? m.required_vram_gb + "GB" : m.vram || ""), badge: String(m.badge || "") })));
        }
      })
      .catch(() => {});

    // Fetch available LoRAs
    fetch(`${API_BASE}/api/v1/models?type=lora`)
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) {
          setAvailableLoras(data.map((m: Record<string, unknown>) => ({
            id: String(m.id || ""),
            name: String(m.name || ""),
            trigger_words: String((m.metadata as Record<string, unknown>)?.trigger_words || ""),
            strength: 0.7,
          })));
        }
      })
      .catch(() => {});

    // Fetch preset packs
    fetch(`${API_BASE}/api/v1/presets`)
      .then((r) => r.json())
      .then((data) => { if (Array.isArray(data)) setPresets(data); })
      .catch(() => {});

    // Fetch which models are actually loaded on the GPU — also populates dropdown
    fetch(`${API_BASE}/api/v1/generate/available-models`)
      .then((r) => r.json())
      .then((data) => {
        if (data?.models) {
          const allModels = data.models as {id: string; name: string; ready: boolean; vram?: string; badge?: string}[];
          const ready = new Set<string>(allModels.filter((m) => m.ready).map((m) => m.id));
          setGpuReadyModels(ready);

          // Update image model list from this authoritative source
          const imageModels = allModels.filter((m) => !m.id.includes("wan"));
          if (imageModels.length > 0) {
            setImageModelList(imageModels.map((m) => ({
              id: m.id,
              name: m.name,
              desc: m.ready ? "Ready on GPU" : "Not loaded (available in B2)",
              vram: m.vram || "",
              badge: m.badge || (m.ready ? "" : ""),
            })));
          }

          // Update video model list
          const videoModels = allModels.filter((m) => m.id.includes("wan"));
          if (videoModels.length > 0) {
            setVideoModelList(videoModels.map((m) => ({
              id: m.id,
              name: m.name,
              desc: m.ready ? "Ready on GPU" : "Not loaded",
              vram: m.vram || "",
              badge: m.badge || "",
            })));
          }
        }
      })
      .catch(() => {});

    // Fetch generation history (recent completed jobs with outputs)
    fetch(`${API_BASE}/api/v1/jobs?status=completed`)
      .then((r) => r.json())
      .then((data) => { if (Array.isArray(data)) setGenerationHistory(data.slice(0, 12)); })
      .catch(() => {});

    // Fetch worker VRAM for GPU compatibility badges
    fetch(`${API_BASE}/api/v1/infrastructure/status`)
      .then((r) => r.json())
      .then((data) => {
        const vram = (data as Record<string, Record<string, unknown>>)?.worker?.gpu_vram_gb;
        if (typeof vram === "number") setWorkerVram(vram);
      })
      .catch(() => {});

    // Update steps/cfg defaults when model changes
  }, []);

  // Check for injected prompt from Brain page
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const injectedPrompt = params.get("prompt") || sessionStorage.getItem("injected_prompt");
    const injectedTab = params.get("tab") || sessionStorage.getItem("injected_tab");
    if (injectedPrompt) {
      const decoded = decodeURIComponent(injectedPrompt);
      // Route prompt to the correct field based on tab
      if (injectedTab === "audio") {
        setVoiceText(decoded);
      } else if (injectedTab === "video") {
        setVideoPrompt(decoded);
      } else {
        setPrompt(decoded);
      }
      sessionStorage.removeItem("injected_prompt");
      sessionStorage.removeItem("injected_tab");
    }
    if (injectedTab && ["image", "video", "audio", "production"].includes(injectedTab)) {
      setActiveTab(injectedTab as "image" | "video" | "audio" | "production");
    }
  }, []);

  // Sync defaults when model changes
  useEffect(() => {
    const defaults: Record<string, { steps: number; cfg: number; width: number; height: number }> = {
      "flux2-dev": { steps: 20, cfg: 1.0, width: 1024, height: 1024 },
      "flux2-klein": { steps: 4, cfg: 1.0, width: 1024, height: 1024 },
      "sdxl-turbo": { steps: 1, cfg: 1.0, width: 512, height: 512 },
      "flux-dev": { steps: 20, cfg: 1.0, width: 1024, height: 1024 },
      "sd15": { steps: 20, cfg: 7.5, width: 512, height: 512 },
    };
    const d = defaults[selectedModel];
    if (d) { setSteps(d.steps); setCfg(d.cfg); setWidth(d.width); setHeight(d.height); }
  }, [selectedModel]);

  async function handleGenerateVoice() {
    if (!voiceText.trim() || voiceLoading) return;
    setVoiceLoading(true);
    setVoiceResult(null);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/voice/generate-tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: voiceText, voice_id: "rachel", provider: "simulation" }),
      });
      const data = await resp.json();
      setVoiceResult(data.audio_url || data.message || "Speech generated successfully");
    } catch {
      setVoiceResult("Failed to generate speech. Is the backend running?");
    } finally {
      setVoiceLoading(false);
    }
  }

  async function handleGenerateMusic() {
    if (!musicPrompt.trim() || musicLoading) return;
    setMusicLoading(true);
    setMusicResult(null);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/audio/music/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: musicPrompt, duration: parseInt(musicDuration), mood: musicMood }),
      });
      const data = await resp.json();
      setMusicResult(data.audio_url || data.message || "Music generated successfully");
    } catch {
      setMusicResult("Failed to generate music. Is the backend running?");
    } finally {
      setMusicLoading(false);
    }
  }

  async function handleGenerateVideo() {
    if (!videoPrompt.trim() || videoLoading) return;
    setVideoLoading(true);
    setVideoResult(null);
    setVideoDownloadUrl(null);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/generate/video`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: videoPrompt,
          model: selectedVideoModel,
          width: 832,
          height: 480,
          duration_seconds: parseFloat(videoDuration),
          steps: 20,
        }),
      });
      const data = await resp.json();
      if (data.success) {
        setVideoResult(`Video generated in ${data.generation_time}s — ${data.frames} frames • ${data.filename}`);
        if (data.download_url) setVideoDownloadUrl(data.download_url);
      } else {
        setVideoResult(data.detail || "Video generation failed. Ensure WAN 2.2 model is loaded on GPU.");
      }
    } catch {
      setVideoResult("Video generation is taking longer than expected. It may still be processing on the GPU — check back in a few minutes.");
    } finally {
      setVideoLoading(false);
    }
  }

  function handleVideoImageSelect(file: File) {
    setVideoImageFile(file);
    setVideoImageResult(null);
    const reader = new FileReader();
    reader.onload = (e) => setVideoImagePreview(e.target?.result as string);
    reader.readAsDataURL(file);
  }

  function handleVideoImageDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("image/")) handleVideoImageSelect(file);
  }

  async function handleAnimateImage() {
    if (!videoImageFile || videoImageLoading) return;
    setVideoImageLoading(true);
    setVideoImageResult(null);
    try {
      // Upload image first, then generate video with it as starting frame
      const formData = new FormData();
      formData.append("file", videoImageFile);
      formData.append("motion_prompt", videoMotionPrompt || "gentle camera movement, cinematic");

      const resp = await fetch(`${API_BASE}/api/v1/generate/video-from-image`, {
        method: "POST",
        body: formData,
      });
      const data = await resp.json();
      if (data.success) {
        setVideoImageResult(`Video generated in ${data.generation_time}s — ${data.frames} frames • ${data.filename}`);
      } else {
        setVideoImageResult(data.detail || "Image-to-video generation failed. Ensure WAN 2.2 model is loaded.");
      }
    } catch {
      setVideoImageResult("Video generation in progress... This takes several minutes. Check back shortly.");
    } finally {
      setVideoImageLoading(false);
    }
  }

  async function handleGenerate() {
    if (!prompt.trim() || generating) return;
    setGenerating(true);
    setResult(null);

    try {
      const payload: Record<string, unknown> = {
        prompt,
        model: selectedModel,
        negative_prompt: negativePrompt || undefined,
        steps,
        cfg,
        seed,
        width,
        height,
      };
      if (selectedLora) {
        payload.lora = selectedLora;
        payload.lora_strength = loraStrength;
      }
      if (activeLoras.length > 0) {
        payload.loras = activeLoras.map((l) => ({ id: l.id, strength: l.strength }));
      }
      if (controlType !== "none" && controlImageFile) {
        // For ControlNet, we need to upload the image first then pass the filename
        payload.controlnet = {
          type: controlType,
          strength: controlStrength,
        };
      }

      const resp = await fetch(`${API_BASE}/api/v1/generate/image`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      if (data.success) {
        setResult(data);
      } else {
        setResult({ error: data.detail || "Generation failed" });
      }
    } catch {
      setResult({ error: "Cannot reach backend. Is ComfyUI worker running?" });
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Create</h1>
        <p className="text-sm text-gray-500">Generate AI content — images, videos, voice, music, or full productions.</p>
      </div>

      {/* Type Tabs */}
      <div className="flex gap-1 border-b border-white/[0.06] pb-px">
        {[
          { key: "image", label: "Image Generation", icon: ImageIcon },
          { key: "video", label: "Video Generation", icon: Film },
          { key: "audio", label: "Voice & Music", icon: Mic },
          { key: "production", label: "Full Production", icon: FileText },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key as "image" | "video" | "audio" | "production")}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? "border-b-2 border-purple-500 text-purple-400"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Image Generation */}
      {activeTab === "image" && (
        <div className="space-y-6">
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
            <h3 className="text-sm font-semibold text-white mb-1">Quick Generate</h3>
            <p className="text-xs text-gray-500 mb-4">Describe what you want — AI handles the rest.</p>

            {/* Main row: prompt + model + generate */}
            <div className="flex gap-3 mb-2">
              <div className="flex-1 relative">
                <input
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) handleGenerate(); }}
                  className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 pr-10 text-sm text-gray-200 placeholder:text-gray-600 outline-none focus:border-purple-500/50"
                  placeholder="A luxury penthouse at sunset, photorealistic..."
                />
                {/* Star/Favorite button */}
                <button
                  onClick={saveFavorite}
                  disabled={!prompt.trim()}
                  className={`absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded transition-colors ${
                    favoritePrompts.some((f) => f.text === prompt.trim())
                      ? "text-yellow-400"
                      : "text-gray-600 hover:text-yellow-400"
                  } disabled:opacity-30`}
                  title="Save to favorites"
                >
                  <svg className="h-4 w-4" fill={favoritePrompts.some((f) => f.text === prompt.trim()) ? "currentColor" : "none"} stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" /></svg>
                </button>
              </div>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="rounded-lg border border-white/[0.08] bg-[#12122a] px-3 py-2 text-sm text-gray-300 outline-none"
              >
                {imageModelList.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}{gpuReadyModels.has(m.id) ? "" : " (not loaded)"}</option>
                ))}
              </select>
              <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-colors ${showAdvanced ? "border-purple-500/50 bg-purple-600/10 text-purple-400" : "border-white/[0.08] bg-white/[0.03] text-gray-400 hover:text-gray-200"}`}
              >
                <Settings2 className="h-4 w-4" />
                <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showAdvanced ? "rotate-180" : ""}`} />
              </button>
              <button
                onClick={handleGenerate}
                disabled={generating || !prompt.trim()}
                className="rounded-lg bg-purple-600 px-6 py-2 text-sm font-medium text-white hover:bg-purple-700 flex items-center gap-2 disabled:opacity-50"
              >
                {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {generating ? "Generating..." : "Generate"}
              </button>
            </div>

            {/* Favorites Bar */}
            {favoritePrompts.length > 0 && (
              <div className="mb-2">
                <button
                  onClick={() => setShowFavorites(!showFavorites)}
                  className="text-[10px] text-yellow-400/70 hover:text-yellow-400 transition-colors"
                >
                  ★ {favoritePrompts.length} saved prompt{favoritePrompts.length > 1 ? "s" : ""} {showFavorites ? "▾" : "▸"}
                </button>
                {showFavorites && (
                  <div className="mt-2 max-h-32 overflow-y-auto space-y-1 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2">
                    {favoritePrompts.slice(0, 10).map((fav, idx) => (
                      <div key={idx} className="flex items-center gap-2 group/fav">
                        <button
                          onClick={() => setPrompt(fav.text)}
                          className="flex-1 text-left text-[11px] text-gray-400 hover:text-white truncate py-0.5 px-1 rounded hover:bg-white/[0.04]"
                        >
                          {fav.text}
                        </button>
                        <button
                          onClick={() => removeFavorite(fav.text)}
                          className="opacity-0 group-hover/fav:opacity-100 text-[10px] text-gray-600 hover:text-red-400"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Advanced Panel */}
            {showAdvanced && (
              <div className="mt-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-4 space-y-3">
                <p className="text-xs font-semibold text-gray-300">Advanced Settings</p>

                {/* Row 1: LoRA + Negative */}
                <div>
                  <label className="block text-[10px] text-gray-500 mb-1">LoRA Models</label>
                  {/* Active LoRAs */}
                  {activeLoras.map((lora, idx) => (
                    <div key={lora.id} className="flex items-center gap-2 mb-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-2 py-1.5">
                      <span className="text-xs text-gray-300 flex-1 truncate">{lora.name}</span>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={lora.strength}
                        onChange={(e) => {
                          const updated = [...activeLoras];
                          updated[idx] = { ...updated[idx], strength: parseFloat(e.target.value) };
                          setActiveLoras(updated);
                        }}
                        className="w-20 accent-purple-500"
                      />
                      <span className="text-[10px] text-gray-500 w-8">{lora.strength.toFixed(2)}</span>
                      <button
                        onClick={() => setActiveLoras((prev) => prev.filter((_, i) => i !== idx))}
                        className="text-gray-600 hover:text-red-400 text-xs"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                  {/* Add LoRA dropdown */}
                  <select
                    value={selectedLora}
                    onChange={(e) => {
                      const id = e.target.value;
                      if (!id) return;
                      const lora = availableLoras.find((l) => l.id === id);
                      if (lora && !activeLoras.find((a) => a.id === id)) {
                        setActiveLoras((prev) => [...prev, { id: lora.id, name: lora.name, strength: lora.strength || 0.7 }]);
                      }
                      setSelectedLora("");
                    }}
                    className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-gray-300 outline-none"
                  >
                    <option value="">+ Add LoRA...</option>
                    {availableLoras
                      .filter((l) => !activeLoras.find((a) => a.id === l.id))
                      .map((l) => (
                        <option key={l.id} value={l.id}>{l.name}</option>
                      ))}
                  </select>
                  {activeLoras.length === 0 && (
                    <p className="text-[10px] text-gray-600 mt-1">No LoRAs active. Add one above to apply style/character training.</p>
                  )}
                </div>

                {/* Row 2: Negative prompt */}
                <div>
                  <label className="block text-[10px] text-gray-500 mb-1">Negative Prompt</label>
                  <input
                    type="text"
                    value={negativePrompt}
                    onChange={(e) => setNegativePrompt(e.target.value)}
                    placeholder="blurry, low quality, deformed, watermark..."
                    className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-gray-300 placeholder:text-gray-600 outline-none"
                  />
                </div>

                {/* Row 3: Steps, CFG, Seed */}
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[10px] text-gray-500 mb-1">Steps: {steps}</label>
                    <input type="range" min="1" max="50" value={steps} onChange={(e) => setSteps(parseInt(e.target.value))} className="w-full accent-purple-500" />
                  </div>
                  <div>
                    <label className="block text-[10px] text-gray-500 mb-1">CFG Scale: {cfg.toFixed(1)}</label>
                    <input type="range" min="1" max="20" step="0.5" value={cfg} onChange={(e) => setCfg(parseFloat(e.target.value))} className="w-full accent-purple-500" />
                  </div>
                  <div>
                    <label className="block text-[10px] text-gray-500 mb-1">Seed (-1 = random)</label>
                    <input
                      type="number"
                      value={seed}
                      onChange={(e) => setSeed(parseInt(e.target.value))}
                      className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-300 outline-none"
                    />
                  </div>
                </div>

                {/* Row 4: Resolution */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[10px] text-gray-500 mb-1">Width: {width}px</label>
                    <select value={width} onChange={(e) => setWidth(parseInt(e.target.value))} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-gray-300 outline-none">
                      {[512, 768, 1024, 1280, 1536].map((v) => <option key={v} value={v}>{v}px</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-[10px] text-gray-500 mb-1">Height: {height}px</label>
                    <select value={height} onChange={(e) => setHeight(parseInt(e.target.value))} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-gray-300 outline-none">
                      {[512, 768, 1024, 1280, 1536].map((v) => <option key={v} value={v}>{v}px</option>)}
                    </select>
                  </div>
                </div>

                {/* Row 5: ControlNet / Pose Reference */}
                <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-[10px] font-semibold text-blue-300">ControlNet / Pose Reference</label>
                    <select
                      value={controlType}
                      onChange={(e) => setControlType(e.target.value)}
                      className="rounded border border-white/[0.08] bg-white/[0.03] px-2 py-0.5 text-[10px] text-gray-300 outline-none"
                    >
                      <option value="none">Disabled</option>
                      <option value="openpose">OpenPose (Body Pose)</option>
                      <option value="canny">Canny (Edge Detection)</option>
                      <option value="depth">Depth Map</option>
                    </select>
                  </div>
                  {controlType !== "none" && (
                    <div className="space-y-2">
                      <div
                        onClick={() => controlImageRef.current?.click()}
                        className="rounded-lg border border-dashed border-white/[0.1] bg-white/[0.02] p-4 text-center cursor-pointer hover:border-blue-500/30"
                      >
                        {controlImagePreview ? (
                          <div className="flex items-center gap-3">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src={controlImagePreview} alt="Reference" className="h-16 w-16 rounded object-cover" />
                            <div className="text-left">
                              <p className="text-xs text-gray-300">Reference uploaded</p>
                              <p className="text-[10px] text-gray-500">Type: {controlType}</p>
                            </div>
                          </div>
                        ) : (
                          <p className="text-[10px] text-gray-500">Upload a reference image for {controlType} guidance</p>
                        )}
                      </div>
                      <input
                        ref={controlImageRef}
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          if (f) {
                            setControlImageFile(f);
                            const reader = new FileReader();
                            reader.onload = (ev) => setControlImagePreview(ev.target?.result as string);
                            reader.readAsDataURL(f);
                          }
                        }}
                      />
                      <div className="flex items-center gap-3">
                        <label className="text-[10px] text-gray-500">Strength: {controlStrength.toFixed(2)}</label>
                        <input
                          type="range"
                          min="0"
                          max="1"
                          step="0.05"
                          value={controlStrength}
                          onChange={(e) => setControlStrength(parseFloat(e.target.value))}
                          className="flex-1 accent-blue-500"
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Preset Packs Browser */}
          {presets.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-white">Style Presets</h3>
                <div className="flex gap-1">
                  {["all", "image", "utility", "advanced"].map((cat) => (
                    <button
                      key={cat}
                      onClick={() => setPresetFilter(cat)}
                      className={`px-2 py-1 rounded text-[10px] font-medium ${presetFilter === cat ? "bg-purple-600 text-white" : "bg-white/[0.04] text-gray-500 hover:text-gray-300"}`}
                    >
                      {cat === "all" ? "All" : cat.charAt(0).toUpperCase() + cat.slice(1)}
                    </button>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-4 gap-3">
                {presets
                  .filter((p) => presetFilter === "all" || p.category === presetFilter)
                  .slice(0, 8)
                  .map((preset) => (
                    <button
                      key={preset.id as string}
                      onClick={() => {
                        // Apply preset settings
                        const d = preset.defaults as Record<string, unknown> || {};
                        setSelectedModel((preset.model as string) || "sdxl-turbo");
                        if (d.steps) setSteps(d.steps as number);
                        if (d.cfg) setCfg(d.cfg as number);
                        if (d.width) setWidth(d.width as number);
                        if (d.height) setHeight(d.height as number);
                        if (preset.negative_prompt) setNegativePrompt(preset.negative_prompt as string);
                        if (preset.prompt_template) {
                          setPrompt((preset.prompt_template as string).replace(/\{[^}]+\}/g, ""));
                        }
                        setShowAdvanced(true);
                      }}
                      className="rounded-xl border border-white/[0.06] bg-[#12122a] p-3 text-left hover:border-purple-500/30 transition-all group"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-semibold text-white group-hover:text-purple-300">{preset.name as string}</span>
                        {Boolean(preset.badge) && (
                          <span className="rounded px-1 py-0.5 text-[8px] font-medium bg-purple-600/20 text-purple-400">
                            {String(preset.badge)}
                          </span>
                        )}
                      </div>
                      <p className="text-[10px] text-gray-500 line-clamp-2">{preset.description as string}</p>
                      <div className="flex items-center gap-2 mt-2">
                        <span className="text-[9px] text-gray-600">{preset.model as string}</span>
                        <span className={`text-[9px] px-1 py-0.5 rounded ${
                          workerVram && (preset.required_vram_gb as number) <= workerVram
                            ? "bg-green-500/10 text-green-400"
                            : (preset.required_vram_gb as number) <= 12
                              ? "bg-green-500/10 text-green-400"
                              : (preset.required_vram_gb as number) <= 32
                                ? "bg-amber-500/10 text-amber-400"
                                : "bg-red-500/10 text-red-400"
                        }`}>
                          {workerVram && (preset.required_vram_gb as number) <= workerVram ? "✓ " : ""}
                          {preset.required_vram_gb as number}GB
                        </span>
                      </div>
                    </button>
                  ))}
              </div>
            </div>
          )}

          {/* Generation Progress */}
          {generating && (
            <div className="rounded-xl border border-purple-500/30 bg-purple-500/5 p-6 text-center">
              <Loader2 className="h-8 w-8 animate-spin text-purple-500 mx-auto mb-3" />
              <p className="text-sm font-medium text-purple-300">Generating with {selectedModel}...</p>
              <p className="text-xs text-gray-500 mt-1">This usually takes 4-17 seconds depending on the model.</p>
            </div>
          )}

          {/* Result Display */}
          {result && !generating && (
            <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
              {result.error ? (
                <div className="text-center py-4">
                  <p className="text-sm text-red-400">{result.error}</p>
                  <p className="text-xs text-gray-600 mt-1">Make sure a GPU worker is running with the model loaded.</p>
                </div>
              ) : result.image_base64 ? (
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-white">Generated Image</h3>
                    <span className="text-xs text-gray-500">{result.generation_time}s • {result.filename}</span>
                  </div>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`data:image/png;base64,${result.image_base64}`}
                    alt="Generated content"
                    className="rounded-lg w-full max-w-lg mx-auto"
                  />
                  {result.saved_to && (
                    <div className="mt-3 flex items-center justify-center gap-2">
                      <span className="inline-flex items-center gap-1.5 rounded-lg bg-green-500/10 border border-green-500/20 px-3 py-1.5">
                        <svg className="h-3.5 w-3.5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                        <span className="text-[11px] text-green-400 font-medium">Saved</span>
                      </span>
                      {typeof window !== "undefined" && window.location.hostname === "localhost" && (
                        <button
                          onClick={() => {
                            // Open folder in Finder (calls backend endpoint)
                            fetch(`${API_BASE}/api/v1/generate/open-folder`, { method: "POST" }).catch(() => {});
                          }}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] px-3 py-1.5 text-[11px] text-gray-300 hover:text-white hover:bg-white/[0.08] transition-colors"
                        >
                          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z" /></svg>
                          Open Folder
                        </button>
                      )}
                    </div>
                  )}
                  {result.estimated_cost !== undefined && result.estimated_cost > 0 && (
                    <p className="text-[10px] text-gray-600 mt-2 text-center">
                      Cost: ${(result.estimated_cost as number).toFixed(5)}
                    </p>
                  )}
                </div>
              ) : null}
            </div>
          )}

          <h3 className="text-sm font-semibold text-white">Image Models</h3>
          <div className="grid grid-cols-3 gap-4">
            {imageModelList.map((model) => (
              <div key={model.id} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5 hover:border-purple-500/30 transition-all cursor-pointer">
                <div className="flex items-center gap-2 mb-2">
                  <ImageIcon className="h-5 w-5 text-purple-400" />
                  <h4 className="text-sm font-semibold text-white">{model.name}</h4>
                  {model.badge && (
                    <span className="rounded px-1.5 py-0.5 text-[10px] font-medium bg-purple-600/20 text-purple-400">
                      {model.badge}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500">{model.desc}</p>
                <p className="text-[10px] text-gray-600 mt-2">Requires: {model.vram} VRAM</p>
              </div>
            ))}
          </div>

          {/* Generation History Gallery */}
          {generationHistory.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-white mb-3">Recent Generations</h3>
              <div className="grid grid-cols-4 gap-3">
                {generationHistory.map((job, idx) => {
                  const input = (job.input as Record<string, unknown>) || {};
                  const jobPrompt = String(input.prompt || job.prompt || "");
                  return (
                    <button
                      key={(job.id as string) || idx}
                      onClick={() => {
                        if (jobPrompt) setPrompt(jobPrompt);
                        if (input.model) setSelectedModel(String(input.model));
                      }}
                      className="rounded-xl border border-white/[0.06] bg-[#12122a] p-3 text-left hover:border-purple-500/30 transition-all"
                    >
                      <div className="aspect-square rounded-lg bg-gradient-to-br from-purple-900/30 to-blue-900/30 mb-2 flex items-center justify-center">
                        <ImageIcon className="h-6 w-6 text-gray-700" />
                      </div>
                      <p className="text-[10px] text-gray-400 line-clamp-2">{jobPrompt.slice(0, 60) || "Generation"}</p>
                      <p className="text-[9px] text-gray-600 mt-1">{String(input.model || job.type || "")}</p>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Video Generation */}
      {activeTab === "video" && (
        <div className="space-y-6">
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
            <h3 className="text-sm font-semibold text-white mb-1">Video from Text</h3>
            <p className="text-xs text-gray-500 mb-4">Describe a scene — AI generates a 2-second video clip.</p>

            {/* Prompt + Model + Generate */}
            <div className="space-y-3">
              <div className="flex gap-3">
                <input
                  value={videoPrompt}
                  onChange={(e) => setVideoPrompt(e.target.value)}
                  className="flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 placeholder:text-gray-600 outline-none focus:border-purple-500/50"
                  placeholder="A woman walking through a luxury hotel lobby, cinematic..."
                />
                <select
                  value={selectedVideoModel}
                  onChange={(e) => setSelectedVideoModel(e.target.value)}
                  className="rounded-lg border border-white/[0.08] bg-[#12122a] px-3 py-2 text-sm text-gray-300 outline-none"
                >
                  {videoModelList.map((m) => (
                    <option key={m.id} value={m.id}>{m.name}{gpuReadyModels.has(m.id) ? "" : " (not loaded)"}</option>
                  ))}
                </select>
                <select
                  value={videoDuration}
                  onChange={(e) => setVideoDuration(e.target.value)}
                  className="rounded-lg border border-white/[0.08] bg-[#12122a] px-3 py-2 text-sm text-gray-300 outline-none"
                >
                  <option value="2">2 sec</option>
                  <option value="3">3 sec</option>
                  <option value="4">4 sec (max single clip)</option>
                </select>
                <button
                  onClick={handleGenerateVideo}
                  disabled={videoLoading || !videoPrompt.trim()}
                  className="rounded-lg bg-purple-600 px-6 py-2 text-sm font-medium text-white hover:bg-purple-700 flex items-center gap-2 disabled:opacity-50"
                >
                  {videoLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Film className="h-4 w-4" />}
                  {videoLoading ? "Generating..." : "Generate"}
                </button>
              </div>
            </div>

            {/* Video Loading State */}
            {videoLoading && (
              <div className="mt-4 rounded-xl border border-blue-500/30 bg-blue-500/5 p-6 text-center">
                <Loader2 className="h-8 w-8 animate-spin text-blue-500 mx-auto mb-3" />
                <p className="text-sm font-medium text-blue-300">Generating video with {selectedVideoModel}...</p>
                <p className="text-xs text-gray-500 mt-1">Video generation takes 5-50 minutes depending on length and quality.</p>
                <p className="text-[10px] text-gray-600 mt-2">Do not close this page. The video will appear below when ready.</p>
              </div>
            )}

            {/* Video Result Display */}
            {videoResult && !videoLoading && (
              <div className="mt-4 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                {videoResult.startsWith("Video generated") ? (
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <span className="inline-flex items-center gap-1.5 rounded-lg bg-green-500/10 border border-green-500/20 px-3 py-1.5">
                        <svg className="h-3.5 w-3.5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                        <span className="text-[11px] text-green-400 font-medium">Complete</span>
                      </span>
                      <p className="text-xs text-gray-400">{videoResult}</p>
                    </div>
                    {videoDownloadUrl && (
                      <div className="rounded-lg bg-black/30 p-2">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={videoDownloadUrl}
                          alt="Generated video"
                          className="rounded-lg w-full max-w-lg mx-auto"
                        />
                        <div className="mt-2 flex justify-center gap-2">
                          <a
                            href={videoDownloadUrl}
                            download
                            className="inline-flex items-center gap-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] px-3 py-1.5 text-[11px] text-gray-300 hover:text-white hover:bg-white/[0.08]"
                          >
                            Download Video
                          </a>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-amber-300">{videoResult}</p>
                )}
              </div>
            )}
          </div>

          <h3 className="text-sm font-semibold text-white">Video Models</h3>
          <div className="grid grid-cols-2 gap-4">
            {videoModelList.map((model) => (
              <div key={model.id} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5 hover:border-purple-500/30 transition-all cursor-pointer">
                <div className="flex items-center gap-2 mb-2">
                  <Film className="h-5 w-5 text-blue-400" />
                  <h4 className="text-sm font-semibold text-white">{model.name}</h4>
                  {model.badge && (
                    <span className="rounded px-1.5 py-0.5 text-[10px] font-medium bg-blue-600/20 text-blue-400">
                      {model.badge}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500">{model.desc}</p>
                <p className="text-[10px] text-gray-600 mt-2">Requires: {model.vram} VRAM</p>
              </div>
            ))}
          </div>

          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
            <h3 className="text-sm font-semibold text-white mb-1">Video from Image</h3>
            <p className="text-xs text-gray-500 mb-4">Upload or select an image to animate into video.</p>
            <input
              ref={videoImageInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleVideoImageSelect(file);
              }}
            />
            {/* Motion prompt */}
            <input
              value={videoMotionPrompt}
              onChange={(e) => setVideoMotionPrompt(e.target.value)}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-200 placeholder:text-gray-600 outline-none focus:border-purple-500/50 mb-3"
              placeholder="Describe the motion: slow zoom in, hair blowing in wind, walking forward..."
            />
            <div className="flex gap-3">
              <div
                onClick={() => videoImageInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleVideoImageDrop}
                className="flex-1 rounded-lg border-2 border-dashed border-white/[0.1] bg-white/[0.02] p-8 text-center cursor-pointer hover:border-purple-500/30"
              >
                {videoImagePreview ? (
                  <div className="space-y-2">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={videoImagePreview} alt="Video source image preview" className="mx-auto h-20 w-20 rounded-lg object-cover" />
                    <p className="text-xs text-gray-300">{videoImageFile?.name}</p>
                  </div>
                ) : (
                  <>
                    <ImageIcon className="h-8 w-8 text-gray-600 mx-auto mb-2" />
                    <p className="text-xs text-gray-500">Drop an image here or click to upload</p>
                  </>
                )}
              </div>
              <button
                onClick={handleAnimateImage}
                disabled={!videoImageFile || videoImageLoading}
                className="self-end rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 flex items-center gap-2 disabled:opacity-50"
              >
                {videoImageLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
                {videoImageLoading ? "Uploading..." : "Animate"}
              </button>
            </div>
            {videoImageResult && (
              <div className="mt-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                <p className="text-xs text-gray-300">{videoImageResult}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Voice & Music */}
      {activeTab === "audio" && (
        <div className="grid grid-cols-2 gap-6">
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
            <Mic className="h-8 w-8 text-green-400 mb-3" />
            <h3 className="text-lg font-semibold text-white">Voice Generation</h3>
            <p className="text-sm text-gray-500 mt-1">Generate speech from text with ElevenLabs or local XTTS.</p>
            <div className="mt-4 space-y-3">
              <textarea
                value={voiceText}
                onChange={(e) => setVoiceText(e.target.value)}
                className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 placeholder:text-gray-600 outline-none resize-none"
                rows={3}
                placeholder="Enter text to speak..."
              />
              <div className="flex gap-2">
                <select className="flex-1 rounded-lg border border-white/[0.08] bg-[#12122a] px-3 py-2 text-sm text-gray-300 outline-none">
                  <option>Rachel (ElevenLabs)</option>
                  <option>Custom Clone</option>
                  <option>XTTS Local</option>
                </select>
                <button
                  onClick={handleGenerateVoice}
                  disabled={voiceLoading || !voiceText.trim()}
                  className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 flex items-center gap-2 disabled:opacity-50"
                >
                  {voiceLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                  {voiceLoading ? "Generating..." : "Generate Speech"}
                </button>
              </div>
              {voiceResult && (
                <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                  <p className="text-xs text-gray-300">{voiceResult}</p>
                </div>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
            <Music className="h-8 w-8 text-amber-400 mb-3" />
            <h3 className="text-lg font-semibold text-white">Music Generation</h3>
            <p className="text-sm text-gray-500 mt-1">AI music for soundtracks, intros, and background.</p>
            <div className="mt-4 space-y-3">
              <input
                value={musicPrompt}
                onChange={(e) => setMusicPrompt(e.target.value)}
                className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 placeholder:text-gray-600 outline-none"
                placeholder="Describe the music: upbeat lo-fi for product reveal..."
              />
              <div className="flex gap-2">
                <select
                  value={musicDuration}
                  onChange={(e) => setMusicDuration(e.target.value)}
                  className="flex-1 rounded-lg border border-white/[0.08] bg-[#12122a] px-3 py-2 text-sm text-gray-300 outline-none"
                >
                  <option value="30">30 seconds</option>
                  <option value="60">60 seconds</option>
                  <option value="120">120 seconds</option>
                </select>
                <select
                  value={musicMood}
                  onChange={(e) => setMusicMood(e.target.value)}
                  className="flex-1 rounded-lg border border-white/[0.08] bg-[#12122a] px-3 py-2 text-sm text-gray-300 outline-none"
                >
                  <option value="cinematic">Cinematic</option>
                  <option value="lofi">Lo-Fi</option>
                  <option value="electronic">Electronic</option>
                  <option value="ambient">Ambient</option>
                </select>
                <button
                  onClick={handleGenerateMusic}
                  disabled={musicLoading || !musicPrompt.trim()}
                  className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 flex items-center gap-2 disabled:opacity-50"
                >
                  {musicLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                  {musicLoading ? "Generating..." : "Generate"}
                </button>
              </div>
              {musicResult && (
                <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                  <p className="text-xs text-gray-300">{musicResult}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Full Production */}
      {activeTab === "production" && (
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-8 text-center">
          <FileText className="h-12 w-12 text-pink-400 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-white">Full Production Pipeline</h3>
          <p className="text-sm text-gray-500 mt-2 max-w-md mx-auto">
            Create a complete production: storyboard → image generation → video → voice → music → export.
            Use the AI Brain to plan your production.
          </p>
          <Link href="/editor" className="mt-4 inline-flex items-center gap-2 rounded-lg bg-purple-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-purple-700">
            <Wand2 className="h-4 w-4" /> Open Video Editor
          </Link>
        </div>
      )}
    </div>
  );
}
