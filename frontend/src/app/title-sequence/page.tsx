"use client";

import Link from "next/link";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  Clapperboard,
  Clock3,
  FileCheck2,
  Film,
  LockKeyhole,
  MoreHorizontal,
  PackageCheck,
  Play,
  ShieldCheck,
  Sparkles,
  UserRound,
} from "lucide-react";

const identityLocks = [
  { label: "Complexion", value: "Deep dark-brown / Black", tone: "amber" },
  { label: "Hair", value: "Tightly coiled, high-volume afro", tone: "violet" },
  { label: "Signature mark", value: "Gold scar on left cheek", tone: "rose" },
  { label: "Eye treatment", value: "Glowing amber left eye", tone: "cyan" },
  { label: "Wardrobe", value: "Black + gold armor and cape", tone: "slate" },
];

const beats = [
  { id: "01", time: "00:00–00:03", title: "The mark", description: "Black screen. A gold thread catches light and resolves into the scar on the left cheek.", status: "Planned", color: "bg-slate-500" },
  { id: "02", time: "00:03–00:07", title: "The reveal", description: "Portrait anchor target: amber eye ignites, then holds. No turn or facial variation.", status: "Awaiting QA", color: "bg-amber-400" },
  { id: "03", time: "00:07–00:11", title: "The mantle", description: "Armor and cape settle into frame as the title treatment emerges from shadow.", status: "Queued", color: "bg-slate-500" },
  { id: "04", time: "00:11–00:15", title: "Obsidian", description: "Title lockup lands. Hard cut to episode one slate; sound bed continues under the cut.", status: "Queued", color: "bg-slate-500" },
];

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-content-muted">{children}</p>;
}

function ReferenceFrame({ label, detail, accent }: { label: string; detail: string; accent: string }) {
  return (
    <div className="group relative overflow-hidden rounded-xl border border-border-subtle bg-[#0b0b18]">
      <div className={`relative aspect-[4/3] overflow-hidden bg-gradient-to-br ${accent}`}>
        <div className="absolute inset-0 opacity-70 [background-image:radial-gradient(circle_at_68%_30%,rgba(251,191,36,.35),transparent_23%),linear-gradient(125deg,transparent_46%,rgba(255,255,255,.08)_47%,transparent_48%)]" />
        <div className="absolute bottom-4 left-4 h-20 w-20 rounded-full border border-amber-300/30 bg-black/30 shadow-[0_0_35px_rgba(245,158,11,.18)]" />
        <span className="absolute left-3 top-3 rounded-md border border-white/10 bg-black/30 px-2 py-1 text-[9px] font-medium uppercase tracking-widest text-white/70">Canon reference</span>
        <span className="absolute bottom-3 right-3 rounded-full bg-black/40 px-2 py-1 text-[9px] text-white/70">{label}</span>
      </div>
      <div className="p-3"><p className="text-xs font-semibold text-content-primary">{label}</p><p className="mt-1 text-[11px] leading-4 text-content-muted">{detail}</p></div>
    </div>
  );
}

