"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Brain,
  Zap,
  Film,
  Mic,
  Server,
  Shield,
  ArrowRight,
  Sparkles,
  DollarSign,
  Users,
  Play,
  Star,
  RefreshCw,
} from "lucide-react";

/**
 * Public landing page for unauthenticated visitors.
 * The "whoa" front door: shows the cast of AI talent + sample work
 * front and center, then features, pricing, and CTA.
 *
 * NOTE: Showcase images are stand-ins for real talent assets until the
 * GPU pipeline is live. Swap in real persona/public_url assets from the
 * DB when available (see reports/phase-walkthrough-2026-08-23.md).
 *
 * The cast is vibe-based: visitors can switch "cast" to see the range of
 * talent an AI studio can produce. In production this becomes user-driven —
 * the cast each creator sees is built from their own trained personas.
 */

type Talent = {
  name: string;
  role: string;
  img: string;
  desc: string;
};

type CastVibe = {
  id: string;
  label: string;
  emoji: string;
  talent: Talent[];
};

const CASTS: CastVibe[] = [
  {
    id: "signature",
    label: "Signature",
    emoji: "✨",
    talent: [
      { name: "Aria", role: "Fashion & Commercial", img: "/showcase/talent-melissa.png", desc: "Luxury editorial. High-fashion lookbook." },
      { name: "Zuri", role: "Beauty & Lifestyle", img: "/showcase/talent-shy.png", desc: "Soft glam, skincare, everyday luxury." },
      { name: "Malik", role: "Men's Style", img: "/showcase/talent-michael.png", desc: "Versatile, athletic, menswear." },
      { name: "Kofi", role: "Editorial & Runway", img: "/showcase/talent-darius.png", desc: "Cinematic, commanding presence." },
      { name: "Amara", role: "Influencer & Commercial", img: "/showcase/talent-latifah.png", desc: "Bold, charismatic brand ambassador." },
      { name: "Nia", role: "Beauty & Youth", img: "/showcase/talent-jasmine.png", desc: "Fresh, Gen-Z clean-girl aesthetic." },
    ],
  },
  {
    id: "lifestyle",
    label: "Lifestyle",
    emoji: "📱",
    talent: [
      { name: "Maya", role: "Day-in-the-life creator", img: "/showcase/life-black-woman.png", desc: "Golden hour, coffee shops, real life." },
      { name: "Kai", role: "Streetwear & urban", img: "/showcase/life-black-man.png", desc: "Mural backdrops, casual flex." },
      { name: "Priya", role: "Cafe & cozy aesthetic", img: "/showcase/life-south-asian.png", desc: "Warm, approachable, everyday." },
      { name: "Lena", role: "Rooftop & travel", img: "/showcase/life-blonde.png", desc: "Sunset skyline, vacation energy." },
      { name: "Jun", role: "City & motion", img: "/showcase/life-east-asian.png", desc: "Street style, golden-hour city." },
      { name: "Sofia", role: "Sun-kissed & outdoors", img: "/showcase/life-latina.png", desc: "Farmers market, beach, warm tones." },
    ],
  },
  {
    id: "global",
    label: "Global",
    emoji: "🌍",
    talent: [
      { name: "Aria", role: "Fashion & Commercial", img: "/showcase/talent-melissa.png", desc: "Luxury editorial." },
      { name: "Ananya", role: "Editorial & Beauty", img: "/showcase/talent-south-asian.png", desc: "Elegant, gold-glow studio." },
      { name: "Hiro", role: "Sharp & Modern", img: "/showcase/talent-east-asian.png", desc: "Clean, editorial menswear." },
      { name: "Valentina", role: "Striking & Confident", img: "/showcase/talent-latina.png", desc: "Bold beauty, magenta glow." },
      { name: "Layla", role: "Graceful & Elegant", img: "/showcase/talent-mideast.png", desc: "Refined, violet studio." },
      { name: "Elle", role: "High-Fashion Edge", img: "/showcase/talent-blonde.png", desc: "Platinum, avant-garde." },
    ],
  },
];

