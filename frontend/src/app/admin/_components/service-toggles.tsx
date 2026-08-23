import { Power } from "lucide-react";
import { ToggleSwitch } from "./toggle-switch";
import type { OllamaPreference } from "./types";

/**
 * ComfyUI + Ollama service toggles with smart GPU/local gating,
 * Ollama source badges, preference select, and install helper.
 */
export function ServiceToggles({
  gpuActive,
  ollamaLocal,
  ollamaSource,
  ollamaRemoteAvailable,
  ollamaPreference,
  serviceToggles,
  serviceToggling,
  onToggleService,
  onOllamaPreferenceChange,
  onCheckAgain,
}: {
  gpuActive: boolean;
  ollamaLocal: boolean;
  ollamaSource: string;
  ollamaRemoteAvailable: boolean;
  ollamaPreference: OllamaPreference;
  serviceToggles: Record<string, boolean>;
  serviceToggling: Record<string, boolean>;
  onToggleService: (serviceName: string) => void;
  onOllamaPreferenceChange: (pref: OllamaPreference) => void;
  onCheckAgain: () => void;
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-content-primary mb-3">Services</h3>
      <div className="grid grid-cols-2 gap-4">
        {/* ComfyUI Toggle */}
        <div className={`rounded-xl border p-5 flex items-center justify-between ${
          (gpuActive || serviceToggles.comfyui) ? "border-border-subtle bg-surface-raised" : "border-border-subtle bg-surface-sunken"
        }`}>
          <div className="flex items-center gap-3">
            <Power className={`h-5 w-5 ${
              serviceToggles.comfyui ? "text-status-success" : (gpuActive || serviceToggles.comfyui) ? "text-content-muted" : "text-gray-700"
            }`} />
            <div>
              <p className={`text-sm font-medium ${(gpuActive || serviceToggles.comfyui) ? "text-content-primary" : "text-content-muted"}`}>ComfyUI</p>
              <p className="text-xs text-content-muted">
                {serviceToggles.comfyui ? "Connected (localhost:8188)" : "Image & video generation engine"}
              </p>
              {!(gpuActive || serviceToggles.comfyui) && (
                <p className="text-[10px] text-amber-500/70 mt-0.5">Requires active GPU worker or SSH tunnel</p>
              )}
            </div>
          </div>
          <ToggleSwitch
            checked={serviceToggles.comfyui}
            onToggle={() => onToggleService("comfyui")}
            disabled={serviceToggling.comfyui || !(gpuActive || serviceToggles.comfyui)}
            ariaLabel="Toggle ComfyUI"
          />
        </div>

        {/* Ollama Toggle — Enhanced with source + preference */}
        <div className={`rounded-xl border p-5 ${
          (gpuActive || ollamaLocal || serviceToggles.ollama) ? "border-border-subtle bg-surface-raised" : "border-border-subtle bg-surface-sunken"
        }`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Power className={`h-5 w-5 ${
                serviceToggles.ollama ? "text-status-success" : (gpuActive || ollamaLocal) ? "text-content-muted" : "text-gray-700"
              }`} />
              <div>
                <p className={`text-sm font-medium ${(gpuActive || ollamaLocal || serviceToggles.ollama) ? "text-content-primary" : "text-content-muted"}`}>Ollama</p>
                <p className="text-xs text-content-muted">
                  {serviceToggles.ollama
                    ? `Active — ${ollamaSource === "local" ? "Local (localhost:11434)" : ollamaSource === "remote" ? "Remote (GPU Worker)" : "Connected"}`
                    : "LLM for AI Brain"}
                </p>
              </div>
            </div>
            <ToggleSwitch
              checked={serviceToggles.ollama}
              onToggle={() => onToggleService("ollama")}
              disabled={serviceToggling.ollama || !(gpuActive || ollamaLocal || serviceToggles.ollama)}
              ariaLabel="Toggle Ollama"
            />
          </div>

          {/* Source badges + preference */}
          <div className="mt-3 flex items-center gap-2">
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
              ollamaLocal ? "bg-green-500/10 text-green-400" : "bg-gray-700/50 text-gray-500"
            }`}>
              <span className={`h-1.5 w-1.5 rounded-full ${ollamaLocal ? "bg-green-400" : "bg-gray-600"}`} />
              Local
            </span>
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
              ollamaRemoteAvailable ? "bg-blue-500/10 text-blue-400" : "bg-gray-700/50 text-gray-500"
            }`}>
              <span className={`h-1.5 w-1.5 rounded-full ${ollamaRemoteAvailable ? "bg-blue-400" : "bg-gray-600"}`} />
              Remote
            </span>
            <select
              value={ollamaPreference}
              onChange={(e) => {
                const pref = e.target.value as OllamaPreference;
                onOllamaPreferenceChange(pref);
              }}
              className="ml-auto rounded-md border border-white/[0.08] bg-[#0d0d1f] px-2 py-0.5 text-[10px] text-gray-300 outline-none"
            >
              <option value="auto">Auto</option>
              <option value="local">Prefer Local</option>
              <option value="remote">Prefer Remote</option>
            </select>
          </div>

          {/* Not installed helper */}
          {!ollamaLocal && !ollamaRemoteAvailable && !serviceToggles.ollama && (
            <div className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5">
              <p className="text-[11px] text-amber-400 font-medium">Ollama not detected</p>
              <p className="text-[10px] text-gray-500 mt-0.5">
                Install locally for free, private AI chat.
              </p>
              <div className="flex gap-2 mt-2">
                <a
                  href="https://ollama.com/download"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded bg-purple-600/20 px-2 py-1 text-[10px] font-medium text-purple-400 hover:bg-purple-600/30 transition-colors"
                >
                  Download Ollama
                </a>
                <button
                  onClick={onCheckAgain}
                  className="rounded bg-white/[0.04] px-2 py-1 text-[10px] font-medium text-gray-400 hover:bg-white/[0.08] transition-colors"
                >
                  Check Again
                </button>
              </div>
            </div>
          )}

          {!(gpuActive || ollamaLocal || serviceToggles.ollama) && ollamaRemoteAvailable === false && ollamaLocal === false && (
            <p className="text-[10px] text-amber-500/70 mt-2">No GPU worker or local installation detected</p>
          )}
        </div>
      </div>
    </div>
  );
}
