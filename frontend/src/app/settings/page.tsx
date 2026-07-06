"use client";

import { useState } from "react";
import { User, HelpCircle, BookOpen, Info, ExternalLink } from "lucide-react";

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState("profile");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-sm text-gray-500">Account, help, and app information.</p>
      </div>

      <div className="grid grid-cols-4 gap-6">
        {/* Sidebar Nav */}
        <div className="space-y-1">
          {[
            { key: "profile", label: "Profile", icon: User },
            { key: "help", label: "How to Use", icon: BookOpen },
            { key: "faq", label: "FAQ", icon: HelpCircle },
            { key: "about", label: "About AI Studio", icon: Info },
          ].map((item) => (
            <button
              key={item.key}
              onClick={() => setActiveSection(item.key)}
              className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
                activeSection === item.key ? "bg-purple-600/20 text-purple-400" : "text-gray-400 hover:text-white hover:bg-white/[0.04]"
              }`}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="col-span-3 rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
          {activeSection === "profile" && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-white">Profile</h2>
              <div className="flex items-center gap-4">
                <div className="h-16 w-16 rounded-full bg-gradient-to-br from-purple-500 to-blue-500" />
                <div>
                  <p className="text-lg font-medium text-white">Gary</p>
                  <p className="text-sm text-gray-500">Studio Owner</p>
                  <p className="text-xs text-gray-600 mt-1">Member since July 2026</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 mt-4">
                <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                  <p className="text-xs text-gray-500">Total Generations</p>
                  <p className="text-xl font-bold text-white mt-1">—</p>
                </div>
                <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                  <p className="text-xs text-gray-500">Models Trained</p>
                  <p className="text-xl font-bold text-white mt-1">—</p>
                </div>
              </div>
            </div>
          )}

          {activeSection === "help" && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-white">How to Use AI Studio</h2>
              <div className="space-y-3">
                {[
                  { title: "Create Your First Image", steps: "Go to Create → type a prompt → click Generate. SDXL Turbo produces images in ~4 seconds." },
                  { title: "Train a LoRA (Custom Model)", steps: "Go to Talent → upload 10-50 photos → click 'Train LoRA'. The AI learns that person/style." },
                  { title: "Generate Video", steps: "Go to Create → Video tab → describe a scene → Generate. WAN 2.2 produces 2-4 second clips." },
                  { title: "Voice Generation", steps: "Go to Create → Audio tab → type text → Generate Voice. Uses ElevenLabs (21 voices available)." },
                  { title: "Use AI Brain", steps: "Click 'Chat with Brain' in sidebar. Ask for prompt help, brainstorming, or script writing." },
                  { title: "Manage Models", steps: "Go to Models → Upload to add new checkpoints, LoRAs, VAEs. Archive to free GPU, restore anytime." },
                  { title: "Schedule Posts", steps: "Go to Publish → Schedule Post → pick platform and time. Connect TikTok/IG via OAuth." },
                  { title: "GPU Management", steps: "Go to Admin → Fleet. Start/stop workers, set budgets, monitor costs in real-time." },
                ].map((item) => (
                  <div key={item.title} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                    <p className="text-sm font-medium text-white">{item.title}</p>
                    <p className="text-xs text-gray-400 mt-1">{item.steps}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeSection === "faq" && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-white">Frequently Asked Questions</h2>
              <div className="space-y-3">
                {[
                  { q: "How much does GPU time cost?", a: "RTX 3090: ~$0.08/hr. A100 80GB: ~$2-3/hr. You only pay while generating." },
                  { q: "What models can I use?", a: "SDXL Turbo (fast), Flux 2 Klein (high quality), WAN 2.2 (video). Upload any .safetensors model." },
                  { q: "How long does training take?", a: "1000 steps on RTX 3090: ~15-20 minutes. Results improve with more images (10-50 recommended)." },
                  { q: "Can I use my own voice?", a: "ElevenLabs supports voice cloning. Upload a 10-second sample to create a custom voice." },
                  { q: "Is my data private?", a: "Yes. Your models, images, and data are stored in your own B2 bucket. Nothing is shared." },
                  { q: "What image sizes work best?", a: "1024x1024 for Flux models, 512x512 for SDXL Turbo. The system auto-selects based on model." },
                ].map((item) => (
                  <div key={item.q} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                    <p className="text-sm font-medium text-white">{item.q}</p>
                    <p className="text-xs text-gray-400 mt-1">{item.a}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeSection === "about" && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-white">About AI Studio</h2>
              <p className="text-sm text-gray-400">
                AI Studio is a commercial multi-tenant SaaS platform for AI-powered content production.
                Create, train, and deploy AI influencer content at scale — without needing to understand ML infrastructure.
              </p>
              <div className="grid grid-cols-2 gap-4 mt-4">
                <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                  <p className="text-xs text-gray-500">Version</p>
                  <p className="text-sm text-white mt-1">Phase 14</p>
                </div>
                <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                  <p className="text-xs text-gray-500">Stack</p>
                  <p className="text-sm text-white mt-1">Next.js + FastAPI + ComfyUI</p>
                </div>
                <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                  <p className="text-xs text-gray-500">GPU Provider</p>
                  <p className="text-sm text-white mt-1">Vast.ai + RunPod</p>
                </div>
                <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                  <p className="text-xs text-gray-500">Storage</p>
                  <p className="text-sm text-white mt-1">Backblaze B2</p>
                </div>
              </div>
              <div className="mt-4 flex gap-3">
                <a href="https://github.com/garymcdaniel7/ai-studio88" target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] px-3 py-1.5 text-xs text-gray-400 hover:text-white">
                  <ExternalLink className="h-3 w-3" /> GitHub
                </a>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
