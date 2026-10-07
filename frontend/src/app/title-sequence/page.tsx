"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  ArrowRight,
  ChevronRight,
  Circle,
  Clapperboard,
  Clock3,
  FileCheck2,
  Loader2,
  LockKeyhole,
  MoreHorizontal,
  PackageCheck,
  Play,
  ShieldCheck,
  Sparkles,
  UserRound,
} from "lucide-react";

/* ── Types ─────────────────────────────────────────────────────── */

interface Scene {
  id: string;
  scene_number: number;
  title: string;
  purpose: string;
  camera_style: string;
  mood: string;
  desired_emotion: string;
  location?: string;
  time_of_day?: string;
  characters?: string;
  music?: string;
  updated_at?: string;
}

interface Episode {
  id: string;
  title: string;
  description: string;
  episode_number: number;
  status: string;
  universe_id: string;
  updated_at?: string;
}

interface TalentIdentity {
  id: string;
  name: string;
  ethnicity?: string;
  hair_color?: string;
  eye_color?: string;
  body_type?: string;
  gender?: string;
  age?: number;
  height?: string;
  avatar_url?: string;
  media?: Array<{ url: string; type: string }>;
}

/* ── Components ─────────────────────────────────────────────────── */

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-content-muted">{children}</p>;
}

function ReferenceFrame({ label, detail, accent, imageUrl }: { label: string; detail: string; accent: string; imageUrl?: string | null }) {
  return (
    <div className="group relative overflow-hidden rounded-xl border border-border-subtle bg-[#0b0b18]">
      <div className={`relative aspect-[4/3] overflow-hidden ${imageUrl ? '' : `bg-gradient-to-br ${accent}`}`}>
        {imageUrl ? (
          <img src={imageUrl} alt={label} className="h-full w-full object-cover" />
        ) : (
          <>
            <div className="absolute inset-0 opacity-70 [background-image:radial-gradient(circle_at_68%_30%,rgba(251,191,36,.35),transparent_23%),linear-gradient(125deg,transparent_46%,rgba(255,255,255,.08)_47%,transparent_48%)]" />
            <div className="absolute bottom-4 left-4 h-20 w-20 rounded-full border border-amber-300/30 bg-black/30 shadow-[0_0_35px_rgba(245,158,11,.18)]" />
          </>
        )}
        <span className="absolute left-3 top-3 rounded-md border border-white/10 bg-black/30 px-2 py-1 text-[9px] font-medium uppercase tracking-widest text-white/70">
          {imageUrl ? "Rendered still" : "Canon reference"}
        </span>
        <span className="absolute bottom-3 right-3 rounded-full bg-black/40 px-2 py-1 text-[9px] text-white/70">{label}</span>
      </div>
      <div className="p-3"><p className="text-xs font-semibold text-content-primary">{label}</p><p className="mt-1 text-[11px] leading-4 text-content-muted">{detail}</p></div>
    </div>
  );
}

function buildIdentitySubject(talent: TalentIdentity | null): string {
  if (!talent) return "";
  const parts: string[] = [];
  const gender = talent.gender?.toLowerCase() || "person";
  parts.push(talent.ethnicity ? `${talent.ethnicity} ${gender}` : gender);
  if (talent.hair_color) parts.push(`${talent.hair_color} hair`);
  if (talent.eye_color) parts.push(`${talent.eye_color} eyes`);
  if (talent.height) parts.push(`${talent.height} tall`);
  if (talent.body_type) parts.push(talent.body_type.toLowerCase());
  return parts.join(", ");
}

function getPromptSections(scene: Scene, identitySubject: string) {
  const subject = identitySubject || "Deep dark-brown / Black man with tightly coiled high-volume afro, gold scar on left cheek, glowing amber left eye, wearing black + gold armor and cape";
  return {
    subject,
    action: scene.purpose || scene.title,
    camera: scene.camera_style || "medium close-up, eye-level, shallow depth of field",
    lighting: scene.mood === "mysterious" ? "near-black with single gold edge light" : "soft key light with amber rim light, controlled shadows",
    extra: scene.desired_emotion ? `emotion: ${scene.desired_emotion}` : undefined,
  };
}

