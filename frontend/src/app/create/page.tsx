"use client";

import { useState, useRef } from "react";
import Link from "next/link";
import { Image, Film, Music, Mic, FileText, Sparkles, Wand2, Loader2 } from "lucide-react";

const imageModels = [
  { id: "flux-dev", name: "Flux Dev", desc: "Highest quality, 1024x1024, 20 steps", vram: "32GB", badge: "Best" },
  { id: "sdxl-turbo", name: "SDXL Turbo", desc: "Fastest, 512x512, 1 step", vram: "8GB", badge: "Fast" },
  { id: "sd15", name: "SD 1.5", desc: "Classic, versatile, 512x512", vram: "6GB", badge: "" },
];

const videoModels = [
  { id: "wan-2.1-t2v", name: "WAN 2.1 (Text-to-Video)", desc: "14B parameter, 2s clips at 24fps", vram: "80GB+", badge: "New" },
  { id: "wan-2.1-i2v", name: "WAN 2.1 (Image-to-Video)", desc: "Animate any image into video", vram: "80GB+", badge: "" },
];

export default function CreatePage() {
  const [activeTab, setActiveTab] = useState<"image" | "video" | "audio" | "production">("image");
  const [prompt, setPrompt] = useState("");
  const [selectedModel, setSelectedModel] = useState("sdxl-turbo");
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<{image_base64?: string; filename?: string; generation_time?: number; error?: string} | null>(null);

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

  // Video from Image state
  const [videoImageFile, setVideoImageFile] = useState<File | null>(null);
  const [videoImagePreview, setVideoImagePreview] = useState<string | null>(null);
  const [videoImageLoading, setVideoImageLoading] = useState(false);
  const [videoImageResult, setVideoImageResult] = useState<string | null>(null);
  const videoImageInputRef = useRef<HTMLInputElement>(null);

  async function handleGenerateVoice() {
    if (!voiceText.trim() || voiceLoading) return;
    setVoiceLoading(true);
    setVoiceResult(null);
    try {
      const resp = await fetch("http://localhost:8000/api/v1/voice/generate-tts", {
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
      const resp = await fetch("http://localhost:8000/api/v1/audio/music/generate", {
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
    try {
      const resp = await fetch("http://localhost:8000/api/v1/videos/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: videoPrompt, model_id: "wan-2.1-t2v" }),
      });
      const data = await resp.json();
      setVideoResult(data.video_url || data.message || "Video generation started");
    } catch {
      setVideoResult("Failed to generate video. Is the backend running?");
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
      const formData = new FormData();
      formData.append("file", videoImageFile);
      const resp = await fetch("http://localhost:8000/api/v1/assets", {
        method: "POST",
        body: formData,
      });
      const data = await resp.json();
      setVideoImageResult(data.message || data.filename || "Image uploaded successfully — animation queued.");
    } catch {
      setVideoImageResult("Failed to upload. Is the backend running?");
    } finally {
      setVideoImageLoading(false);
    }
  }

  async function handleGenerate() {
    if (!prompt.trim() || generating) return;
    setGenerating(true);
    setResult(null);

    try {
      const resp = await fetch("http://localhost:8000/api/v1/generate/image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, model: selectedModel }),
      });
      const data = await resp.json();
      if (data.success) {
        setResult(data);
      } else {
        setResult({ error: data.detail || "Generation failed" });
      }
    } catch (e: any) {
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
          { key: "image", label: "Image Generation", icon: Image },
          { key: "video", label: "Video Generation", icon: Film },
          { key: "audio", label: "Voice & Music", icon: Mic },
          { key: "production", label: "Full Production", icon: FileText },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key as any)}
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
            <div className="flex gap-3">
              <input
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleGenerate(); }}
                className="flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 placeholder:text-gray-600 outline-none focus:border-purple-500/50"
                placeholder="A luxury penthouse at sunset, photorealistic..."
              />
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="rounded-lg border border-white/[0.08] bg-[#12122a] px-3 py-2 text-sm text-gray-300 outline-none"
              >
                {imageModels.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
              <button
                onClick={handleGenerate}
                disabled={generating || !prompt.trim()}
                className="rounded-lg bg-purple-600 px-6 py-2 text-sm font-medium text-white hover:bg-purple-700 flex items-center gap-2 disabled:opacity-50"
              >
                {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {generating ? "Generating..." : "Generate"}
              </button>
            </div>
          </div>

          {/* Result Display */}
          {result && (
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
                  <img
                    src={`data:image/png;base64,${result.image_base64}`}
                    alt="Generated"
                    className="rounded-lg w-full max-w-lg mx-auto"
                  />
                </div>
              ) : null}
            </div>
          )}

          <h3 className="text-sm font-semibold text-white">Image Models</h3>
          <div className="grid grid-cols-3 gap-4">
            {imageModels.map((model) => (
              <div key={model.id} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5 hover:border-purple-500/30 transition-all cursor-pointer">
                <div className="flex items-center gap-2 mb-2">
                  <Image className="h-5 w-5 text-purple-400" />
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
        </div>
      )}

      {/* Video Generation */}
      {activeTab === "video" && (
        <div className="space-y-6">
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
            <h3 className="text-sm font-semibold text-white mb-1">Video from Text</h3>
            <p className="text-xs text-gray-500 mb-4">Describe a scene — AI generates a video clip.</p>
            <div className="flex gap-3">
              <input
                value={videoPrompt}
                onChange={(e) => setVideoPrompt(e.target.value)}
                className="flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 placeholder:text-gray-600 outline-none focus:border-purple-500/50"
                placeholder="A woman walking through a luxury hotel lobby, cinematic..."
              />
              <button
                onClick={handleGenerateVideo}
                disabled={videoLoading || !videoPrompt.trim()}
                className="rounded-lg bg-purple-600 px-6 py-2 text-sm font-medium text-white hover:bg-purple-700 flex items-center gap-2 disabled:opacity-50"
              >
                {videoLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Film className="h-4 w-4" />}
                {videoLoading ? "Generating..." : "Generate Video"}
              </button>
            </div>
            {videoResult && (
              <div className="mt-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                <p className="text-xs text-gray-300">{videoResult}</p>
              </div>
            )}
          </div>

          <h3 className="text-sm font-semibold text-white">Video Models</h3>
          <div className="grid grid-cols-2 gap-4">
            {videoModels.map((model) => (
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
            <div className="flex gap-3">
              <div
                onClick={() => videoImageInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleVideoImageDrop}
                className="flex-1 rounded-lg border-2 border-dashed border-white/[0.1] bg-white/[0.02] p-8 text-center cursor-pointer hover:border-purple-500/30"
              >
                {videoImagePreview ? (
                  <div className="space-y-2">
                    <img src={videoImagePreview} alt="Preview" className="mx-auto h-20 w-20 rounded-lg object-cover" />
                    <p className="text-xs text-gray-300">{videoImageFile?.name}</p>
                  </div>
                ) : (
                  <>
                    <Image className="h-8 w-8 text-gray-600 mx-auto mb-2" />
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
