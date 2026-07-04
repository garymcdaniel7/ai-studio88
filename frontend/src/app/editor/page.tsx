"use client";

import { useState, useRef } from "react";
import { Play, Pause, Scissors, Plus, Download, Film, Music, Type, ChevronLeft, ChevronRight } from "lucide-react";

interface TimelineClip {
  id: string;
  track: "video" | "audio" | "text";
  label: string;
  startFrame: number;
  durationFrames: number;
  color: string;
}

const defaultClips: TimelineClip[] = [
  { id: "v1", track: "video", label: "Clip 1", startFrame: 0, durationFrames: 90, color: "bg-purple-600" },
  { id: "v2", track: "video", label: "Clip 2", startFrame: 90, durationFrames: 60, color: "bg-purple-500" },
  { id: "a1", track: "audio", label: "Music Track", startFrame: 0, durationFrames: 150, color: "bg-blue-600" },
  { id: "t1", track: "text", label: "Title Card", startFrame: 10, durationFrames: 40, color: "bg-green-600" },
];

export default function EditorPage() {
  const [playing, setPlaying] = useState(false);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [clips, setClips] = useState<TimelineClip[]>(defaultClips);
  const [totalFrames] = useState(300);
  const scrubRef = useRef<HTMLDivElement>(null);

  function handleScrub(e: React.MouseEvent<HTMLDivElement>) {
    if (!scrubRef.current) return;
    const rect = scrubRef.current.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    setCurrentFrame(Math.round(pct * totalFrames));
  }

  function handleAddClip() {
    const newClip: TimelineClip = {
      id: `v${Date.now()}`,
      track: "video",
      label: `Clip ${clips.filter((c) => c.track === "video").length + 1}`,
      startFrame: currentFrame,
      durationFrames: 45,
      color: "bg-purple-400",
    };
    setClips([...clips, newClip]);
  }

  function handleCut() {
    // Cut the first video clip at current frame (simple implementation)
    const videoClips = clips.filter((c) => c.track === "video");
    const target = videoClips.find(
      (c) => currentFrame > c.startFrame && currentFrame < c.startFrame + c.durationFrames
    );
    if (!target) return;

    const leftDuration = currentFrame - target.startFrame;
    const rightDuration = target.durationFrames - leftDuration;
    const updated = clips.filter((c) => c.id !== target.id);
    updated.push({ ...target, durationFrames: leftDuration, label: target.label + " (L)" });
    updated.push({
      ...target,
      id: target.id + "-r",
      startFrame: currentFrame,
      durationFrames: rightDuration,
      label: target.label + " (R)",
    });
    setClips(updated);
  }

  async function handleExport() {
    try {
      const resp = await fetch("http://localhost:8000/api/v1/cinematic/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ timeline_id: "current", format: "mp4" }),
      });
      const data = await resp.json();
      alert(data.message || "Export started — check production queue.");
    } catch {
      alert("Backend not reachable. Export will be available when the render service is running.");
    }
  }

  const trackOrder: Array<{ type: "video" | "audio" | "text"; label: string; icon: typeof Film }> = [
    { type: "video", label: "Video", icon: Film },
    { type: "audio", label: "Audio", icon: Music },
    { type: "text", label: "Text", icon: Type },
  ];

  const frameToPct = (frame: number) => `${(frame / totalFrames) * 100}%`;

  return (
    <div className="flex flex-col h-[calc(100vh-64px)] space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Video Editor</h1>
          <p className="text-sm text-gray-500">Timeline-based editing for your AI productions.</p>
        </div>
        <button
          onClick={handleExport}
          className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700"
        >
          <Download className="h-4 w-4" /> Export
        </button>
      </div>

      {/* Preview Area */}
      <div className="flex-1 min-h-0 rounded-xl border border-white/[0.06] bg-[#0a0a1a] flex items-center justify-center overflow-hidden">
        <div className="text-center">
          <div className="w-[640px] h-[360px] bg-gradient-to-br from-[#1a1a3a] to-[#0d0d20] rounded-lg flex items-center justify-center border border-white/[0.04]">
            <div className="text-center">
              <Film className="h-16 w-16 text-gray-700 mx-auto mb-3" />
              <p className="text-sm text-gray-500">Preview</p>
              <p className="text-xs text-gray-600 mt-1">Frame {currentFrame} / {totalFrames}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Transport Controls */}
      <div className="flex items-center justify-center gap-3">
        <button className="p-2 text-gray-400 hover:text-white" onClick={() => setCurrentFrame(Math.max(0, currentFrame - 10))}>
          <ChevronLeft className="h-5 w-5" />
        </button>
        <button
          onClick={() => setPlaying(!playing)}
          className="flex items-center justify-center h-10 w-10 rounded-full bg-purple-600 text-white hover:bg-purple-700"
        >
          {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 ml-0.5" />}
        </button>
        <button className="p-2 text-gray-400 hover:text-white" onClick={() => setCurrentFrame(Math.min(totalFrames, currentFrame + 10))}>
          <ChevronRight className="h-5 w-5" />
        </button>
        <div className="w-px h-6 bg-white/[0.1] mx-2" />
        <button onClick={handleAddClip} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/[0.08] text-xs text-gray-300 hover:text-white hover:border-white/[0.15]">
          <Plus className="h-3.5 w-3.5" /> Add Clip
        </button>
        <button onClick={handleCut} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/[0.08] text-xs text-gray-300 hover:text-white hover:border-white/[0.15]">
          <Scissors className="h-3.5 w-3.5" /> Cut
        </button>
      </div>

      {/* Timeline */}
      <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 space-y-2">
        {/* Scrubber / Ruler */}
        <div
          ref={scrubRef}
          className="relative h-6 bg-white/[0.03] rounded cursor-pointer"
          onClick={handleScrub}
        >
          {/* Playhead */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-purple-500 z-10"
            style={{ left: frameToPct(currentFrame) }}
          />
          {/* Frame markers */}
          {Array.from({ length: 11 }).map((_, i) => (
            <span
              key={i}
              className="absolute bottom-0 text-[9px] text-gray-600 -translate-x-1/2"
              style={{ left: `${i * 10}%` }}
            >
              {Math.round((i / 10) * totalFrames)}
            </span>
          ))}
        </div>

        {/* Tracks */}
        {trackOrder.map((track) => (
          <div key={track.type} className="flex items-center gap-3">
            <div className="w-16 flex items-center gap-1.5 text-xs text-gray-500">
              <track.icon className="h-3.5 w-3.5" />
              {track.label}
            </div>
            <div className="relative flex-1 h-10 bg-white/[0.02] rounded border border-white/[0.04]">
              {clips
                .filter((c) => c.track === track.type)
                .map((clip) => (
                  <div
                    key={clip.id}
                    className={`absolute top-1 bottom-1 rounded ${clip.color} flex items-center px-2 text-[10px] text-white font-medium truncate`}
                    style={{
                      left: frameToPct(clip.startFrame),
                      width: frameToPct(clip.durationFrames),
                    }}
                  >
                    {clip.label}
                  </div>
                ))}
              {/* Playhead on track */}
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-purple-500/50"
                style={{ left: frameToPct(currentFrame) }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