const FALLBACK_LOCKS = [
  { label: "Complexion", value: "Deep dark-brown / Black", tone: "amber" as const },
  { label: "Hair", value: "Tightly coiled, high-volume afro", tone: "violet" as const },
  { label: "Signature mark", value: "Gold scar on left cheek", tone: "rose" as const },
  { label: "Eye treatment", value: "Glowing amber left eye", tone: "cyan" as const },
  { label: "Wardrobe", value: "Black + gold armor and cape", tone: "slate" as const },
];

/* ── Page ───────────────────────────────────────────────────────── */

export default function TitleSequencePage() {
  const [queuing, setQueuing] = useState(false);
  const [queueMessage, setQueueMessage] = useState<string | null>(null);
  const [refImageId] = useState<string | null>(null);
  const [talent, setTalent] = useState<TalentIdentity | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [episode, setEpisode] = useState<Episode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        // 1. Load talent data for identity constraints
        const talentData = await api.get<{ items?: TalentIdentity[]; total?: number }>("/api/v1/talent?limit=10");
        if (talentData?.items) {
          const found = talentData.items.find((t) => t.name.toLowerCase().includes("obsidian")) || talentData.items[0];
          if (found) setTalent(found);
        }

        // 2. Find Obsidian universe
        const universeData = await api.get<{ id: string; name: string }[]>("/api/v1/universes?name=eq.Obsidian&limit=1");
        if (!Array.isArray(universeData) || universeData.length === 0) {
          setError("Obsidian universe not found — create one via Story engine first.");
          setLoading(false);
          return;
        }
        const universe = universeData[0];

        // 3. Get episodes, find Title Sequence
        const episodes = await api.get<Episode[]>(`/api/v1/universes/${universe.id}/episodes`);
        const titleSeq = Array.isArray(episodes)
          ? episodes.find((e) => e.title.toLowerCase().includes("title"))
          : null;

        if (!titleSeq) {
          setError("No Title Sequence episode found — create one via Story engine.");
          setLoading(false);
          return;
        }

        setEpisode(titleSeq);

        // 4. Fetch scenes (beats)
        const beats = await api.get<Scene[]>(`/api/v1/episodes/${titleSeq.id}/scenes`);
        if (Array.isArray(beats)) {
          setScenes(beats.sort((a, b) => a.scene_number - b.scene_number));
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load sequence data");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const identitySubject = buildIdentitySubject(talent);

  const identityLocks = talent
    ? [
        ...(talent.ethnicity ? [{ label: "Complexion", value: talent.ethnicity, tone: "amber" as const }] : []),
        ...(talent.hair_color ? [{ label: "Hair", value: talent.hair_color, tone: "violet" as const }] : []),
        ...(talent.eye_color ? [{ label: "Eye color", value: talent.eye_color, tone: "cyan" as const }] : []),
        ...(talent.body_type ? [{ label: "Build", value: talent.body_type, tone: "slate" as const }] : []),
        ...(talent.gender ? [{ label: "Gender", value: talent.gender, tone: "rose" as const }] : []),
      ]
    : FALLBACK_LOCKS;

  const faceImage = talent?.media?.find((m) => m.type === "face" || m.type === "portrait")?.url || talent?.avatar_url || null;

  async function queueAllBeats() {
    if (!episode || scenes.length === 0) return;
    setQueuing(true);
    setQueueMessage("Queuing all beats as Motion Director chain…");
    try {
      const result = await api.post<{
        chain_id: string;
        status: "queued" | "pending_approval";
        total_estimated_cost_usd: number;
        jobs: Array<{ beat_index: number; job_id: string }>;
        approval_url: string | null;
      }>("/api/v1/generate/chain", {
        idempotency_key: `title-seq-${episode.id}-${Date.now()}`,
        label: `Title Sequence — ${episode.title}`,
        pipeline: "motion-director-h3",
        beats: scenes.map((scene, index) => ({
          beat_index: index,
          model_ref: "model-krea2-nsfw",
          task_type: "i2v",
          prompt_sections: getPromptSections(scene, identitySubject),
          ref_image_id: index === 0 ? refImageId : null,
          frame_count: 243,
          frame_rate: 24,
          pipeline_config: { anti_plastic: true },
        })),
      });
      if (result.status === "pending_approval") {
        setQueueMessage(`Pending approval. Est. $${result.total_estimated_cost_usd.toFixed(3)}`);
      } else {
        setQueueMessage(`Queued! Chain: ${result.chain_id.slice(0, 12)} — ${result.jobs.length} jobs`);
      }
    } catch (err) {
      setQueueMessage(err instanceof Error ? `Failed: ${err.message}` : "Failed.");
    } finally {
      setQueuing(false);
    }
  }

  /* ── Loading ──────────────────────────────────────────────────── */

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="h-8 w-8 animate-spin text-purple-400" />
      </div>
    );
  }

  /* ── Error (no universe / no episode) ─────────────────────────── */

  if (error) {
    return (
      <div className="mx-auto max-w-xl py-32 text-center">
        <p className="text-lg font-semibold text-status-error">{error}</p>
        <Link href="/projects" className="mt-4 inline-block text-sm text-amber-300 hover:text-amber-200">← Back to Projects</Link>
      </div>
    );
  }

  /* ── Loaded ───────────────────────────────────────────────────── */

  return (
    <div className="mx-auto max-w-[1440px] space-y-6 pb-10">

      {/* Breadcrumb */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-xs text-content-muted">
          <Link href="/title-sequence" className="hover:text-content-primary">Title Sequences</Link>
          <ChevronRight className="h-3.5 w-3.5" />
          <span className="text-content-secondary">{episode?.title || "Sequence"}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider ${
            episode?.status === "completed"
              ? "border border-green-400/20 bg-green-400/10 text-green-300"
              : "border border-amber-400/20 bg-amber-400/10 text-amber-300"
          }`}>
            {episode?.status || "Draft"}
          </span>
          <button
            type="button"
            onClick={() => setQueueMessage("Export options coming soon.")}
            className="rounded-lg border border-border-default p-2 text-content-muted hover:bg-surface-hover"
            aria-label="More actions"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Header */}
      <header className="relative overflow-hidden rounded-2xl border border-amber-400/15 bg-gradient-to-br from-[#181524] via-[#111122] to-[#0b0b18] p-7 shadow-2xl">
        <div className="absolute -right-20 -top-32 h-80 w-80 rounded-full bg-amber-500/10 blur-3xl" />
        <div className="relative flex flex-col justify-between gap-8 lg:flex-row lg:items-end">
          <div className="max-w-2xl">
            <div className="mb-4 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-300">
              <Sparkles className="h-3.5 w-3.5" /> {episode?.title || "Obsidian"} / {scenes.length} beats
            </div>
            <h1 className="font-serif text-5xl tracking-[0.16em] text-white sm:text-7xl">{episode?.title || "OBSIDIAN"}</h1>
            <p className="mt-4 max-w-xl text-sm leading-6 text-content-secondary">
              {episode?.description || "Title sequence designed against the Obsidian canon."}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-x-8 gap-y-4 text-right sm:grid-cols-4 lg:min-w-[480px]">
            <div><p className="text-[10px] uppercase tracking-wider text-content-muted">Status</p><p className="mt-1 text-sm font-semibold text-amber-300">{episode?.status === "completed" ? "Complete" : "In progress"}</p></div>
            <div><p className="text-[10px] uppercase tracking-wider text-content-muted">Beats</p><p className="mt-1 text-sm font-semibold text-content-primary">{scenes.length}</p></div>
            <div><p className="text-[10px] uppercase tracking-wider text-content-muted">Updated</p><p className="mt-1 text-sm font-semibold text-content-primary">{episode?.updated_at ? new Date(episode.updated_at).toLocaleDateString() : "Today"}</p></div>
            <div><p className="text-[10px] uppercase tracking-wider text-content-muted">Version</p><p className="mt-1 text-sm font-semibold text-content-primary">Live</p></div>
          </div>
        </div>
      </header>

      {/* Main layout */}
      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <main className="space-y-6">

          {/* Identity Reference Plan */}
          <section className="rounded-2xl border border-border-subtle bg-surface-raised p-5">
            <div className="flex items-center justify-between">
              <SectionLabel>Identity reference plan</SectionLabel>
              <span className="flex items-center gap-1 text-[10px] text-amber-300">
                <ShieldCheck className="h-3.5 w-3.5" /> {talent ? "Wired" : "Canon fallback"}
              </span>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <ReferenceFrame
                label="Face anchor"
                detail={talent ? `${talent.name} — front portrait` : "Front portrait · scar + eye priority"}
                accent="from-[#33251f] via-[#17131d] to-[#0b0c18]"
                imageUrl={faceImage}
              />
              <ReferenceFrame
                label={talent ? `${talent.name} portrait` : "Wardrobe anchor"}
                detail={talent ? `Full body — ${talent.body_type || "athletic"} build` : "Black / gold armor + cape silhouette"}
                accent="from-[#25213a] via-[#111321] to-[#080a13]"
              />
              <ReferenceFrame
                label="Title treatment"
                detail={`${episode?.title || "Obsidian"} wordmark · amber edge light`}
                accent="from-[#302718] via-[#16131c] to-[#080912]"
              />
            </div>
            <div className="mt-4 flex items-center justify-between rounded-lg border border-amber-400/10 bg-amber-400/[0.04] px-3 py-2.5 text-[11px] text-content-secondary">
              <span className="flex items-center gap-2"><LockKeyhole className="h-3.5 w-3.5 text-amber-300" /> References are the canon.</span>
              <Link href="/talent" className="font-medium text-amber-300 hover:text-amber-200">Open identity bible <ArrowRight className="ml-1 inline h-3 w-3" /></Link>
            </div>
          </section>

          {/* Sequence Beats — from API */}
          <section className="rounded-2xl border border-border-subtle bg-surface-raised p-5">
            <div className="flex items-center justify-between">
              <SectionLabel>Sequence beats <span className="text-content-muted">({scenes.length} from story API)</span></SectionLabel>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={queuing || scenes.length === 0}
                  onClick={() => void queueAllBeats()}
                  className="flex items-center gap-1.5 rounded-md bg-purple-600 px-3 py-1.5 text-[10px] font-medium text-white hover:bg-purple-500 disabled:opacity-50"
                >
                  {queuing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
                  {queuing ? "Queuing…" : "Queue All to H3"}
                </button>
                <button
                  type="button"
                  onClick={() => setQueueMessage("Preview animatic: queue beats to H3 first to generate renders.")}
                  className="flex items-center gap-1.5 rounded-md border border-border-default px-2.5 py-1.5 text-[10px] font-medium text-content-secondary hover:bg-surface-hover"
                >
                  <Play className="h-3 w-3" /> Preview animatic
                </button>
              </div>
            </div>
            <div className="relative space-y-2">
              {scenes.length === 0 ? (
                <p className="py-8 text-center text-xs text-content-muted">No beats defined for this sequence. Add scenes in the Story engine.</p>
              ) : (
                scenes.map((scene, index) => (
                  <div key={scene.id} className="group grid grid-cols-[44px_64px_1fr_auto] items-center gap-3 rounded-xl border border-transparent bg-surface-sunken/60 p-3 transition-colors hover:border-border-default">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-active text-[10px] font-bold text-content-secondary">
                      {String(scene.scene_number).padStart(2, "0")}
                    </div>
                    <div>
                      <p className="text-[10px] font-medium text-content-muted">{scene.mood || "—"}</p>
                      <p className="mt-0.5 text-xs font-semibold text-content-primary">{scene.title}</p>
                    </div>
                    <p className="hidden text-xs leading-5 text-content-tertiary md:block">{scene.purpose || scene.title}</p>
                    <span className="flex items-center gap-1.5 whitespace-nowrap text-[10px] text-content-muted">
                      <span className={`h-1.5 w-1.5 rounded-full ${index === 0 ? "bg-amber-400" : "bg-slate-500"}`} />
                      {scene.desired_emotion || "planned"}
                    </span>
                    {index < scenes.length - 1 && <div className="absolute left-[27px] hidden h-2 translate-y-8 border-l border-border-default sm:block" />}
                  </div>
                ))
              )}
            </div>
          </section>
        </main>

        <aside className="space-y-6">

          {/* Locked Constraints */}
          <section className="rounded-2xl border border-border-subtle bg-surface-raised p-5">
            <SectionLabel>Locked constraints {talent ? <span className="text-green-400">✓</span> : ""}</SectionLabel>
            <div className="space-y-3">
              {identityLocks.map((item) => (
                <div key={item.label} className="flex items-start justify-between gap-3 border-b border-border-subtle pb-3 last:border-0 last:pb-0">
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-content-muted">{item.label}</p>
                    <p className="mt-1 text-xs font-medium text-content-primary">{item.value}</p>
                  </div>
                  <LockKeyhole className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-300/70" />
                </div>
              ))}
            </div>
            <div className="mt-4 rounded-lg border border-status-error/20 bg-status-error-muted/30 p-3 text-[10px] leading-4 text-content-secondary">
              <b className="text-status-error">Do not generate:</b> turning, facial variation, costume changes, plastic skin, or a fresh T2I frame.
            </div>
          </section>

          {/* Production Status */}
          <section className="rounded-2xl border border-border-subtle bg-surface-raised p-5">
            <SectionLabel>Production gates</SectionLabel>
            <div className="h-1.5 overflow-hidden rounded-full bg-surface-active">
              <div className="h-full w-1/4 rounded-full bg-gradient-to-r from-amber-500 to-amber-300" />
            </div>
            <div className="mt-5 space-y-3">
              {[
                { label: "Story board", state: scenes.length > 0 ? "Done" : "Empty" },
                { label: "Canon references", state: talent ? "Available" : "Pending" },
                { label: "Still frames", state: "Awaiting QA" },
                { label: "H3 motion chain", state: "Queued" },
                { label: "Final assembly", state: "Queued" },
              ].map((item) => (
                <div key={item.label} className="flex items-center gap-2.5 text-xs">
                  <span className="text-content-muted"><Circle className="h-4 w-4" /></span>
                  <span className="text-content-muted">{item.label} · {item.state}</span>
                </div>
              ))}
            </div>
          </section>

          {/* Provenance */}
          <section className="rounded-2xl border border-border-subtle bg-surface-raised p-5">
            <SectionLabel>Provenance</SectionLabel>
            <div className="space-y-3 text-[11px]">
              <div className="flex items-center gap-2 text-content-secondary">
                <FileCheck2 className="h-3.5 w-3.5 text-amber-300" /> Identity bible · <Link href="/talent" className="text-amber-300 hover:text-amber-200">Open talent</Link>
              </div>
              <div className="flex items-center gap-2 text-content-secondary">
                <Clapperboard className="h-3.5 w-3.5 text-amber-300" /> Episode · {episode?.id?.slice(0, 8) || "—"}
              </div>
              <div className="flex items-center gap-2 text-content-secondary">
                <Clock3 className="h-3.5 w-3.5 text-content-muted" /> Updated · {episode?.updated_at ? new Date(episode.updated_at).toLocaleString() : "Unverified"}
              </div>
              <div className="flex items-center gap-2 text-content-secondary">
                <UserRound className="h-3.5 w-3.5 text-content-muted" /> Owner · AI Studio
              </div>
            </div>
          </section>
        </aside>
      </div>

      {/* Footer */}
      <footer className="flex flex-col justify-between gap-4 rounded-2xl border border-purple-400/20 bg-gradient-to-r from-purple-500/[0.09] to-transparent p-5 sm:flex-row sm:items-center">
        <div>
          <p className="flex items-center gap-2 text-xs font-semibold text-content-primary"><PackageCheck className="h-4 w-4 text-purple-300" /> Next handoff: motion chain</p>
          <p className="mt-1 text-xs text-content-muted">Still frames are planned; verified anchor and QA sign-off required before Motion Director.</p>
        </div>
        <Link href="/make?model=h3-video" className="inline-flex items-center justify-center gap-2 rounded-lg bg-purple-600 px-4 py-2.5 text-xs font-semibold text-white shadow-lg shadow-purple-900/20 hover:bg-purple-500">
          Open Motion Director <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </footer>

      {queueMessage && (
        <div role="status" className="rounded-lg border border-purple-500/30 bg-purple-500/10 px-4 py-3 text-xs text-purple-200">{queueMessage}</div>
      )}
    </div>
  );
}