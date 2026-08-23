"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useState } from "react";

// ---------------------------------------------------------------------------
// Voice Demo Button — Plays a sample phrase using the assigned voice
// ---------------------------------------------------------------------------

export function VoiceDemoButton({ voiceProfile, talentName }: { voiceProfile: Record<string, unknown>; talentName: string }) {
  const [playing, setPlaying] = useState(false);

  // Gender-aware sample phrases
  const FEMALE_PHRASES = [
    `Hi, I'm ${talentName}. This is how I sound.`,
    `Welcome to my world. I'm ${talentName}, and I'm excited to create with you.`,
    `Hey there! ${talentName} here. Let's make something beautiful today.`,
    `This is ${talentName} speaking. Ready when you are.`,
  ];
  const MALE_PHRASES = [
    `What's up, I'm ${talentName}. This is my voice.`,
    `Hey, ${talentName} here. Let's get to work.`,
    `This is ${talentName}. Ready to create something great.`,
    `${talentName} speaking. Let's make it happen.`,
  ];
  const NEUTRAL_PHRASES = [
    `Hello, I'm ${talentName}. This is a sample of my voice.`,
    `Hi there, ${talentName} here. This is how I sound.`,
    `This is ${talentName}. Nice to meet you.`,
  ];

  function getSamplePhrase(): string {
    const gender = String(voiceProfile.gender || "").toLowerCase();
    let phrases = NEUTRAL_PHRASES;
    if (gender.includes("female") || gender.includes("woman")) phrases = FEMALE_PHRASES;
    else if (gender.includes("male") || gender.includes("man")) phrases = MALE_PHRASES;
    return phrases[Math.floor(Math.random() * phrases.length)];
  }

  async function handlePlay() {
    if (playing) return;
    setPlaying(true);

    try {
      const provider = voiceProfile.provider as string;
      const phrase = getSamplePhrase();

      // Check if there's a saved sample URL in metadata
      const meta = (voiceProfile.metadata || {}) as Record<string, unknown>;
      const sampleUrl = meta.sample_url as string || meta.b2_url as string;

      if (sampleUrl) {
        // Play the saved sample directly
        const audio = new Audio(sampleUrl);
        audio.onended = () => setPlaying(false);
        audio.onerror = () => setPlaying(false);
        await audio.play();
        return;
      }

      // For ElevenLabs: use the preview URL if available
      const elevenVoice = meta.elevenlabs_voice as Record<string, unknown> | undefined;
      if (elevenVoice?.preview_url) {
        const audio = new Audio(elevenVoice.preview_url as string);
        audio.onended = () => setPlaying(false);
        audio.onerror = () => setPlaying(false);
        await audio.play();
        return;
      }

      // Generate a fresh sample via MOSS/provider
      const endpoint = provider === "elevenlabs"
        ? `${API_BASE}/api/v1/audio/tts/preview`
        : `${API_BASE}/api/v1/voices/moss/generate-speech`;

      const body = provider === "elevenlabs"
        ? { text: phrase, voice_id: voiceProfile.provider_voice_id, provider: "elevenlabs" }
        : { text: phrase, talent_id: voiceProfile.talent_id };

      const resp = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (resp.ok) {
        const data = await resp.json();
        const audioBase64 = data.audio_base64;
        if (audioBase64) {
          const audio = new Audio(`data:audio/wav;base64,${audioBase64}`);
          audio.onended = () => setPlaying(false);
          audio.onerror = () => setPlaying(false);
          await audio.play();
          return;
        }
      }
      setPlaying(false);
    } catch {
      setPlaying(false);
    }
  }

  return (
    <button
      onClick={handlePlay}
      disabled={playing}
      className="p-1.5 rounded-lg text-gray-400 hover:text-green-400 hover:bg-green-400/10 transition-colors disabled:opacity-50"
      title="Play voice demo"
    >
      {playing ? (
        <svg className="h-3.5 w-3.5 animate-pulse" fill="currentColor" viewBox="0 0 24 24"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
      ) : (
        <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
      )}
    </button>
  );
}
