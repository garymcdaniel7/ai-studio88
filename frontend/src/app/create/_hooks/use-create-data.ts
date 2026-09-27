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
  capabilities?: string[];
  ready?: boolean;
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
  const [imageModelList, setImageModelList] = useState<ModelOption[]>([]);
  const [videoModelList, setVideoModelList] = useState<ModelOption[]>([]);
  const [availableLoras, setAvailableLoras] = useState<LoraOption[]>([]);
  const [presets, setPresets] = useState<Record<string, unknown>[]>([]);
  const [gpuReadyModels, setGpuReadyModels] = useState<Set<string>>(new Set());
  const [gpuOnline, setGpuOnline] = useState<boolean | null>(null); // null = unknown, true = online, false = offline
  const [workerVram, setWorkerVram] = useState<number | null>(null);
  const [generationHistory, setGenerationHistory] = useState<Record<string, unknown>[]>([]);
  const [talentList, setTalentList] = useState<TalentOption[]>([]);
  const [projectList, setProjectList] = useState<{ id: string; name: string }[]>([]);
  const [elevenlabsVoices, setElevenlabsVoices] = useState<VoiceOption[]>([]);
  const [mossVoices, setMossVoices] = useState<MossVoiceOption[]>([]);

  useEffect(() => {
    // PRIMARY source: available-models (real production models on GPU)
    authFetch(`${API_BASE}/api/v1/generation/available-models`)
      .then((r) => r.json())
      .then((data) => {
        if (data?.models && Array.isArray(data.models)) {
          const models = data.models as Array<{
            id: string;
            name?: string;
            description?: string;
            capabilities?: string[];
            vram?: number;
            ready?: boolean;
          }>;

          // Split by capability
          const imageModels = models
            .filter((m) => (m.capabilities || []).some((c) => ["txt2img", "img2img"].includes(c)))
            .map((m) => ({
              id: m.id,
              name: m.name || m.id,
              desc: m.description || "",
              vram: m.vram ? `${m.vram}GB` : "",
              badge: m.ready ? "Loaded" : "",
              capabilities: m.capabilities,
              ready: m.ready,
            }));

          const videoModels = models
            .filter((m) => (m.capabilities || []).some((c) => ["txt2video", "img2video"].includes(c)))
            .map((m) => ({
              id: m.id,
              name: m.name || m.id,
              desc: m.description || "",
              vram: m.vram ? `${m.vram}GB` : "",
              badge: m.ready ? "Loaded" : "",
              capabilities: m.capabilities,
              ready: m.ready,
            }));

          // Reorder image models: quality-first (SD3.5 / FLUX Dev before Turbo / Klein)
          const imagePriority = ["flux2-dev", "flux-dev", "sd35", "sdxl-turbo", "sd15", "flux2-klein"];
          imageModels.sort((a, b) => {
            const ai = imagePriority.indexOf(a.id);
            const bi = imagePriority.indexOf(b.id);
            if (ai === -1 && bi === -1) return 0;
            if (ai === -1) return 1;
            if (bi === -1) return -1;
            return ai - bi;
          });

          if (imageModels.length > 0) setImageModelList(imageModels);
          if (videoModels.length > 0) setVideoModelList(videoModels);

          // GPU readiness + auto-select first ready model
          const ready = new Set<string>(models.filter((m) => m.ready).map((m) => m.id));
          setGpuReadyModels(ready);
          setGpuOnline(ready.size > 0);
          if (ready.size > 0 && !ready.has(selectedModel)) {
            const firstReady = models.find((m) => m.ready);
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

    // SECONDARY: model registry for supplemental info (B2 status badges)
    authFetch(`${API_BASE}/api/v1/models`)
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          const active = data.filter((m: Record<string, unknown>) => m.status !== "archived");
          const seen = new Set<string>();
          const deduped = active.filter((m: Record<string, unknown>) => {
            const name = String(m.name || "");
            if (seen.has(name)) return false;
            seen.add(name);
            return true;
          });

          // Enrich existing model lists with B2 badge if model is B2-only
          setImageModelList((prev) =>
            prev.map((m) => {
              const reg = deduped.find(
                (r: Record<string, unknown>) => String(r.id || r.name) === m.id
              );
              const status = reg ? String((reg as Record<string, unknown>).status || "") : "";
              if (status === "available_b2_only" && !m.ready) {
                return { ...m, badge: "B2" };
              }
              return m;
            })
          );
          setVideoModelList((prev) =>
            prev.map((m) => {
              const reg = deduped.find(
                (r: Record<string, unknown>) => String(r.id || r.name) === m.id
              );
              const status = reg ? String((reg as Record<string, unknown>).status || "") : "";
              if (status === "available_b2_only" && !m.ready) {
                return { ...m, badge: "B2" };
              }
              return m;
            })
          );
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
