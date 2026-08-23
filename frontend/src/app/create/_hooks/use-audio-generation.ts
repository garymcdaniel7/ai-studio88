"use client";

import { useState } from "react";
import type { VoiceOption } from "./use-create-data";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Voice generation state + handlers for the Create page audio tab.
 */
export function useAudioGeneration({
  elevenlabsVoices,
}: {
  elevenlabsVoices: VoiceOption[];
}) {
  const [voiceText, setVoiceText] = useState("");
  const [voiceLoading, setVoiceLoading] = useState(false);
  const [voiceResult, setVoiceResult] = useState<string | null>(null);
  const [selectedVoiceId, setSelectedVoiceId] = useState("rachel");
  const [selectedVoiceProvider, setSelectedVoiceProvider] = useState<"elevenlabs" | "moss">("elevenlabs");
  const [playingPreview, setPlayingPreview] = useState<string | null>(null);

  async function handleGenerateVoice() {
    if (!voiceText.trim() || voiceLoading) return;
    setVoiceLoading(true);
    setVoiceResult(null);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/audio/tts/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: voiceText,
          voice_id: selectedVoiceId,
          provider: selectedVoiceProvider === "moss" ? "moss-tts" : "elevenlabs",
        }),
      });
      const data = await resp.json();
      if (data.audio_base64) {
        // Set as playable audio data URL
        const mimeType = data.mime_type || "audio/wav";
        setVoiceResult(`data:${mimeType};base64,${data.audio_base64}`);
      } else {
        setVoiceResult(data.detail || data.message || "Generation failed — check provider status in Admin.");
      }
    } catch {
      setVoiceResult("Failed to generate speech. Is the backend running?");
    } finally {
      setVoiceLoading(false);
    }
  }

  function togglePreview() {
    const voice = elevenlabsVoices.find((v) => v.voice_id === selectedVoiceId);
    if (!voice?.preview_url) return;
    if (playingPreview === selectedVoiceId) {
      setPlayingPreview(null);
    } else {
      setPlayingPreview(selectedVoiceId);
      const audio = new Audio(voice.preview_url);
      audio.onended = () => setPlayingPreview(null);
      audio.play().catch(() => setPlayingPreview(null));
    }
  }

  async function saveVoiceToLibrary(): Promise<void> {
    // Save to B2 via the full TTS endpoint
    try {
      const resp = await fetch(`${API_BASE}/api/v1/audio/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: voiceText, voice_id: selectedVoiceId, provider: selectedVoiceProvider === "moss" ? "moss-tts" : "elevenlabs" }),
      });
      if (resp.ok) {
        const data = await resp.json();
        setVoiceResult(`Saved to library. Asset ID: ${data.asset_id || "saved"}`);
      }
    } catch {}
  }

  return {
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
  };
}
