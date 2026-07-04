"use client";

import { useState } from "react";
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
                className="flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 placeholder:text-gray-600 outline-none focus:border-purple-500/50"
                placeholder="A woman walking through a luxury hotel lobby, cinematic..."
              />
              <button className="rounded-lg bg-purple-600 px-6 py-2 text-sm font-medium text-white hover:bg-purple-700 flex items-center gap-2">
                <Film className="h-4 w-4" /> Generate Video
              </button>
            </div>
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
            <div className="flex gap-3">
              <div className="flex-1 rounded-lg border-2 border-dashed border-white/[0.1] bg-white/[0.02] p-8 text-center cursor-pointer hover:border-purple-500/30">
                <Image className="h-8 w-8 text-gray-600 mx-auto mb-2" />
                <p className="text-xs text-gray-500">Drop an image here or click to upload</p>
              </div>
              <button className="self-end rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 flex items-center gap-2">
                <Wand2 className="h-4 w-4" /> Animate
              </button>
            </div>
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
                <button className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700">
                  Generate Speech
                </button>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
            <Music className="h-8 w-8 text-amber-400 mb-3" />
            <h3 className="text-lg font-semibold text-white">Music Generation</h3>
            <p className="text-sm text-gray-500 mt-1">AI music for soundtracks, intros, and background.</p>
            <div className="mt-4 space-y-3">
              <input
                className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 placeholder:text-gray-600 outline-none"
                placeholder="Describe the music: upbeat lo-fi for product reveal..."
              />
              <div className="flex gap-2">
                <select className="flex-1 rounded-lg border border-white/[0.08] bg-[#12122a] px-3 py-2 text-sm text-gray-300 outline-none">
                  <option>30 seconds</option>
                  <option>60 seconds</option>
                  <option>120 seconds</option>
                </select>
                <select className="flex-1 rounded-lg border border-white/[0.08] bg-[#12122a] px-3 py-2 text-sm text-gray-300 outline-none">
                  <option>Cinematic</option>
                  <option>Lo-Fi</option>
                  <option>Electronic</option>
                  <option>Ambient</option>
                </select>
                <button className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700">
                  Generate
                </button>
              </div>
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
          <Link href="/brain" className="mt-4 inline-flex items-center gap-2 rounded-lg bg-purple-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-purple-700">
            <Wand2 className="h-4 w-4" /> Plan with AI Brain
          </Link>
        </div>
      )}
    </div>
  );
}
