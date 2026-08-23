"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ModelOption {
  id: string;
  name: string;
  desc: string;
  vram: string;
  badge: string;
}

export interface LoraOption {
  id: string;
  name: string;
  trigger_words?: string;
  strength?: number;
}

export interface TalentOption {
  id: string;
  name: string;
  avatar_url?: string;
  trigger_words?: string;
  visual_style?: string;
}

export interface VoiceOption {
  voice_id: string;
  name: string;
  preview_url?: string;
  labels?: Record<string, string>;
}

export interface MossVoiceOption {
  id: string;
  name: string;
  provider: string;
  talent_id?: string;
}

/**
 * Mount-time catalog bootstrap for the Create page.
 * Loads model registry, LoRAs, preset packs, GPU readiness, job history,
 * worker VRAM, talents, projects, and voice catalogs.
 */
export function useCreateData({
  selectedModel,
  setSelectedModel,
}: {
  selectedModel: string;
  setSelectedModel: (id: string) => void;
}) {
  const [imageModelList, setImageModelList] = useState<ModelOption[]>([
    { id: "flux2-dev", name: "Flux 2 Dev", desc: "Best quality — 32B params, portraits, editorial", vram: "24GB+", badge: "Quality" },
    { id: "flux2-klein", name: "Flux 2 Klein", desc: "Fast + great quality — 4B params, 4 steps", vram: "12GB", badge: "Fast" },
  ]);
  const [videoModelList, setVideoModelList] = useState<ModelOption[]>([
    { id: "wan-2.1-t2v", name: "WAN 2.1 (Text-to-Video)", desc: "Best video — 2-6s clips at 24fps", vram: "24GB+", badge: "Quality" },
    { id: "wan-2.1-i2v", name: "WAN 2.1 (Image-to-Video)", desc: "Animate any image into video", vram: "24GB+", badge: "" },
  ]);
  const [availableLoras, setAvailableLoras] = useState<LoraOption[]>([]);
  const [presets, setPresets] = useState<Record<string, unknown>[]>([]);
  const [gpuReadyModels, setGpuReadyModels] = useState<Set<string>>(new Set(["sdxl-turbo", "flux2-klein"]));
  const [gpuOnline, setGpuOnline] = useState<boolean | null>(null); // null = unknown, true = online, false = offline
  const [workerVram, setWorkerVram] = useState<number | null>(null);
  const [generationHistory, setGenerationHistory] = useState<Record<string, unknown>[]>([]);
  const [talentList, setTalentList] = useState<TalentOption[]>([]);
  const [projectList, setProjectList] = useState<{ id: string; name: string }[]>([]);
  const [elevenlabsVoices, setElevenlabsVoices] = useState<VoiceOption[]>([]);
  const [mossVoices, setMossVoices] = useState<MossVoiceOption[]>([]);

  useEffect(() => {
    // Primary source: model registry (all models in B2 + their metadata)
    authFetch(`${API_BASE}/api/v1/models`)
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          // Filter out archived models and deduplicate by name
          const active = data.filter((m: Record<string, unknown>) => m.status !== "archived");
          const seen = new Set<string>();
          const deduped = active.filter((m: Record<string, unknown>) => {
            const name = String(m.name || "");
            if (seen.has(name)) return false;
            seen.add(name);
            return true;
          });

          // Split into image and video models based on type and supported_tasks
          const imageModels = deduped.filter((m: Record<string, unknown>) => {
            const type = String(m.type || "");
            const tasks = (m.supported_tasks as string[]) || [];
            return type === "checkpoint" && (
              tasks.includes("txt2img") || tasks.includes("img2img") || tasks.length === 0
            ) && !tasks.includes("txt2video");
          });
          const videoModels = deduped.filter((m: Record<string, unknown>) => {
            const tasks = (m.supported_tasks as string[]) || [];
            return tasks.includes("txt2video") || tasks.includes("img2video");
          });

          if (imageModels.length > 0) {
            setImageModelList(imageModels.map((m: Record<string, unknown>) => {
              const status = String(m.status || "available");
              const isLoaded = status === "available";
              const isB2Only = status === "available_b2_only";
              const vramGb = m.required_vram_gb ? `${m.required_vram_gb}GB` : "";
              return {
                id: String(m.id || m.name),
                name: String(m.name || ""),
                desc: `${String(m.family || "").toUpperCase()} • ${vramGb} VRAM`,
                vram: vramGb,
                badge: isLoaded ? "Loaded" : isB2Only ? "B2" : "",
              };
            }));
          }
          if (videoModels.length > 0) {
            setVideoModelList(videoModels.map((m: Record<string, unknown>) => {
              const status = String(m.status || "available");
              const isLoaded = status === "available";
              const vramGb = m.required_vram_gb ? `${m.required_vram_gb}GB` : "";
              return {
                id: String(m.id || m.name),
                name: String(m.name || ""),
                desc: `${String(m.family || "").toUpperCase()} • ${vramGb} VRAM`,
                vram: vramGb,
                badge: isLoaded ? "Loaded" : "B2",
              };
            }));
          }
        }
      })
      .catch(() => {});

    // Fetch available LoRAs
    authFetch(`${API_BASE}/api/v1/models?type=lora`)
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
    authFetch(`${API_BASE}/api/v1/presets`)
      .then((r) => r.json())
      .then((data) => { if (Array.isArray(data)) setPresets(data); })
      .catch(() => {});

    // Fetch which models are actually loaded on the GPU
    authFetch(`${API_BASE}/api/v1/generate/available-models`)
      .then((r) => r.json())
      .then((data) => {
        if (data?.models) {
          const allModels = data.models as { id: string; name: string; ready: boolean; vram?: string; badge?: string }[];
          const ready = new Set<string>(allModels.filter((m) => m.ready).map((m) => m.id));
          setGpuReadyModels(ready);
          setGpuOnline(true);
          // Auto-select first available model if current selection isn't loaded
          if (ready.size > 0 && !ready.has(selectedModel)) {
            const firstReady = allModels.find((m) => m.ready);
            if (firstReady) setSelectedModel(firstReady.id);
          }
        } else {
          setGpuOnline(false);
        }
      })
      .catch(() => {
        setGpuOnline(false);
        setGpuReadyModels(new Set());
      });

    // Fetch generation history (recent completed jobs with outputs)
    authFetch(`${API_BASE}/api/v1/jobs?status=completed`)
      .then((r) => r.json())
      .then((data) => { if (Array.isArray(data)) setGenerationHistory(data.slice(0, 12)); })
      .catch(() => {});

    // Fetch worker VRAM for GPU compatibility badges
    authFetch(`${API_BASE}/api/v1/infrastructure/status`)
      .then((r) => r.json())
      .then((data) => {
        const vram = (data as Record<string, Record<string, unknown>>)?.worker?.gpu_vram_gb;
        if (typeof vram === "number") setWorkerVram(vram);
      })
      .catch(() => {});

    // Fetch talent list for injection
    authFetch(`${API_BASE}/api/v1/talent`)
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) setTalentList(data.map((t: Record<string, unknown>) => ({ id: String(t.id), name: String(t.name), avatar_url: t.avatar_url ? String(t.avatar_url) : undefined, trigger_words: t.trigger_words ? String(t.trigger_words) : undefined, visual_style: t.visual_style ? String(t.visual_style) : undefined })));
      })
      .catch(() => {});

    // Fetch projects for project selector
    authFetch(`${API_BASE}/api/v1/projects`)
      .then((r) => r.json())
      .then((data) => {
        const projects = data?.projects || (Array.isArray(data) ? data : []);
        setProjectList(projects.filter((p: Record<string, unknown>) => p.status === "active").map((p: Record<string, unknown>) => ({ id: String(p.id), name: String(p.name) })));
      })
      .catch(() => {});

    // Fetch ElevenLabs voices for voice tab
    fetch(`${API_BASE}/api/v1/voices/elevenlabs`)
      .then((r) => r.json())
      .then((data) => {
        if (data?.voices) setElevenlabsVoices(data.voices.map((v: Record<string, unknown>) => ({ voice_id: String(v.voice_id), name: String(v.name), preview_url: v.preview_url ? String(v.preview_url) : undefined, labels: (v.labels || {}) as Record<string, string> })));
      })
      .catch(() => {});

    // Fetch saved MOSS/talent voices
    fetch(`${API_BASE}/api/v1/voices/moss`)
      .then((r) => r.json())
      .then((data) => {
        if (data?.voices) setMossVoices(data.voices.map((v: Record<string, unknown>) => ({ id: String(v.id || v.provider_voice_id), name: String(v.name), provider: String(v.provider || "moss-tts"), talent_id: v.talent_id ? String(v.talent_id) : undefined })));
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    imageModelList,
    videoModelList,
    availableLoras,
    presets,
    gpuReadyModels,
    gpuOnline,
    workerVram,
    generationHistory,
    talentList,
    projectList,
    elevenlabsVoices,
    mossVoices,
  };
}