export default function TitleSequencePage() {
  return (
    <div className="mx-auto max-w-[1440px] space-y-6 pb-10">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-xs text-content-muted"><Link href="/projects" className="hover:text-content-primary">Projects</Link><ChevronRight className="h-3.5 w-3.5" /><span>Obsidian</span><ChevronRight className="h-3.5 w-3.5" /><span className="text-content-secondary">Title sequence</span></div>
        <div className="flex items-center gap-2"><span className="rounded-full border border-amber-400/20 bg-amber-400/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-amber-300">Production deliverable</span><button className="rounded-lg border border-border-default p-2 text-content-muted hover:bg-surface-hover" aria-label="More actions"><MoreHorizontal className="h-4 w-4" /></button></div>
      </div>

      <header className="relative overflow-hidden rounded-2xl border border-amber-400/15 bg-gradient-to-br from-[#181524] via-[#111122] to-[#0b0b18] p-7 shadow-2xl">
        <div className="absolute -right-20 -top-32 h-80 w-80 rounded-full bg-amber-500/10 blur-3xl" />
        <div className="relative flex flex-col justify-between gap-8 lg:flex-row lg:items-end">
          <div className="max-w-2xl"><div className="mb-4 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-300"><Sparkles className="h-3.5 w-3.5" /> Obsidian / opening identity</div><h1 className="font-serif text-5xl tracking-[0.16em] text-white sm:text-7xl">OBSIDIAN</h1><p className="mt-4 max-w-xl text-sm leading-6 text-content-secondary">A 15-second title-sequence concept designed against the Obsidian canon. The mark, the eye, and the mantle are planned as four deliberate beats before the episode slate; render evidence is pending.</p></div>
          <div className="grid grid-cols-2 gap-x-8 gap-y-4 text-right sm:grid-cols-4 lg:min-w-[480px]"><div><p className="text-[10px] uppercase tracking-wider text-content-muted">Status</p><p className="mt-1 text-sm font-semibold text-amber-300">Planned · QA pending</p></div><div><p className="text-[10px] uppercase tracking-wider text-content-muted">Target runtime</p><p className="mt-1 text-sm font-semibold text-content-primary">00:15</p></div><div><p className="text-[10px] uppercase tracking-wider text-content-muted">Target format</p><p className="mt-1 text-sm font-semibold text-content-primary">21:9 · 24 fps</p></div><div><p className="text-[10px] uppercase tracking-wider text-content-muted">Draft</p><p className="mt-1 text-sm font-semibold text-content-primary">Unversioned</p></div></div>
        </div>
      </header>

      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <main className="space-y-6">
          <section className="rounded-2xl border border-border-subtle bg-surface-raised p-5"><div className="flex items-center justify-between"><SectionLabel>Identity reference plan</SectionLabel><span className="flex items-center gap-1 text-[10px] text-amber-300"><ShieldCheck className="h-3.5 w-3.5" /> Lock unverified</span></div><div className="grid gap-4 sm:grid-cols-3"><ReferenceFrame label="Face anchor" detail="Front portrait · scar + eye priority" accent="from-[#33251f] via-[#17131d] to-[#0b0c18]" /><ReferenceFrame label="Wardrobe anchor" detail="Black / gold armor + cape silhouette" accent="from-[#25213a] via-[#111321] to-[#080a13]" /><ReferenceFrame label="Title treatment" detail="Obsidian wordmark · amber edge light" accent="from-[#302718] via-[#16131c] to-[#080912]" /></div><div className="mt-4 flex items-center justify-between rounded-lg border border-amber-400/10 bg-amber-400/[0.04] px-3 py-2.5 text-[11px] text-content-secondary"><span className="flex items-center gap-2"><LockKeyhole className="h-3.5 w-3.5 text-amber-300" /> References are the canon. Any visible drift blocks animation.</span><button className="font-medium text-amber-300 hover:text-amber-200">Open identity bible <ArrowRight className="ml-1 inline h-3 w-3" /></button></div></section>

          <section className="rounded-2xl border border-border-subtle bg-surface-raised p-5"><div className="flex items-center justify-between"><SectionLabel>Sequence beats</SectionLabel><button className="flex items-center gap-1.5 rounded-md border border-border-default px-2.5 py-1.5 text-[10px] font-medium text-content-secondary hover:bg-surface-hover"><Play className="h-3 w-3" /> Preview animatic</button></div><div className="relative space-y-2">{beats.map((beat, index) => <div key={beat.id} className="group grid grid-cols-[44px_78px_1fr_auto] items-center gap-3 rounded-xl border border-transparent bg-surface-sunken/60 p-3 transition-colors hover:border-border-default"><div className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-active text-[10px] font-bold text-content-secondary">{beat.id}</div><div><p className="text-[10px] font-medium text-content-muted">{beat.time}</p><p className="mt-0.5 text-xs font-semibold text-content-primary">{beat.title}</p></div><p className="hidden text-xs leading-5 text-content-tertiary md:block">{beat.description}</p><span className="flex items-center gap-1.5 whitespace-nowrap text-[10px] text-content-muted"><span className={`h-1.5 w-1.5 rounded-full ${beat.color}`} />{beat.status}</span>{index < beats.length - 1 && <div className="absolute left-[27px] hidden h-2 translate-y-8 border-l border-border-default sm:block" />}</div>)}</div></section>
        </main>

        <aside className="space-y-6">
          <section className="rounded-2xl border border-border-subtle bg-surface-raised p-5"><SectionLabel>Locked constraints</SectionLabel><div className="space-y-3">{identityLocks.map((item) => <div key={item.label} className="flex items-start justify-between gap-3 border-b border-border-subtle pb-3 last:border-0 last:pb-0"><div><p className="text-[10px] uppercase tracking-wider text-content-muted">{item.label}</p><p className="mt-1 text-xs font-medium text-content-primary">{item.value}</p></div><LockKeyhole className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-300/70" /></div>)}</div><div className="mt-4 rounded-lg border border-status-error/20 bg-status-error-muted/30 p-3 text-[10px] leading-4 text-content-secondary"><b className="text-status-error">Do not generate:</b> turning or rotation, facial variation, costume changes, plastic skin, or a fresh T2I frame.</div></section>

          <section className="rounded-2xl border border-border-subtle bg-surface-raised p-5"><SectionLabel>Production status</SectionLabel><div className="mb-4 flex items-center justify-between"><span className="text-2xl font-bold text-content-primary">Planned</span><span className="text-[10px] text-content-muted">0 of 5 verified gates</span></div><div className="h-1.5 overflow-hidden rounded-full bg-surface-active"><div className="h-full w-0 rounded-full bg-gradient-to-r from-amber-500 to-amber-300" /></div><div className="mt-5 space-y-3">{[{ label: "Script + beat map", state: "Planned" }, { label: "Canon references", state: "Awaiting evidence" }, { label: "Still frames", state: "Awaiting QA" }, { label: "H3 motion chain", state: "Queued" }, { label: "TTS + final assembly", state: "Queued" }].map((item) => <div key={item.label} className="flex items-center gap-2.5 text-xs"><span className="text-content-muted"><Circle className="h-4 w-4" /></span><span className="text-content-muted">{item.label} · {item.state}</span></div>)}</div></section>

          <section className="rounded-2xl border border-border-subtle bg-surface-raised p-5"><SectionLabel>Provenance & approvals</SectionLabel><div className="space-y-3 text-[11px]"><div className="flex items-center gap-2 text-content-secondary"><FileCheck2 className="h-3.5 w-3.5 text-amber-300" /> Identity bible · version / approval unverified</div><div className="flex items-center gap-2 text-content-secondary"><Clapperboard className="h-3.5 w-3.5 text-amber-300" /> Beat map · Gary approval unverified</div><div className="flex items-center gap-2 text-content-secondary"><Clock3 className="h-3.5 w-3.5 text-content-muted" /> Last touched · timestamp unverified</div><div className="flex items-center gap-2 text-content-secondary"><UserRound className="h-3.5 w-3.5 text-content-muted" /> Owner · AI Studio / Obsidian</div></div></section>
        </aside>
      </div>

      <footer className="flex flex-col justify-between gap-4 rounded-2xl border border-purple-400/20 bg-gradient-to-r from-purple-500/[0.09] to-transparent p-5 sm:flex-row sm:items-center"><div><p className="flex items-center gap-2 text-xs font-semibold text-content-primary"><PackageCheck className="h-4 w-4 text-purple-300" /> Next handoff: motion chain</p><p className="mt-1 text-xs text-content-muted">Still frames are planned; a verified anchor and QA sign-off are required before Motion Director.</p></div><Link href="/editor" className="inline-flex items-center justify-center gap-2 rounded-lg bg-purple-600 px-4 py-2.5 text-xs font-semibold text-white shadow-lg shadow-purple-900/20 hover:bg-purple-500">Open Motion Director <ArrowRight className="h-3.5 w-3.5" /></Link></footer>
    </div>
  );
}
