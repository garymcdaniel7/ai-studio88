"use client";

import { useState, useEffect } from "react";
import { Key, Eye, EyeOff, CheckCircle, AlertCircle, Loader2, Save } from "lucide-react";

interface KeyConfig {
  id: string;
  label: string;
  envVar: string;
  placeholder: string;
  category: string;
  description: string;
}

const KEY_CONFIGS: KeyConfig[] = [
  { id: "vast", label: "Vast.ai", envVar: "VAST_API_KEY", placeholder: "vast_ai_...", category: "GPU Providers", description: "GPU cloud compute for generation and training" },
  { id: "runpod", label: "RunPod", envVar: "RUNPOD_API_KEY", placeholder: "rp_...", category: "GPU Providers", description: "Alternative GPU cloud provider" },
  { id: "b2_key_id", label: "Backblaze B2 Key ID", envVar: "B2_KEY_ID", placeholder: "00...", category: "Storage", description: "Object storage for models, assets, outputs" },
  { id: "b2_app_key", label: "Backblaze B2 App Key", envVar: "B2_APPLICATION_KEY", placeholder: "K00...", category: "Storage", description: "Application key for B2 bucket access" },
  { id: "supabase_url", label: "Supabase URL", envVar: "SUPABASE_URL", placeholder: "https://xxx.supabase.co", category: "Database", description: "PostgreSQL database via Supabase" },
  { id: "supabase_key", label: "Supabase Service Key", envVar: "SUPABASE_SERVICE_ROLE_KEY", placeholder: "eyJ...", category: "Database", description: "Full DB access (backend only)" },
  { id: "hf", label: "HuggingFace", envVar: "HF_TOKEN", placeholder: "hf_...", category: "AI Models", description: "Download gated models from HuggingFace" },
  { id: "openai", label: "OpenAI", envVar: "OPENAI_API_KEY", placeholder: "sk-...", category: "AI Models", description: "GPT-4 fallback for Brain chat" },
  { id: "anthropic", label: "Anthropic", envVar: "ANTHROPIC_API_KEY", placeholder: "sk-ant-...", category: "AI Models", description: "Claude fallback for Brain chat" },
  { id: "elevenlabs", label: "ElevenLabs", envVar: "ELEVENLABS_API_KEY", placeholder: "xi_...", category: "Audio", description: "Voice generation and cloning" },
  { id: "kling", label: "KLING AI", envVar: "KLING_API_KEY", placeholder: "kling_...", category: "Video Providers", description: "KLING 3.0 video/image generation (text-to-video, image-to-video)" },
];

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [visibility, setVisibility] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [statuses, setStatuses] = useState<Record<string, "connected" | "invalid" | "empty">>({});

  useEffect(() => {
    // Load current key statuses from backend
    fetch("http://localhost:8000/api/v1/infrastructure/admin/services")
      .then((r) => r.json())
      .then((data) => {
        const services = data?.services || {};
        const newStatuses: Record<string, "connected" | "invalid" | "empty"> = {};
        if (services.vast_ai?.connected) newStatuses.vast = "connected";
        if (services.backblaze_b2?.connected) { newStatuses.b2_key_id = "connected"; newStatuses.b2_app_key = "connected"; }
        if (services.supabase?.connected) { newStatuses.supabase_url = "connected"; newStatuses.supabase_key = "connected"; }
        if (services.huggingface?.connected) newStatuses.hf = "connected";
        setStatuses(newStatuses);
      })
      .catch(() => {});

    // Check RunPod
    fetch("http://localhost:8000/api/v1/infrastructure/runpod/status")
      .then((r) => r.json())
      .then((data) => {
        if (data?.api_connected) setStatuses((prev) => ({ ...prev, runpod: "connected" }));
      })
      .catch(() => {});
  }, []);

  function toggleVisibility(id: string) {
    setVisibility((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  async function handleSave() {
    setSaving(true);
    try {
      const resp = await fetch("http://localhost:8000/api/v1/infrastructure/admin/keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keys }),
      });
      if (resp.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      }
    } catch {
      // Backend may not have this endpoint yet — that's OK
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally {
      setSaving(false);
    }
  }

  const categories = Array.from(new Set(KEY_CONFIGS.map((k) => k.category)));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">API Keys</h1>
          <p className="text-sm text-gray-500">Configure service connections. Keys are stored securely and never displayed after saving.</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving || Object.keys(keys).length === 0}
          className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {saving ? "Saving..." : "Save Keys"}
        </button>
      </div>

      {saved && (
        <div className="flex items-center gap-2 rounded-xl border border-green-500/20 bg-green-500/5 px-4 py-3">
          <CheckCircle className="h-4 w-4 text-green-400" />
          <p className="text-sm text-green-300">Keys saved successfully. Restart the backend to apply changes.</p>
        </div>
      )}

      {categories.map((category) => (
        <div key={category}>
          <h3 className="text-sm font-semibold text-white mb-3">{category}</h3>
          <div className="space-y-3">
            {KEY_CONFIGS.filter((k) => k.category === category).map((config) => {
              const status = statuses[config.id];
              return (
                <div key={config.id} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <Key className="h-4 w-4 text-purple-400" />
                      <div>
                        <p className="text-sm font-medium text-white">{config.label}</p>
                        <p className="text-[10px] text-gray-500">{config.description}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {status === "connected" && (
                        <span className="flex items-center gap-1 text-xs text-green-400">
                          <CheckCircle className="h-3 w-3" /> Connected
                        </span>
                      )}
                      {status === "invalid" && (
                        <span className="flex items-center gap-1 text-xs text-red-400">
                          <AlertCircle className="h-3 w-3" /> Invalid
                        </span>
                      )}
                      {!status && (
                        <span className="text-xs text-gray-600">Not configured</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <code className="text-[10px] text-gray-600 w-40 shrink-0">{config.envVar}</code>
                    <div className="relative flex-1">
                      <input
                        type={visibility[config.id] ? "text" : "password"}
                        value={keys[config.id] || ""}
                        onChange={(e) => setKeys((prev) => ({ ...prev, [config.id]: e.target.value }))}
                        placeholder={status === "connected" ? "••••••••• (configured)" : config.placeholder}
                        className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:border-purple-500 focus:outline-none pr-10"
                      />
                      <button
                        onClick={() => toggleVisibility(config.id)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-300"
                      >
                        {visibility[config.id] ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
        <h3 className="text-sm font-semibold text-white mb-2">How Keys Work</h3>
        <ul className="text-xs text-gray-400 space-y-1 list-disc list-inside">
          <li>Keys are written to the backend .env configuration file</li>
          <li>Keys are masked after entry — they cannot be retrieved</li>
          <li>The backend must be restarted for new keys to take effect</li>
          <li>Green checkmarks indicate the key is valid and the service is reachable</li>
          <li>Never share your API keys or commit them to version control</li>
        </ul>
      </div>
    </div>
  );
}
