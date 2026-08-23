"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useEffect, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { VoiceDemoButton } from "./voice-demo-button";

// ---------------------------------------------------------------------------
// Talent Voice Section — ElevenLabs voice browser + assignment
// ---------------------------------------------------------------------------

export function TalentVoiceSection({ talentId, talentName }: { talentId: string; talentName: string }) {
  const [voices, setVoices] = useState<Record<string, unknown>[]>([]);
  const [assignedVoices, setAssignedVoices] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [assigning, setAssigning] = useState<string | null>(null);
  const [showCreateVoice, setShowCreateVoice] = useState(false);
  const [voiceDesc, setVoiceDesc] = useState("");
  const [voiceName, setVoiceName] = useState("");
  const [creating, setCreating] = useState(false);
  const [voiceMode, setVoiceMode] = useState<"generate" | "clone">("generate");
  const [cloneSample, setCloneSample] = useState<File | null>(null);
  const [previewAudio, setPreviewAudio] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/v1/voices/elevenlabs`).then((r) => r.json()),
      fetch(`${API_BASE}/api/v1/voice-profiles?talent_id=${talentId}`).then((r) => r.json()),
    ])
      .then(([elevenData, profileData]) => {
        setVoices(elevenData?.voices || []);
        setAssignedVoices(Array.isArray(profileData) ? profileData : []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [talentId]);

  async function assignVoice(voice: Record<string, unknown>) {
    setAssigning(voice.voice_id as string);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/voice-profiles`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: `${talentName} - ${voice.name}`,
          talent_id: talentId,
          provider: "elevenlabs",
          provider_voice_id: voice.voice_id,
          voice_type: "character",
          language: "en",
          gender: (voice.labels as Record<string, string>)?.gender || "",
          accent: (voice.labels as Record<string, string>)?.accent || "",
          metadata: { elevenlabs_voice: voice },
        }),
      });
      if (resp.ok) {
        const profile = await resp.json();
        setAssignedVoices((prev) => [...prev, profile]);
      }
    } catch {}
    setAssigning(null);
  }

  async function removeVoice(profileId: string) {
    try {
      await fetch(`${API_BASE}/api/v1/voice-profiles/${profileId}`, { method: "DELETE" });
      setAssignedVoices((prev) => prev.filter((v) => v.id !== profileId));
    } catch {}
  }

  if (loading) {
    return <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin text-purple-500" /></div>;
  }

  const assignedIds = new Set(assignedVoices.map((v) => v.provider_voice_id));

  return (
    <div className="space-y-4">
      {/* Create Voice Button */}
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-gray-400 uppercase">Voice Management</p>
        <button
          onClick={() => setShowCreateVoice(true)}
          className="flex items-center gap-1.5 rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
        >
          <Sparkles className="h-3 w-3" /> Create Voice (MOSS)
        </button>
      </div>

      {/* Create Voice Modal — Generate or Clone */}
      {showCreateVoice && (
        <div className="rounded-lg border border-green-500/20 bg-green-500/5 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-green-300">Create Voice for {talentName}</p>
            <button onClick={() => setShowCreateVoice(false)} className="text-xs text-gray-500 hover:text-white">&times;</button>
          </div>

          {/* Mode toggle: Generate vs Clone */}
          <div className="flex gap-2">
            <button
              onClick={() => setVoiceMode("generate")}
              className={`flex-1 rounded-lg px-3 py-2 text-xs font-medium border transition-colors ${voiceMode === "generate" ? "bg-green-600/20 border-green-500/40 text-green-300" : "border-white/[0.08] text-gray-400 hover:text-white"}`}
            >
              Generate from Description
            </button>
            <button
              onClick={() => setVoiceMode("clone")}
              className={`flex-1 rounded-lg px-3 py-2 text-xs font-medium border transition-colors ${voiceMode === "clone" ? "bg-purple-600/20 border-purple-500/40 text-purple-300" : "border-white/[0.08] text-gray-400 hover:text-white"}`}
            >
              Clone from Audio Sample
            </button>
          </div>

          {voiceMode === "generate" && (
            <div className="space-y-2">
              <input value={voiceName} onChange={(e) => setVoiceName(e.target.value)} placeholder={`${talentName}'s Voice`} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-white placeholder:text-gray-600 outline-none" />
              <input value={voiceDesc} onChange={(e) => setVoiceDesc(e.target.value)} placeholder="Warm female voice, mid-30s, confident, slight accent..." className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-white placeholder:text-gray-600 outline-none" />
            </div>
          )}

          {voiceMode === "clone" && (
            <div className="space-y-2">
              <input value={voiceName} onChange={(e) => setVoiceName(e.target.value)} placeholder={`${talentName}'s Voice (cloned)`} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-white placeholder:text-gray-600 outline-none" />
              <label className="block">
                <span className="text-[10px] text-gray-400">Upload audio sample (6+ seconds)</span>
                <input
                  type="file"
                  accept="audio/*"
                  className="mt-1 w-full text-xs text-gray-400 file:mr-2 file:rounded-lg file:border-0 file:bg-purple-600 file:px-3 file:py-1.5 file:text-xs file:text-white file:cursor-pointer"
                  onChange={(e) => setCloneSample(e.target.files?.[0] || null)}
                />
              </label>
              {cloneSample && <p className="text-[10px] text-green-400">Selected: {cloneSample.name}</p>}
            </div>
          )}

          {/* Preview Audio Player */}
          {previewAudio && (
            <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
              <p className="text-[10px] text-gray-400 mb-1">Preview:</p>
              <audio controls className="w-full h-8" src={previewAudio} />
              <button
                onClick={async () => {
                  // Save to B2
                  try {
                    const resp = await fetch(`${API_BASE}/api/v1/voices/moss/generate-speech`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ text: "Hello, this is a sample of my voice.", talent_id: talentId, save: true }),
                    });
                    if (resp.ok) {
                      const data = await resp.json();
                      if (data.saved) {
                        setAssignedVoices((prev) => [...prev, ...(data.profile ? [data.profile] : [])]);
                      }
                    }
                  } catch {}
                }}
                className="mt-2 w-full rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
              >
                Save to Library
              </button>
            </div>
          )}

          <div className="flex gap-2">
            <button
              onClick={async () => {
                setCreating(true);
                setPreviewAudio(null);
                try {
                  if (voiceMode === "generate") {
                    if (!voiceDesc.trim()) { setCreating(false); return; }
                    const resp = await fetch(`${API_BASE}/api/v1/voices/moss/create-voice`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ description: voiceDesc, name: voiceName || `${talentName}'s Voice`, talent_id: talentId }),
                    });
                    if (resp.ok) {
                      const data = await resp.json();
                      // If we got a sample URL, set preview
                      if (data.sample_url) {
                        setPreviewAudio(data.sample_url);
                      }
                      setAssignedVoices((prev) => [...prev, data.profile || data]);
                      setVoiceDesc("");
                      setVoiceName("");
                    }
                  } else {
                    // Clone mode — upload sample and generate speech
                    if (!cloneSample) { setCreating(false); return; }
                    // Upload sample file first
                    const formData = new FormData();
                    formData.append("file", cloneSample);
                    const uploadResp = await fetch(`${API_BASE}/api/v1/talent/${talentId}/media`, { method: "POST", body: formData });
                    if (uploadResp.ok) {
                      const asset = await uploadResp.json();
                      const sampleUrl = asset.public_url;
                      // Now generate speech with this sample as voice reference
                      const genResp = await fetch(`${API_BASE}/api/v1/voices/moss/generate-speech`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ text: "Hello, this is a sample of my cloned voice.", voice_sample_url: sampleUrl, talent_id: talentId, consent_acknowledged: true }),
                      });
                      if (genResp.ok) {
                        const genData = await genResp.json();
                        if (genData.audio_base64) {
                          setPreviewAudio(`data:audio/wav;base64,${genData.audio_base64}`);
                        }
                        // Create voice profile
                        const profileResp = await fetch(`${API_BASE}/api/v1/voice-profiles`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ name: voiceName || `${talentName}'s Voice (cloned)`, talent_id: talentId, provider: "moss-tts", voice_type: "cloned", metadata: { sample_url: sampleUrl, clone_source: cloneSample.name } }),
                        });
                        if (profileResp.ok) {
                          const profile = await profileResp.json();
                          setAssignedVoices((prev) => [...prev, profile]);
                        }
                      }
                    }
                    setCloneSample(null);
                    setVoiceName("");
                  }
                } catch {}
                setCreating(false);
              }}
              disabled={creating || (voiceMode === "generate" ? !voiceDesc.trim() : !cloneSample)}
              className="rounded-lg bg-green-600 px-4 py-2 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
            >
              {creating ? "Processing..." : voiceMode === "generate" ? "Generate Voice" : "Clone Voice"}
            </button>
            <button onClick={() => { setShowCreateVoice(false); setPreviewAudio(null); }} className="rounded-lg border border-white/[0.08] px-4 py-2 text-xs text-gray-400 hover:text-white">Cancel</button>
          </div>
        </div>
      )}

      {/* Assigned voices */}
      {assignedVoices.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase mb-2">Assigned Voices</p>
          <div className="space-y-2">
            {assignedVoices.map((v) => (
              <div key={v.id as string} className="rounded-lg border border-green-500/20 bg-green-500/5 px-3 py-2">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-white">{v.name as string}</p>
                    <p className="text-[10px] text-gray-400">
                      {v.provider as string} &middot; {v.language as string || "en"} &middot; {v.gender as string || "—"}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <VoiceDemoButton voiceProfile={v} talentName={talentName} />
                    <button
                      onClick={() => removeVoice(v.id as string)}
                      className="text-xs text-red-400 hover:text-red-300"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Browse ElevenLabs voices */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase mb-2">
          ElevenLabs Voices ({voices.length} available)
        </p>
        <div className="max-h-[300px] overflow-y-auto space-y-1.5 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2">
          {voices.map((v) => {
            const voiceId = v.voice_id as string;
            const isAssigned = assignedIds.has(voiceId);
            const labels = (v.labels || {}) as Record<string, string>;
            return (
              <div
                key={voiceId}
                className={`flex items-center justify-between rounded-lg px-3 py-2 ${
                  isAssigned ? "bg-green-500/10 border border-green-500/20" : "hover:bg-white/[0.04]"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-white truncate">{v.name as string}</p>
                  <p className="text-[10px] text-gray-500">
                    {labels.accent || ""} {labels.gender || ""} {labels.age || ""} &middot; {labels.use_case || labels.description || ""}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {(v.preview_url as string) && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        const audio = new Audio(v.preview_url as string);
                        audio.play().catch(() => {});
                      }}
                      className="p-1 rounded text-gray-500 hover:text-purple-400 hover:bg-purple-400/10"
                      title="Play demo"
                    >
                      <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                    </button>
                  )}
                  {isAssigned ? (
                    <span className="text-[10px] text-green-400 font-medium">Assigned</span>
                  ) : (
                    <button
                      onClick={() => assignVoice(v)}
                      disabled={assigning === voiceId}
                      className="rounded-lg bg-purple-600 px-3 py-1 text-[10px] font-medium text-white hover:bg-purple-700 disabled:opacity-50"
                    >
                      {assigning === voiceId ? "..." : "Assign"}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
          {voices.length === 0 && (
            <p className="text-xs text-gray-500 text-center py-4">
              No ElevenLabs voices found. Check your API key in Admin settings.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
