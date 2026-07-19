"use client";

import { useState, useEffect } from "react";
import { User, HelpCircle, BookOpen, Info, ExternalLink, Settings2 } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState("profile");
  const [totalGenerations, setTotalGenerations] = useState<string>("—");
  const [modelsTrained, setModelsTrained] = useState<string>("—");

  // Preferences state
  const [autoApproveLimit, setAutoApproveLimit] = useState("0.05");
  const [dailyBudget, setDailyBudget] = useState("10.00");
  const [defaultRecipe, setDefaultRecipe] = useState("auto");
  const [defaultFormat, setDefaultFormat] = useState("square");
  const [useTalentLora, setUseTalentLora] = useState(true);
  const [brainMode, setBrainMode] = useState("creative");
  const [llmProvider, setLlmProvider] = useState("gpu-ollama");

  useEffect(() => {
    async function loadProfileStats() {
      try {
        const jobsResp = await fetch(`${API_BASE}/api/v1/jobs?status=completed`);
        if (jobsResp.ok) {
          const data = await jobsResp.json();
          setTotalGenerations(String(Array.isArray(data) ? data.length : 0));
        }
      } catch {}
      try {
        const modelsResp = await fetch(`${API_BASE}/api/v1/models?type=lora`);
        if (modelsResp.ok) {
          const data = await modelsResp.json();
          setModelsTrained(String(Array.isArray(data) ? data.length : 0));
        }
      } catch {}
    }
    loadProfileStats();
  }, []);

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
            { key: "preferences", label: "Preferences", icon: Settings2 },
            { key: "help", label: "How to Use", icon: BookOpen },
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
                  <p className="text-lg font-medium text-white">My Profile</p>
                  <p className="text-sm text-gray-500">Studio Owner</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 mt-4">
                <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                  <p className="text-xs text-gray-500">Total Generations</p>
                  <p className="text-xl font-bold text-white mt-1">{totalGenerations}</p>
                </div>
                <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                  <p className="text-xs text-gray-500">Models Trained</p>
                  <p className="text-xl font-bold text-white mt-1">{modelsTrained}</p>
                </div>
              </div>
            </div>
          )}

          {activeSection === "preferences" && (
            <div className="space-y-6">
              <h2 className="text-lg font-semibold text-white">Preferences</h2>

              {/* AI Automation */}
              <div>
                <h3 className="text-sm font-medium text-gray-300 mb-3">AI Automation</h3>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-white">Auto-approve generation up to</p>
                      <p className="text-[10px] text-gray-500">Skip approval for generations below this cost</p>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="text-sm text-gray-400">$</span>
                      <input type="number" step="0.01" value={autoApproveLimit} onChange={(e) => setAutoApproveLimit(e.target.value)} className="w-20 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-sm text-white outline-none text-right" />
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-white">Daily budget limit</p>
                      <p className="text-[10px] text-gray-500">Stop all generation when this limit is reached</p>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="text-sm text-gray-400">$</span>
                      <input type="number" step="1" value={dailyBudget} onChange={(e) => setDailyBudget(e.target.value)} className="w-20 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-sm text-white outline-none text-right" />
                    </div>
                  </div>
                </div>
              </div>

              {/* Default Creative Settings */}
              <div>
                <h3 className="text-sm font-medium text-gray-300 mb-3">Default Creative Settings</h3>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm text-white">Preferred recipe</p>
                    <select value={defaultRecipe} onChange={(e) => setDefaultRecipe(e.target.value)} className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-sm text-white outline-none">
                      <option value="auto">Auto (AI picks best)</option>
                      <option value="recipe-magazine-cover">Magazine Cover</option>
                      <option value="recipe-golden-hour">Golden Hour</option>
                      <option value="recipe-fast-draft">Fast Draft</option>
                    </select>
                  </div>
                  <div className="flex items-center justify-between">
                    <p className="text-sm text-white">Default format</p>
                    <select value={defaultFormat} onChange={(e) => setDefaultFormat(e.target.value)} className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-sm text-white outline-none">
                      <option value="square">Square (1024x1024)</option>
                      <option value="portrait">Portrait (768x1344)</option>
                      <option value="landscape">Landscape (1344x768)</option>
                    </select>
                  </div>
                  <div className="flex items-center justify-between">
                    <p className="text-sm text-white">Always use talent LoRA when available</p>
                    <button onClick={() => setUseTalentLora(!useTalentLora)} className={`relative h-6 w-11 rounded-full transition-colors ${useTalentLora ? "bg-purple-600" : "bg-gray-700"}`}>
                      <span className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform ${useTalentLora ? "translate-x-5" : ""}`} />
                    </button>
                  </div>
                </div>
              </div>

              {/* Brain Preferences */}
              <div>
                <h3 className="text-sm font-medium text-gray-300 mb-3">Brain Preferences</h3>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm text-white">Default mode</p>
                    <select value={brainMode} onChange={(e) => setBrainMode(e.target.value)} className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-sm text-white outline-none">
                      <option value="creative">Creative</option>
                      <option value="prompt_engineer">Prompt Engineer</option>
                      <option value="story_assistant">Story Assistant</option>
                      <option value="production_advisor">Production Advisor</option>
                    </select>
                  </div>
                  <div className="flex items-center justify-between">
                    <p className="text-sm text-white">LLM Provider</p>
                    <select value={llmProvider} onChange={(e) => setLlmProvider(e.target.value)} className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-sm text-white outline-none">
                      <option value="gpu-ollama">GPU Ollama (dolphin-llama3)</option>
                      <option value="local-ollama">Local Ollama</option>
                      <option value="openrouter">OpenRouter (cloud)</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Save */}
              <button className="rounded-lg bg-purple-600 px-5 py-2 text-sm font-medium text-white hover:bg-purple-700">
                Save Preferences
              </button>
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
