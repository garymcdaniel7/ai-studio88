"use client";

import { Loader2, Mic, Music } from "lucide-react";
import { Select, SelectItem } from "@/components/ui/select";
import type { useAudioGeneration } from "../_hooks/use-audio-generation";
import type { MossVoiceOption, VoiceOption } from "../_hooks/use-create-data";

interface AudioTabProps {
  audio: ReturnType<typeof useAudioGeneration>;
  elevenlabsVoices: VoiceOption[];
  mossVoices: MossVoiceOption[];
}

/**
 * Voice & Music tab — speech generation (ElevenLabs / talent voices) plus the
 * disabled music-generation placeholder.
 */
export function AudioTab({ audio, elevenlabsVoices, mossVoices }: AudioTabProps) {
  const {
    voiceText,
    setVoiceText,
    voiceLoading,
    voiceResult,
    selectedVoiceId,
    setSelectedVoiceId,
    selectedVoiceProvider,
    setSelectedVoiceProvider,
    playingPreview,
    togglePreview,
    handleGenerateVoice,
    saveVoiceToLibrary,
  } = audio;

  return (
    <div className="grid grid-cols-2 gap-6">
      <div className="rounded-xl border border-border-subtle bg-surface-raised p-6">
        <Mic className="h-8 w-8 text-status-success mb-3" />
        <h3 className="text-lg font-semibold text-content-primary">Voice Generation</h3>
        <p className="text-sm text-content-muted mt-1">Generate speech from text with ElevenLabs or local XTTS.</p>
        <div className="mt-4 space-y-3">
          <textarea
            value={voiceText}
            onChange={(e) => setVoiceText(e.target.value)}
            className="w-full rounded-lg border border-border-default bg-surface-hover px-4 py-3 text-sm text-content-secondary placeholder:text-content-muted outline-none resize-none"
            rows={3}
            placeholder="Enter text to speak..."
          />
          <div className="space-y-2">
            {/* Provider toggle */}
            <div className="flex gap-1">
              <button
                onClick={() => setSelectedVoiceProvider("elevenlabs")}
                className={`px-3 py-1 rounded text-[10px] font-medium ${selectedVoiceProvider === "elevenlabs" ? "bg-green-600 text-white" : "bg-surface-hover text-content-muted"}`}
              >
                ElevenLabs ({elevenlabsVoices.length})
              </button>
              <button
                onClick={() => setSelectedVoiceProvider("moss")}
                className={`px-3 py-1 rounded text-[10px] font-medium ${selectedVoiceProvider === "moss" ? "bg-green-600 text-white" : "bg-surface-hover text-content-muted"}`}
              >
                Talent Voices ({mossVoices.length})
              </button>
            </div>
            <div className="flex gap-2">
              <Select
                value={selectedVoiceId}
                onValueChange={(v) => setSelectedVoiceId(String(v))}
                className="flex-1 rounded-lg border border-border-default bg-surface-raised px-3 py-2 text-sm text-content-secondary outline-none"
              >
                {selectedVoiceProvider === "elevenlabs" ? (
                  <>
                    <SelectItem value="rachel">Rachel (Default)</SelectItem>
                    {elevenlabsVoices.map((v) => (
                      <SelectItem key={v.voice_id} value={v.voice_id}>
                        {v.name} {v.labels?.gender ? `(${v.labels.gender})` : ""}
                      </SelectItem>
                    ))}
                  </>
                ) : (
                  <>
                    {mossVoices.length > 0 ? (
                      mossVoices.map((v) => (
                        <SelectItem key={v.id} value={v.id}>
                          {v.name} ({v.provider === "moss-voicegenerator" ? "Generated" : "Cloned"})
                        </SelectItem>
                      ))
                    ) : (
                      <SelectItem value="">No talent voices yet — create one on the Talent page</SelectItem>
                    )}
                  </>
                )}
                <SelectItem value="xtts_local">XTTS Local (Free)</SelectItem>
              </Select>
              {/* Preview button */}
              {selectedVoiceProvider === "elevenlabs" && elevenlabsVoices.find((v) => v.voice_id === selectedVoiceId)?.preview_url && (
                <button
                  onClick={togglePreview}
                  className="rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-content-tertiary hover:text-status-success hover:border-green-500/30"
                  title="Preview voice"
                >
                  {playingPreview === selectedVoiceId ? "⏹" : "▶"}
                </button>
              )}
              <button
                onClick={handleGenerateVoice}
                disabled={voiceLoading || !voiceText.trim()}
                className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 flex items-center gap-2 disabled:opacity-50"
              >
                {voiceLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                {voiceLoading ? "Generating..." : "Generate Speech"}
              </button>
            </div>
          </div>
          {voiceResult && (
            <div className="rounded-lg border border-border-subtle bg-surface-hover p-3 space-y-2">
              {voiceResult.startsWith("data:audio") ? (
                <>
                  <p className="text-xs text-status-success">Generated successfully</p>
                  <audio controls className="w-full h-8" src={voiceResult} />
                  <button
                    onClick={saveVoiceToLibrary}
                    className="w-full rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
                  >
                    Save to Library (B2)
                  </button>
                </>
              ) : (
                <p className="text-xs text-content-secondary">{voiceResult}</p>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-border-subtle bg-surface-raised p-6 relative">
        <span className="absolute top-3 right-3 rounded-full bg-amber-500/20 border border-amber-500/40 px-2 py-0.5 text-[10px] font-medium text-status-warning">Coming Soon</span>
        <Music className="h-8 w-8 text-amber-400/50 mb-3" />
        <h3 className="text-lg font-semibold text-white/60">Music Generation</h3>
        <p className="text-sm text-content-muted mt-1">AI music for soundtracks, intros, and background. Requires Suno or Udio provider.</p>
        <div className="mt-4 space-y-3 opacity-50 pointer-events-none">
          <input
            disabled
            className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 placeholder:text-gray-600 outline-none"
            placeholder="Describe the music: upbeat lo-fi for product reveal..."
          />
          <div className="flex gap-2">
            <Select disabled className="flex-1 rounded-lg border border-white/[0.08] bg-[#12122a] px-3 py-2 text-sm text-gray-300 outline-none">
              <SelectItem value="30s">30 seconds</SelectItem>
            </Select>
            <Select disabled className="flex-1 rounded-lg border border-white/[0.08] bg-[#12122a] px-3 py-2 text-sm text-gray-300 outline-none">
              <SelectItem value="cinematic">Cinematic</SelectItem>
            </Select>
            <button
              disabled
              className="rounded-lg bg-amber-600/50 px-4 py-2 text-sm font-medium text-white/50 cursor-not-allowed"
            >
              Generate
            </button>
          </div>
        </div>
        <p className="mt-3 text-[11px] text-content-muted">Configure a music provider in Admin → API Keys to enable this feature.</p>
      </div>
    </div>
  );
}
