import Image from "next/image";
import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Showcase — AI Studio",
  description: "Explore AI Studio's public gallery of talent, campaigns, and cinematic work.",
};

type GalleryItem = {
  src: string;
  alt: string;
  label: string;
  detail: string;
};

const CAST: GalleryItem[] = [
  { src: "/showcase/talent-melissa.png", alt: "AI fashion talent in an editorial portrait", label: "Aria", detail: "Fashion editorial" },
  { src: "/showcase/talent-shy.png", alt: "AI beauty talent in a studio portrait", label: "Zuri", detail: "Beauty and lifestyle" },
  { src: "/showcase/talent-michael.png", alt: "AI menswear talent in a studio portrait", label: "Malik", detail: "Men's style" },
  { src: "/showcase/talent-darius.png", alt: "AI editorial talent in a studio portrait", label: "Kofi", detail: "Editorial and runway" },
  { src: "/showcase/talent-latifah.png", alt: "AI commercial talent in a studio portrait", label: "Amara", detail: "Commercial campaigns" },
  { src: "/showcase/talent-jasmine.png", alt: "AI beauty talent in a natural portrait", label: "Nia", detail: "Beauty and youth" },
];

const WORK: GalleryItem[] = [
  { src: "/showcase/work-fashion.png", alt: "AI-generated fashion campaign still", label: "Fashion editorial", detail: "Campaign" },
  { src: "/showcase/work-product.png", alt: "AI-generated luxury product campaign still", label: "Luxury product", detail: "Product" },
  { src: "/showcase/work-film.png", alt: "AI-generated cinematic neon city still", label: "Neon city", detail: "Film" },
];

function GalleryCard({ item }: { item: GalleryItem }) {
  return (
    <article className="group overflow-hidden rounded-2xl border border-white/[0.08] bg-white/[0.035] shadow-2xl shadow-black/20">
      <div className="relative aspect-[3/4] overflow-hidden bg-[#15152d]">
        <Image
          src={item.src}
          alt={item.alt}
          fill
          sizes="(max-width: 640px) 45vw, (max-width: 1024px) 30vw, 16vw"
          className="object-cover transition duration-500 group-hover:scale-105"
        />
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-4 pt-14">
          <p className="text-sm font-semibold text-white">{item.label}</p>
          <p className="mt-1 text-xs text-purple-200/75">{item.detail}</p>
        </div>
      </div>
    </article>
  );
}

export default function ShowcasePage() {
  return (
    <main className="min-h-screen bg-[#090918] text-white">
      <nav className="mx-auto flex max-w-7xl items-center justify-between px-5 py-5 sm:px-8" aria-label="Showcase navigation">
        <Link href="/" className="text-sm font-semibold tracking-[0.18em] text-white/90">
          AI STUDIO
        </Link>
        <div className="flex items-center gap-4 text-sm">
          <Link href="/pricing" className="text-white/60 transition hover:text-white">Pricing</Link>
          <Link href="/login" className="rounded-full border border-purple-400/40 bg-purple-500/15 px-4 py-2 text-purple-100 transition hover:bg-purple-500/25">Get started</Link>
        </div>
      </nav>

      <section className="relative isolate overflow-hidden border-y border-white/[0.06]">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_75%_25%,rgba(124,58,237,0.24),transparent_38%),radial-gradient(circle_at_15%_80%,rgba(37,99,235,0.16),transparent_35%)]" />
        <div className="mx-auto grid max-w-7xl gap-10 px-5 py-20 sm:px-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:py-28">
          <div>
            <p className="mb-5 text-xs font-semibold uppercase tracking-[0.28em] text-purple-300">Public gallery</p>
            <h1 className="max-w-3xl text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">A studio for characters, campaigns, and worlds.</h1>
            <p className="mt-6 max-w-xl text-base leading-7 text-white/60 sm:text-lg">See the kind of visual work AI Studio is built to produce. Every image here is a local showcase asset, not a private tenant record.</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/login" className="rounded-full bg-purple-600 px-5 py-3 text-sm font-medium text-white transition hover:bg-purple-500">Create with AI Studio</Link>
              <a href="#the-cast" className="rounded-full border border-white/15 px-5 py-3 text-sm text-white/75 transition hover:border-white/30 hover:text-white">Browse the gallery</a>
            </div>
          </div>
          <div className="relative mx-auto w-full max-w-md overflow-hidden rounded-3xl border border-white/10 bg-white/[0.04] p-2 shadow-2xl shadow-purple-950/30">
            <div className="relative aspect-[4/3] overflow-hidden rounded-2xl bg-[#15152d]">
              <Image src="/showcase/hero.png" alt="AI Studio showcase hero artwork" fill priority sizes="(max-width: 1024px) 90vw, 35vw" className="object-cover" />
            </div>
          </div>
        </div>
      </section>

      <section id="the-cast" className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
        <div className="mb-8 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-purple-300">The cast</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight">Meet the talent</h2>
          </div>
          <p className="max-w-md text-sm leading-6 text-white/50">A sample range of consistent AI personas for editorial, lifestyle, and commercial work.</p>
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {CAST.map((item) => <GalleryCard key={item.src} item={item} />)}
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 pb-20 sm:px-8">
        <div className="mb-8">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-300">Selected work</p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight">From prompt to frame</h2>
        </div>
        <div className="grid gap-5 md:grid-cols-3">
          {WORK.map((item) => (
            <article key={item.src} className="group overflow-hidden rounded-2xl border border-white/[0.08] bg-white/[0.035]">
              <div className="relative aspect-[16/10] overflow-hidden bg-[#15152d]">
                <Image src={item.src} alt={item.alt} fill sizes="(max-width: 768px) 90vw, 30vw" className="object-cover transition duration-500 group-hover:scale-105" />
              </div>
              <div className="p-4"><p className="text-sm font-semibold text-white">{item.label}</p><p className="mt-1 text-xs text-white/50">{item.detail} · AI Studio sample</p></div>
            </article>
          ))}
        </div>
      </section>

      <footer className="border-t border-white/[0.06] px-5 py-8 sm:px-8">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 text-xs text-white/40 sm:flex-row sm:items-center sm:justify-between">
          <span>AI Studio public showcase</span>
          <Link href="/" className="text-purple-300 transition hover:text-purple-200">Back to AI Studio →</Link>
        </div>
      </footer>
    </main>
  );
}
