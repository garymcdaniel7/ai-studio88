/**
 * Brain Page Constants — Story 136.a
 *
 * Mode definitions and welcome messages extracted from page.tsx.
 */

import {
  MessageSquare,
  Wand2,
  BookOpen,
  Film,
  Search,
  ImageIcon,
} from "lucide-react";
import type { BrainMode } from "./types";

export const WELCOME_MESSAGES: Record<string, string> = {
  creative:
    "Hey! 👋 Welcome to AI Studio. I'm your Creative Director AI. I can help you brainstorm ideas, explore concepts, develop campaigns, and push creative boundaries. What are you working on today?",
  prompt_engineer:
    "Let's build the perfect prompt. 🎯 Tell me what you want to create — describe the subject, mood, or concept — and I'll guide you toward a production-ready prompt optimized for Flux, SDXL, or WAN 2.1. Start simple, I'll refine it with you.",
  script_writer:
    "I'm your Script Writer. ✍️ I'm skilled in all genres — screenplays, songs, reels, commercials, TikTok hooks, YouTube scripts, R&B lyrics, and cinematic narratives. I'll ask probing questions to develop award-winning content. What are we creating together?",
  story_assistant:
    "I'm your Story Assistant. 📖 I help develop narratives for commercials, series, social content, and films. Whether it's a 15-second reel or a 10-episode series, let's build a compelling story. What's the concept?",
  production_advisor:
    "Production Advisor here. 📊 I help optimize your workflows, estimate GPU costs, plan pipelines, and schedule batch renders. What production challenge are you facing?",
  image_analyzer:
    "Image Analyzer ready. 🖼️ Describe an image or paste a reference, and I'll break down the composition, lighting, color palette, and suggest how to recreate or improve it with AI generation.",
};

export const BRAIN_MODES: BrainMode[] = [
  { name: "Creative Chat", desc: "General conversations", icon: MessageSquare, key: "creative" },
  { name: "Prompt Engineer", desc: "Improve your prompts", icon: Wand2, key: "prompt_engineer" },
  { name: "Script Writer", desc: "Scripts, songs & screenplays", icon: BookOpen, key: "script_writer" },
  { name: "Story Assistant", desc: "Develop narratives", icon: Film, key: "story_assistant" },
  { name: "Production Advisor", desc: "Plan & optimize workflows", icon: Search, key: "production_advisor" },
  { name: "Image Analyzer", desc: "Analyze images & assets", icon: ImageIcon, key: "image_analyzer" },
];

export const COLLECTION_COLORS = [
  "#8b5cf6",
  "#3b82f6",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#ec4899",
];

export const QUICK_ACTIONS = [
  { label: "Create Storyboard", prompt: "Help me create a storyboard for a short video. Ask me about the concept, target audience, and mood." },
  { label: "Generate Prompt", prompt: "Help me write an optimized image generation prompt. Ask me what I want to create." },
  { label: "Brainstorm Ideas", prompt: "Let's brainstorm creative content ideas together. What's the project or campaign about?" },
  { label: "Suggest Music", prompt: "Suggest music tracks or instrumentals for my video project. What's the mood and genre?" },
];

export const LOADING_MESSAGES: Record<string, string> = {
  creative: "Crafting a creative response...",
  prompt_engineer: "Optimizing your prompt...",
  story_assistant: "Developing narrative...",
  production_advisor: "Analyzing your workflow...",
  image_analyzer: "Analyzing visual content...",
  script_writer: "Processing your request...",
};
