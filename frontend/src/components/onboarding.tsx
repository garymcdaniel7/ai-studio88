"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Brain, Sparkles, Building2, Wrench, ArrowRight, X } from "lucide-react";

/**
 * Onboarding — First-run experience for new users.
 *
 * Shows when: no talent exists + no generation history + not dismissed
 * Asks: "What brings you here?" → sets default experience mode
 * Then guides to first action (Brain chat or Create)
 */

const ONBOARDING_DISMISSED_KEY = "ai_studio_onboarding_dismissed";

interface OnboardingProps {
  talentCount: number;
  jobCount: number;
}

export function Onboarding({ talentCount, jobCount }: OnboardingProps) {
  const [dismissed, setDismissed] = useState(true); // Start hidden until we check
  const [step, setStep] = useState<"persona" | "action">("persona");
  const [selectedPersona, setSelectedPersona] = useState<string | null>(null);

  useEffect(() => {
    // Only show if user is genuinely new (no talent, no jobs, not dismissed before)
    const wasDismissed = localStorage.getItem(ONBOARDING_DISMISSED_KEY);
    if (!wasDismissed && talentCount === 0 && jobCount === 0) {
      setDismissed(false);
    }
  }, [talentCount, jobCount]);

  function dismiss() {
    setDismissed(true);
    localStorage.setItem(ONBOARDING_DISMISSED_KEY, "true");
  }

  function selectPersona(persona: string) {
    setSelectedPersona(persona);
    setStep("action");
    // Store preference
    localStorage.setItem("ai_studio_user_type", persona);
  }

  if (dismissed) return null;

  const personas = [
    {
      id: "creator",
      icon: Sparkles,
      title: "I create AI content",
      desc: "Social media, campaigns, art, influencer content",
      color: "border-purple-500/30 bg-purple-500/5 hover:border-purple-500/60",
    },
    {
      id: "brand",
      icon: Building2,
      title: "I manage a brand",
      desc: "Product photos, marketing, campaigns at scale",
      color: "border-blue-500/30 bg-blue-500/5 hover:border-blue-500/60",
    },
    {
      id: "technical",
      icon: Wrench,
      title: "I'm technical",
      desc: "I know ComfyUI, models, LoRAs, and infrastructure",
      color: "border-amber-500/30 bg-amber-500/5 hover:border-amber-500/60",
    },
  ];

  const actionSuggestions: Record<string, { title: string; desc: string; href: string; cta: string }[]> = {
    creator: [
      { title: "Talk to your AI Creative Director", desc: "Describe what you want — the Brain handles everything", href: "/brain", cta: "Open Brain" },
      { title: "Create your first AI persona", desc: "Upload photos to train a unique AI talent", href: "/talent", cta: "Create Talent" },
    ],
    brand: [
      { title: "Start a campaign brief", desc: "Tell the Brain about your brand and products", href: "/brain?prompt=Help me plan a product campaign", cta: "Start Brief" },
      { title: "Upload product photos", desc: "Add your products as AI talent for generation", href: "/talent", cta: "Add Products" },
    ],
    technical: [
      { title: "Generate an image", desc: "Flux 2 Dev + Klein available. Full ComfyUI under the hood.", href: "/create", cta: "Create" },
      { title: "Check infrastructure", desc: "GPU workers, model loading, fleet management", href: "/admin", cta: "Admin Panel" },
    ],
  };

  return (
    <div className="rounded-2xl border border-purple-500/20 bg-gradient-to-br from-[#12122a] to-[#1a1a3a] p-8 relative overflow-hidden">
      {/* Background decoration */}
      <div className="absolute top-0 right-0 w-64 h-64 bg-purple-600/5 rounded-full blur-3xl" />
      <div className="absolute bottom-0 left-0 w-48 h-48 bg-blue-600/5 rounded-full blur-3xl" />

      {/* Dismiss button */}
      <button
        onClick={dismiss}
        className="absolute top-4 right-4 p-2 text-gray-500 hover:text-white transition-colors"
      >
        <X className="h-4 w-4" />
      </button>

      {step === "persona" && (
        <div className="relative">
          <div className="flex items-center gap-3 mb-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-600/20">
              <Brain className="h-5 w-5 text-purple-400" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">Welcome to AI Studio</h2>
              <p className="text-sm text-gray-400">Your AI Creative Operating System</p>
            </div>
          </div>

          <p className="text-gray-400 mt-4 mb-6">What brings you here? This helps us customize your experience.</p>

          <div className="grid grid-cols-3 gap-4">
            {personas.map((p) => (
              <button
                key={p.id}
                onClick={() => selectPersona(p.id)}
                className={`rounded-xl border p-5 text-left transition-all ${p.color} ${
                  selectedPersona === p.id ? "ring-2 ring-purple-500" : ""
                }`}
              >
                <p.icon className="h-6 w-6 text-white mb-3" />
                <p className="text-sm font-semibold text-white">{p.title}</p>
                <p className="text-xs text-gray-400 mt-1">{p.desc}</p>
              </button>
            ))}
          </div>

          <p className="text-[11px] text-gray-600 mt-4 text-center">
            You can change this anytime in Settings.
          </p>
        </div>
      )}

      {step === "action" && selectedPersona && (
        <div className="relative">
          <h2 className="text-lg font-bold text-white mb-1">Great! Here's how to get started:</h2>
          <p className="text-sm text-gray-400 mb-6">Pick one to begin — you can always come back to the other.</p>

          <div className="grid grid-cols-2 gap-4">
            {actionSuggestions[selectedPersona]?.map((action) => (
              <Link
                key={action.href}
                href={action.href}
                onClick={dismiss}
                className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-5 hover:border-purple-500/30 hover:bg-purple-500/5 transition-all group"
              >
                <p className="text-sm font-semibold text-white group-hover:text-purple-300 transition-colors">{action.title}</p>
                <p className="text-xs text-gray-500 mt-1">{action.desc}</p>
                <div className="flex items-center gap-1 mt-3 text-xs text-purple-400 font-medium">
                  {action.cta} <ArrowRight className="h-3 w-3" />
                </div>
              </Link>
            ))}
          </div>

          <button
            onClick={dismiss}
            className="mt-4 text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            Skip for now — I'll explore on my own
          </button>
        </div>
      )}
    </div>
  );
}
