"use client";

import Link from "next/link";
import { Brain, Zap, Film, Mic, Server, Shield, ArrowRight, Sparkles, DollarSign } from "lucide-react";

/**
 * Public landing page for unauthenticated visitors.
 * Shows: hero, features, pricing comparison, and CTA.
 */
export function LandingPage() {
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

      {/* Hero */}
      <section className="px-6 pt-20 pb-16 max-w-5xl mx-auto text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-purple-500/30 bg-purple-500/10 px-4 py-1.5 text-xs text-purple-300 mb-6">
          <Sparkles className="h-3.5 w-3.5" />
          Pay only for GPU time you use. No subscription.
        </div>

        <h1 className="text-5xl font-bold leading-tight tracking-tight mb-4">
          Your AI Creative
          <br />
          <span className="bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text text-transparent">
            Operating System
          </span>
        </h1>

        <p className="text-lg text-gray-400 max-w-2xl mx-auto mb-8">
          Generate images, train custom AI models, produce videos, clone voices,
          and publish content — all from one platform. Connect your own GPU provider
          and pay only for compute time.
        </p>

        <div className="flex items-center justify-center gap-4">
          <Link
            href="/login"
            className="flex items-center gap-2 rounded-lg bg-purple-600 px-6 py-3 text-sm font-medium text-white hover:bg-purple-700 transition-colors"
          >
            Start Creating <ArrowRight className="h-4 w-4" />
          </Link>
          <a
            href="#pricing"
            className="flex items-center gap-2 rounded-lg border border-white/10 px-6 py-3 text-sm text-gray-300 hover:bg-white/5 transition-colors"
          >
            View Pricing
          </a>
        </div>
      </section>

      {/* Features Grid */}
      <section className="px-6 py-16 max-w-6xl mx-auto">
        <h2 className="text-2xl font-bold text-center mb-2">Everything you need to create</h2>
        <p className="text-sm text-gray-500 text-center mb-10">From prompt to published content in minutes, not weeks.</p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {[
            {
              icon: Sparkles,
              title: "Image Generation",
              desc: "Flux Dev, SDXL Turbo, SD 1.5. Generate professional images in seconds with full control over style, composition, and lighting.",
              color: "text-purple-400",
            },
            {
              icon: Film,
              title: "Video Production",
              desc: "WAN 2.1/2.2 text-to-video and image-to-video. Storyboard editor for multi-shot sequences with FFMPEG assembly.",
              color: "text-blue-400",
            },
            {
              icon: Mic,
              title: "Voice & Music",
              desc: "ElevenLabs voice generation with 21+ voices. MOSS-TTS for voice cloning. Music generation for soundtracks.",
              color: "text-pink-400",
            },
            {
              icon: Brain,
              title: "AI Brain",
              desc: "Built-in LLM assistant for prompt engineering, brainstorming, story writing, and production planning. Local-first with Ollama.",
              color: "text-green-400",
            },
            {
              icon: Zap,
              title: "LoRA Training",
              desc: "Train custom identity models from 10-50 photos. Your AI talent stays consistent across every generation.",
              color: "text-amber-400",
            },
            {
              icon: Server,
              title: "GPU Fleet Management",
              desc: "Connect Vast.ai or RunPod. Launch workers on demand, auto-provision based on workload, track costs in real-time.",
              color: "text-cyan-400",
            },
          ].map((feature) => (
            <div
              key={feature.title}
              className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6 hover:border-purple-500/20 transition-colors"
            >
              <feature.icon className={`h-8 w-8 ${feature.color} mb-3`} />
              <h3 className="text-sm font-semibold text-white mb-1">{feature.title}</h3>
              <p className="text-xs text-gray-500 leading-relaxed">{feature.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How It Works */}
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
              {idx < 2 && (
                <ArrowRight className="h-4 w-4 text-gray-700 mx-auto mt-3 hidden lg:block" />
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="px-6 py-16 max-w-6xl mx-auto">
        <h2 className="text-2xl font-bold text-center mb-2">Transparent pricing</h2>
        <p className="text-sm text-gray-500 text-center mb-10">
          No monthly subscriptions. No token limits. Pay only for the GPU time you use.
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

      {/* Security */}
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

      {/* Final CTA */}
      <section className="px-6 py-16 max-w-3xl mx-auto text-center">
        <h2 className="text-2xl font-bold mb-3">Ready to create?</h2>
        <p className="text-sm text-gray-500 mb-6">
          Sign up in 30 seconds. Connect your GPU provider. Start generating.
        </p>
        <Link
          href="/login"
          className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-8 py-3.5 text-sm font-medium text-white hover:bg-purple-700 transition-colors"
        >
          Create Free Account <ArrowRight className="h-4 w-4" />
        </Link>
      </section>

      {/* Footer */}
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
