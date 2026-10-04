"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import {
  EpisodeList,
  RecoverableError,
  ShotDetails,
  StoryboardTimeline,
  WriteSkeleton,
  EmptyState,
} from "./_components";
import {
  type Episode,
  type Scene,
  type Shot,
  type UploadedReference,
  generateShotPreview,
  getApiError,
  listEpisodes,
  listScenes,
  listShots,
  listUniverses,
  updateShot,
} from "./contracts";

interface LoadError {
  message: string;
  requestId: string;
}

function errorState(reason: unknown): LoadError {
  return getApiError(reason);
}

export default function WritePage() {
  const router = useRouter();
  const { status } = useAuth();
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [selectedEpisode, setSelectedEpisode] = useState<Episode | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [shots, setShots] = useState<Shot[]>([]);
  const [selectedShot, setSelectedShot] = useState<Shot | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingEpisode, setLoadingEpisode] = useState(false);
  const [loadError, setLoadError] = useState<LoadError | null>(null);
  const [episodeError, setEpisodeError] = useState<LoadError | null>(null);

  const loadEpisode = useCallback(async (episode: Episode, preserveShotId?: string) => {
    setSelectedEpisode(episode);
    setLoadingEpisode(true);
    setEpisodeError(null);
    setScenes([]);
    setShots([]);
    setSelectedShot(null);
    try {
      const nextScenes = await listScenes(episode.id);
      const nextShots = (await Promise.all(nextScenes.map((scene) => listShots(scene.id)))).flat();
      setScenes(nextScenes);
      setShots(nextShots);
      setSelectedShot(nextShots.find((shot) => shot.id === preserveShotId) || nextShots[0] || null);
    } catch (reason) {
      setEpisodeError(errorState(reason));
    } finally {
      setLoadingEpisode(false);
    }
  }, []);

  const loadWorkspace = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const universes = await listUniverses();
      const universe = universes[0];
      if (!universe) {
        setEpisodes([]);
        setSelectedEpisode(null);
        return;
      }
      const nextEpisodes = await listEpisodes(universe.id);
      setEpisodes(nextEpisodes);
      if (nextEpisodes[0]) await loadEpisode(nextEpisodes[0]);
    } catch (reason) {
      setLoadError(errorState(reason));
    } finally {
      setLoading(false);
    }
  }, [loadEpisode]);

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace(`/login?redirect=${encodeURIComponent("/write")}`);
      return;
    }
    if (status === "authenticated" || status === "unconfigured") void loadWorkspace();
  }, [loadWorkspace, router, status]);

  const sceneById = useMemo(() => new Map(scenes.map((scene) => [scene.id, scene])), [scenes]);
  const selectedScene = selectedShot ? sceneById.get(selectedShot.scene_id) : undefined;
  const selectedIndex = selectedShot ? shots.findIndex((shot) => shot.id === selectedShot.id) : -1;
  const previousShot = selectedIndex > 0 ? shots[selectedIndex - 1] : undefined;

  function selectEpisode(episode: Episode) {
    void loadEpisode(episode);
  }

  function updateSelectedShot(nextShot: Shot) {
    setShots((current) => current.map((shot) => shot.id === nextShot.id ? { ...shot, ...nextShot } : shot));
    setSelectedShot((current) => current?.id === nextShot.id ? { ...current, ...nextShot } : current);
  }

  async function regenerate(prompt: string, frameGrid: 124 | 141 | 209 | 226 | 243 | 260 | 277 | 294 | 362 | 480 | 600, references: UploadedReference[], continuity: string) {
    if (!selectedShot) return;
    const newSeed = Math.floor(Math.random() * 2_147_483_646) + 1;
    const params: Record<string, unknown> = {
      ...(selectedShot.generation_params || {}),
      prompt,
      frame_grid: frameGrid,
      seed: newSeed,
      quality: "preview",
      steps: 4,
      height: 480,
    };
    const metadata = {
      ...(selectedShot.metadata || {}),
      references,
      continuity,
      preview_quality: true,
    };
    const persisted = await updateShot(selectedShot.id, {
      description: prompt,
      generation_params: params,
      metadata,
    });
    const nextShot = { ...selectedShot, ...persisted, description: prompt, generation_params: params, metadata };
    updateSelectedShot(nextShot);
    const result = await generateShotPreview(selectedShot.id, {
      prompt,
      negative_prompt: String(params.negative_prompt || ""),
      quality: "preview",
      steps: 4,
      height: 480,
      frame_grid: frameGrid,
      seed: newSeed,
      previous_shot_id: previousShot?.id,
      character_ids: selectedScene?.characters || [],
      location: selectedScene?.location,
      continuity,
      reference_asset_ids: references.map((reference) => reference.id),
      workflow_id: typeof params.workflow_id === "string" ? params.workflow_id : undefined,
      model_id: typeof params.model_id === "string" ? params.model_id : undefined,
    });
    updateSelectedShot({
      ...nextShot,
      job_id: result.job_id || result.generation_result?.job_id || nextShot.job_id,
      asset_id: result.asset_id || result.generation_result?.asset?.id || nextShot.asset_id,
      status: result.status || result.generation_result?.status || "queued",
      generation_params: { ...params, seed: result.seed || result.generation_result?.seed || newSeed },
    });
  }

  if (status === "loading" || loading) return <WriteSkeleton />;
  if (loadError) return <RecoverableError {...loadError} onRetry={() => void loadWorkspace()} />;
  if (episodes.length === 0) return <EmptyState title="No episodes to write yet" detail="Create an episode in the Story Engine before opening its storyboard. Your tenant context is supplied by the authenticated session." action={<button onClick={() => void loadWorkspace()} className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:border-violet-500 hover:text-violet-200"><RefreshCw className="h-3.5 w-3.5" /> Refresh episodes</button>} />;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2"><BookOpen className="h-5 w-5 text-violet-400" /><p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-violet-300">WRITE</p></div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-100">Story and storyboard</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">Shape the script, continuity, and preview frames. Full-quality rendering stays in MAKE.</p>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-slate-500"><span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 py-1 text-emerald-300">Authenticated workspace</span><button onClick={() => void loadWorkspace()} className="rounded-lg border border-slate-700 p-2 text-slate-400 hover:text-slate-200" aria-label="Refresh story"><RefreshCw className="h-3.5 w-3.5" /></button></div>
      </header>
      <div className="grid min-h-[620px] grid-cols-1 gap-4 xl:grid-cols-[220px_minmax(0,1fr)_360px] lg:grid-cols-[200px_minmax(0,1fr)]">
        <EpisodeList episodes={episodes} selectedId={selectedEpisode?.id} onSelect={selectEpisode} />
        <div className="min-w-0">
          {loadingEpisode ? <WriteSkeleton /> : episodeError ? <RecoverableError {...episodeError} onRetry={() => selectedEpisode && void loadEpisode(selectedEpisode, selectedShot?.id)} /> : <StoryboardTimeline scenes={scenes} shots={shots} selectedId={selectedShot?.id} onSelect={setSelectedShot} />}
        </div>
        <div className="lg:col-span-2 xl:col-span-1">
          {selectedShot ? <ShotDetails key={selectedShot.id} shot={selectedShot} scene={selectedScene} previousShot={previousShot} onUpdate={updateSelectedShot} onRegenerate={regenerate} /> : <EmptyState title="Select a shot" detail="Choose a frame in the storyboard timeline to edit its six-section prompt and continuity context." />}
        </div>
      </div>
      {status === "unconfigured" && <p className="text-[10px] text-amber-300/80">Supabase is not configured in this build. API requests still use the canonical transport and will redirect to sign in when the backend requires a session.</p>}
    </div>
  );
}