const WORK = [
  { img: "/showcase/work-fashion.png", tag: "Campaign", label: "Fashion editorial — brand campaign" },
  { img: "/showcase/work-product.png", tag: "Product", label: "Luxury product commercial still" },
  { img: "/showcase/work-film.png", tag: "Film", label: "Cinematic film still — neon city night" },
];

export function LandingPage() {
  const [activeCast, setActiveCast] = useState<string>("signature");
  const activeTalent = CASTS.find((c) => c.id === activeCast)?.talent ?? CASTS[0].talent;

  return (
    <div className="min-h-screen bg-[#0a0a1a] text-white">
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-4 max-w-7xl mx-auto">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-purple-600">
            <Brain className="h-5 w-5 text-white" />
          </div>
          <span className="text-lg font-bold">AI Studio</span>
        </div>
        <div className="flex items-center gap-4">
          <Link href="/login" className="text-sm text-gray-400 hover:text-white transition-colors">
            Sign In
          </Link>
          <Link
            href="/login"
            className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 transition-colors"
          >
            Get Started
          </Link>
        </div>
      </nav>

      {/* ===== HERO — the whoa ===== */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/showcase/hero.png"
            alt=""
            className="w-full h-full object-cover object-center"
          />
          <div className="absolute inset-0 bg-gradient-to-r from-[#0a0a1a] via-[#0a0a1a]/70 to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-t from-[#0a0a1a] via-transparent to-[#0a0a1a]/40" />
        </div>

        <div className="relative px-6 py-28 max-w-7xl mx-auto">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-purple-500/30 bg-purple-500/10 px-4 py-1.5 text-xs text-purple-300 mb-6 backdrop-blur">
              <Sparkles className="h-3.5 w-3.5" />
              Your AI talent agency. Pay only for GPU time you use.
            </div>

            <h1 className="text-5xl md:text-6xl font-bold leading-tight tracking-tight mb-5">
              Your AI
              <br />
              <span className="bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text text-transparent">
                Talent Agency
              </span>
            </h1>

            <p className="text-lg text-gray-300 max-w-xl mb-8 leading-relaxed">
              Meet Aria, Zuri, Malik, Kofi, Amara, and Nia — your cast
              of AI models, ready to shoot. Generate images, train custom models,
              produce video, and publish content. One platform. Your compute.
            </p>

            <div className="flex items-center gap-4">
              <Link
                href="/login"
                className="flex items-center gap-2 rounded-lg bg-purple-600 px-6 py-3 text-sm font-medium text-white hover:bg-purple-700 transition-colors"
              >
                Meet the Talent <ArrowRight className="h-4 w-4" />
              </Link>
              <a
                href="#showcase"
                className="flex items-center gap-2 rounded-lg border border-white/10 px-6 py-3 text-sm text-gray-300 hover:bg-white/5 transition-colors"
              >
                See the Work
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* ===== THE CAST ===== */}
      <section id="showcase" className="px-6 py-20 max-w-7xl mx-auto">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold mb-3">Meet your cast</h2>
          <p className="text-sm text-gray-500 max-w-xl mx-auto">
            AI models trained on your brand. Consistent across every generation,
            every campaign, every post. Pick a vibe — the cast is yours to shape.
          </p>

          {/* Vibe switcher — cast changes per vibe */}
          <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-white/[0.08] bg-[#12122a] p-1.5">
            {CASTS.map((cast) => (
              <button
                key={cast.id}
                onClick={() => setActiveCast(cast.id)}
                className={`flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium transition-colors ${
                  activeCast === cast.id
                    ? "bg-purple-600 text-white"
                    : "text-gray-400 hover:text-white hover:bg-white/[0.04]"
                }`}
              >
                <span>{cast.emoji}</span>
                {cast.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {activeTalent.map((t) => (
            <div
              key={t.name}
              className="group rounded-2xl overflow-hidden border border-white/[0.06] bg-[#12122a] hover:border-purple-500/40 transition-colors"
            >
              <div className="aspect-[3/4] overflow-hidden">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={t.img}
                  alt={t.name}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                />
              </div>
              <div className="p-3">
                <p className="text-sm font-semibold text-white flex items-center gap-1">
                  {t.name}
                </p>
                <p className="text-[10px] text-purple-400 mt-0.5">{t.role}</p>
                <p className="text-[10px] text-gray-500 mt-1 leading-relaxed">{t.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ===== SAMPLE WORK ===== */}
      <section className="px-6 pb-20 max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h2 className="text-2xl font-bold mb-1">Made in AI Studio</h2>
            <p className="text-sm text-gray-500">From prompt to published. A few things the machine made.</p>
          </div>
          <Link href="/login" className="text-sm text-purple-400 hover:text-purple-300 flex items-center gap-1">
            Start creating <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {WORK.map((w) => (
            <div
              key={w.img}
              className="group relative rounded-2xl overflow-hidden border border-white/[0.06] bg-[#12122a]"
            >
              <div className="aspect-[16/10] overflow-hidden">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={w.img}
                  alt={w.label}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                />
              </div>
              <div className="absolute top-3 left-3 rounded-full bg-black/60 backdrop-blur px-3 py-1 text-[10px] font-medium text-purple-300 border border-purple-500/30">
                {w.tag}
              </div>
              <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-end">
                <p className="p-4 text-sm text-white font-medium">{w.label}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ===== HOW IT WORKS ===== */}
      <section className="px-6 py-16 max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold text-center mb-10">How it works</h2>
        <div className="flex items-start justify-between gap-8">
          {[
            { step: "1", title: "Sign Up", desc: "Create a free account. No credit card required." },
            { step: "2", title: "Connect GPU", desc: "Add your Vast.ai or RunPod API key. Bring your own compute." },
            { step: "3", title: "Create", desc: "Generate images, train models, produce videos. Pay only for GPU time." },
          ].map((item, idx) => (
            <div key={item.step} className="flex-1 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-purple-600/20 border border-purple-500/30 mx-auto mb-3">
                <span className="text-lg font-bold text-purple-400">{item.step}</span>
              </div>
              <h3 className="text-sm font-semibold text-white mb-1">{item.title}</h3>
              <p className="text-xs text-gray-500">{item.desc}</p>
              {idx < 2 && <ArrowRight className="h-4 w-4 text-gray-700 mx-auto mt-3 hidden lg:block" />}
            </div>
          ))}
        </div>
      </section>

      {/* ===== PRICING ===== */}
      <section id="pricing" className="px-6 py-16 max-w-6xl mx-auto">
        <h2 className="text-2xl font-bold text-center mb-2">Transparent pricing</h2>
        <p className="text-sm text-gray-500 text-center mb-10">
          Simple monthly plans from $29. Credits included. Pay only for the GPU time you use.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10">
          {/* Our Model */}
          <div className="rounded-xl border-2 border-purple-500/40 bg-purple-500/5 p-6 relative">
            <div className="absolute -top-3 left-6">
              <span className="rounded-full bg-purple-600 px-3 py-1 text-xs font-medium text-white">
                AI Studio
              </span>
            </div>
            <div className="mt-2">
              <div className="flex items-baseline gap-1 mb-1">
                <span className="text-3xl font-bold text-white">$0</span>
                <span className="text-sm text-gray-400">/month</span>
              </div>
              <p className="text-xs text-gray-500 mb-4">+ GPU compute at cost</p>

              <div className="space-y-2 mb-6">
                {[
                  "Unlimited generations",
                  "Unlimited model training",
                  "Unlimited video production",
                  "Full platform access",
                  "AI Brain (local LLM, free)",
                  "Pay ~$0.003/image (SDXL) or ~$0.01/image (Flux)",
                  "Bring your own GPU provider",
                  "No vendor lock-in",
                ].map((item) => (
                  <div key={item} className="flex items-start gap-2 text-xs text-gray-300">
                    <DollarSign className="h-3.5 w-3.5 text-purple-400 mt-0.5 shrink-0" />
                    {item}
                  </div>
                ))}
              </div>

              <Link
                href="/login"
                className="block w-full rounded-lg bg-purple-600 py-2.5 text-center text-sm font-medium text-white hover:bg-purple-700 transition-colors"
              >
                Get Started Free
              </Link>
            </div>
          </div>

          {/* Competitor Comparison */}
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
            <h3 className="text-sm font-semibold text-white mb-4">vs. Subscriptions</h3>
            <div className="space-y-3">
              {[
                { name: "Midjourney", price: "$10–60/mo", limit: "Limited generations, no training, no video" },
                { name: "Leonardo AI", price: "$12–48/mo", limit: "Token-based, runs out fast with high quality" },
                { name: "Runway ML", price: "$15–76/mo", limit: "Limited video seconds, no image training" },
                { name: "Pika", price: "$8–58/mo", limit: "Video only, no image generation or training" },
              ].map((comp) => (
                <div key={comp.name} className="flex items-center justify-between rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-3">
                  <div>
                    <p className="text-xs font-medium text-white">{comp.name}</p>
                    <p className="text-[10px] text-gray-500">{comp.limit}</p>
                  </div>
                  <span className="text-xs text-red-400 font-medium">{comp.price}</span>
                </div>
              ))}
            </div>
            <div className="mt-4 rounded-lg border border-green-500/20 bg-green-500/5 p-3">
              <p className="text-xs text-green-400 font-medium">AI Studio advantage</p>
              <p className="text-[10px] text-gray-400 mt-0.5">
                Everything unlimited. Average user spends $5–15/month on GPU compute.
                Power users who generate 500+ images/month spend less than a Midjourney Pro subscription.
              </p>
            </div>
          </div>
        </div>

        {/* Cost Examples */}
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
          <h3 className="text-sm font-semibold text-white mb-4">Real cost examples</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { action: "1 image (SDXL Turbo)", cost: "$0.001", time: "~2 sec" },
              { action: "1 image (Flux Dev)", cost: "$0.005", time: "~15 sec" },
              { action: "1 video clip (WAN 2.1)", cost: "$0.05", time: "~60 sec" },
              { action: "LoRA training (1000 steps)", cost: "$1.50", time: "~15 min" },
            ].map((ex) => (
              <div key={ex.action} className="text-center">
                <p className="text-lg font-bold text-white">{ex.cost}</p>
                <p className="text-xs text-gray-400 mt-0.5">{ex.action}</p>
                <p className="text-[10px] text-gray-600">{ex.time}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== SECURITY ===== */}
      <section className="px-6 py-12 max-w-4xl mx-auto">
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6 flex items-start gap-4">
          <Shield className="h-8 w-8 text-green-400 shrink-0" />
          <div>
            <h3 className="text-sm font-semibold text-white mb-1">Your data, your infrastructure</h3>
            <p className="text-xs text-gray-500 leading-relaxed">
              AI Studio is fully multi-tenant with strict data isolation. Your models, images, and training data
              are stored in your own Backblaze B2 bucket. GPU compute runs on your own provider account.
              Nothing is shared between organizations. All API communication is encrypted.
            </p>
          </div>
        </div>
      </section>

      {/* ===== FINAL CTA ===== */}
      <section className="px-6 py-16 max-w-3xl mx-auto text-center">
        <h2 className="text-2xl font-bold mb-3">Ready to cast your next campaign?</h2>
        <p className="text-sm text-gray-500 mb-6">
          Sign up in 30 seconds. Connect your GPU provider. Start creating with your own AI talent.
        </p>
        <Link
          href="/login"
          className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-8 py-3.5 text-sm font-medium text-white hover:bg-purple-700 transition-colors"
        >
          Create Free Account <ArrowRight className="h-4 w-4" />
        </Link>
      </section>

      {/* ===== FOOTER ===== */}
      <footer className="border-t border-white/[0.06] px-6 py-8">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-purple-600">
              <Brain className="h-4 w-4 text-white" />
            </div>
            <span className="text-sm font-bold text-gray-400">AI Studio</span>
          </div>
          <p className="text-[10px] text-gray-600">
            Built with Next.js, FastAPI, ComfyUI, and Ollama. GPU via Vast.ai and RunPod.
          </p>
        </div>
      </footer>
    </div>
  );
}
