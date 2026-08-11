"use client";

import {
  MessageSquare,
  Wand2,
  BookOpen,
  Film,
  Search,
  ImageIcon,
} from "lucide-react";

export interface BrainMode {
  name: string;
  desc: string;
  icon: typeof MessageSquare;
  key: string;
}

export const BRAIN_MODES: BrainMode[] = [
  { name: "Creative Chat", desc: "General conversations", icon: MessageSquare, key: "creative" },
  { name: "Prompt Engineer", desc: "Improve your prompts", icon: Wand2, key: "prompt_engineer" },
  { name: "Script Writer", desc: "Scripts, songs & screenplays", icon: BookOpen, key: "script_writer" },
  { name: "Story Assistant", desc: "Develop narratives", icon: Film, key: "story_assistant" },
  { name: "Production Advisor", desc: "Plan & optimize workflows", icon: Search, key: "production_advisor" },
  { name: "Image Analyzer", desc: "Analyze images & assets", icon: ImageIcon, key: "image_analyzer" },
];

export const WELCOME_MESSAGES: Record<string, string> = {
  creative: "Hey! 👋 Welcome to AI Studio. I'm your Creative Director AI. I can help you brainstorm ideas, explore concepts, develop campaigns, and push creative boundaries. What are you working on today?",
  prompt_engineer: "Let's build the perfect prompt. 🎯 Tell me what you want to create — describe the subject, mood, or concept — and I'll guide you toward a production-ready prompt optimized for Flux, SDXL, or WAN 2.1. Start simple, I'll refine it with you.",
  script_writer: "I'm your Script Writer. ✍️ I'm skilled in all genres — screenplays, songs, reels, commercials, TikTok hooks, YouTube scripts, R&B lyrics, and cinematic narratives. I'll ask probing questions to develop award-winning content. What are we creating together?",
  story_assistant: "I'm your Story Assistant. 📖 I help develop narratives for commercials, series, social content, and films. Whether it's a 15-second reel or a 10-episode series, let's build a compelling story. What's the concept?",
  production_advisor: "Production Advisor here. 📊 I help optimize your workflows, estimate GPU costs, plan pipelines, and schedule batch renders. What production challenge are you facing?",
  image_analyzer: "Image Analyzer ready. 🖼️ Describe an image or paste a reference, and I'll break down the composition, lighting, color palette, and suggest how to recreate or improve it with AI generation.",
};

interface ModeSelectorProps {
  currentMode: string;
  onModeChange: (mode: string) => void;
}

/**
 * Mode pills — compact horizontal selector for Brain modes.
 */
export function ModeSelector({ currentMode, onModeChange }: ModeSelectorProps) {
  return (
    <div className="flex items-center gap-1.5 px-6 py-2">
      {BRAIN_MODES.map((mode) => (
        <button
          key={mode.key}
          onClick={() => onModeChange(mode.key)}
          className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-all ${
            currentMode === mode.key
              ? "bg-purple-600/20 text-purple-300 border border-purple-500/40"
              : "text-gray-500 hover:text-gray-300 hover:bg-white/[0.04] border border-transparent"
          }`}
        >
          <mode.icon className="h-3 w-3" />
          {mode.name}
        </button>
      ))}
    </div>
  );
}
