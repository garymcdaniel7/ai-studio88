"use client";

import { useRef } from "react";
import { Image as ImageIcon, Film, Loader2, Wand2 } from "lucide-react";
import { TalentSelector } from "./talent-selector";
import type { ModelOption, TalentOption } from "../_hooks/use-create-data";
import type { useVideoGeneration } from "../_hooks/use-video-generation";

interface VideoTabProps {
  apiBase: string;
  videoModelList: ModelOption[];
  talentList: TalentOption[];
  selectedTalents: string[];
  onChangeTalents: (next: string[]) => void;
  video: ReturnType<typeof useVideoGeneration>;
}

/**
 * Video generation tab — text-to-video card and image-to-video card.
 */
export function VideoTab({
  apiBase,
  videoModelList,
  talentList,
  selectedTalents,
  onChangeTalents,
  video,
}: VideoTabProps) {
  const videoImageInputRef = useRef<HTMLInputElement>(null);
  const {
    videoPrompt,
    setVideoPrompt,
    videoLoading,
    videoResult,
    selectedVideoModel,
    setSelectedVideoModel,
    videoDownloadUrl,
    videoDuration,
    setVideoDuration,
    videoWidth,
    setVideoWidth,
    videoHeight,
    setVideoHeight,
    videoSteps,
    setVideoSteps,
    videoGuidance,
    setVideoGuidance,
    videoFps,
    setVideoFps,
    videoSeed,
    setVideoSeed,
    videoImageFile,
    videoImagePreview,
    videoImageLoading,
    videoImageResult,
    videoMotionPrompt,
    setVideoMotionPrompt,
    handleGenerateVideo,
    handleVideoImageSelect,
    handleVideoImageDrop,
    handleAnimateImage,
  } = video;

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border-subtle bg-surface-raised p-6">
        <h3 className="text-sm font-semibold text-content-primary mb-1">Video from Text</h3>
        <p className="text-xs text-content-muted mb-4">Describe a scene — AI generates a video clip (up to 10s).</p>

        {/* Prompt + Model + Generate */}
        <div className="space-y-3">
          <div className="flex gap-3">
            <input
              value={videoPrompt}
              onChange={(e) => setVideoPrompt(e.target.value)}
              className="flex-1 rounded-lg border border-border-default bg-surface-hover px-4 py-3 text-sm text-content-secondary placeholder:text-content-muted outline-none focus:border-purple-500/50"
              placeholder="A woman walking through a luxury hotel lobby, cinematic..."
            />
            <select
              value={selectedVideoModel}
              onChange={(e) => setSelectedVideoModel(e.target.value)}
              className="rounded-lg border border-border-default bg-surface-raised px-3 py-2 text-sm text-content-secondary outline-none"
            >
              {videoModelList.map((m) => (
                <option key={m.id} value={m.id}>{m.name}{m.badge === "Loaded" ? " ✓" : m.badge ? ` (${m.badge})` : ""}</option>
              ))}
            </select>
            <button
              onClick={handleGenerateVideo}
              disabled={videoLoading || !videoPrompt.trim()}
              className="rounded-lg bg-purple-600 px-6 py-2 text-sm font-medium text-white hover:bg-purple-700 flex items-center gap-2 disabled:opacity-50"
            >
              {videoLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Film className="h-4 w-4" />}
              {videoLoading ? "Generating..." : "Generate"}
            </button>
          </div>

          {/* Talent Selection for Video */}
          <TalentSelector
            apiBase={apiBase}
            talentList={talentList}
            selectedTalents={selectedTalents}
            onChange={onChangeTalents}
          />

          {/* Video Options Grid */}
          <div className="rounded-lg border border-border-subtle bg-surface-hover p-4 space-y-3">
            <p className="text-xs font-semibold text-content-secondary">Video Settings</p>

            {/* Resolution + Duration */}
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-[10px] text-content-muted mb-1">Resolution</label>
                <select
                  value={`${videoWidth}x${videoHeight}`}
                  onChange={(e) => {
                    const [w, h] = e.target.value.split("x").map(Number);
                    setVideoWidth(w);
                    setVideoHeight(h);
                  }}
                  className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-1.5 text-xs text-content-secondary outline-none"
                >
                  <option value="480x832">480×832 (Portrait)</option>
                  <option value="832x480">832×480 (Landscape)</option>
                  <option value="720x720">720×720 (Square)</option>
                  <option value="1280x720">1280×720 (Wide)</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-content-muted mb-1">Duration</label>
                <select
                  value={videoDuration}
                  onChange={(e) => setVideoDuration(e.target.value)}
                  className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-1.5 text-xs text-content-secondary outline-none"
                >
                  <option value="2">2 sec</option>
                  <option value="4">4 sec</option>
                  <option value="6">6 sec</option>
                  <option value="8">8 sec</option>
                  <option value="10">10 sec (max)</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-content-muted mb-1">FPS</label>
                <select
                  value={videoFps}
                  onChange={(e) => setVideoFps(parseInt(e.target.value))}
                  className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-1.5 text-xs text-content-secondary outline-none"
                >
                  <option value="8">8 fps</option>
                  <option value="16">16 fps</option>
                  <option value="24">24 fps</option>
                </select>
              </div>
            </div>

            {/* Steps + Guidance + Seed */}
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-[10px] text-content-muted mb-1">Steps: {videoSteps}</label>
                <input type="range" min="10" max="50" value={videoSteps} onChange={(e) => setVideoSteps(parseInt(e.target.value))} className="w-full accent-purple-500" />
                <p className="text-[9px] text-content-muted">Recommended: 20-30</p>
              </div>
              <div>
                <label className="block text-[10px] text-content-muted mb-1">Guidance: {videoGuidance.toFixed(1)}</label>
                <input type="range" min="1" max="20" step="0.5" value={videoGuidance} onChange={(e) => setVideoGuidance(parseFloat(e.target.value))} className="w-full accent-purple-500" />
                <p className="text-[9px] text-content-muted">Default: 7.5 for WAN</p>
              </div>
              <div>
                <label className="block text-[10px] text-content-muted mb-1">Seed (-1 = random)</label>
                <input
                  type="number"
                  value={videoSeed}
                  onChange={(e) => setVideoSeed(parseInt(e.target.value))}
                  className="w-full rounded-lg border border-border-default bg-surface-hover px-2 py-1.5 text-xs text-content-secondary outline-none"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Video Loading State */}
        {videoLoading && (
          <div className="mt-4 rounded-xl border border-blue-500/30 bg-blue-500/5 p-6 text-center">
            <Loader2 className="h-8 w-8 animate-spin text-blue-500 mx-auto mb-3" />
            <p className="text-sm font-medium text-blue-300">Generating video with {selectedVideoModel}...</p>
            <p className="text-xs text-gray-500 mt-1">Video generation takes 5-50 minutes depending on length and quality.</p>
            <p className="text-[10px] text-gray-600 mt-2">Do not close this page. The video will appear below when ready.</p>
          </div>
        )}

        {/* Video Result Display */}
        {videoResult && !videoLoading && (
          <div className="mt-4 rounded-xl border border-border-subtle bg-surface-hover p-4">
            {videoResult.startsWith("Video generated") ? (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <span className="inline-flex items-center gap-1.5 rounded-lg bg-green-500/10 border border-green-500/20 px-3 py-1.5">
                    <svg className="h-3.5 w-3.5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                    <span className="text-[11px] text-green-400 font-medium">Complete</span>
                  </span>
                  <p className="text-xs text-content-tertiary">{videoResult}</p>
                </div>
                {videoDownloadUrl && (
                  <div className="rounded-lg bg-black/30 p-2">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={videoDownloadUrl}
                      alt="Generated video"
                      className="rounded-lg w-full max-w-lg mx-auto"
                    />
                    <div className="mt-2 flex justify-center gap-2">
                      <a
                        href={videoDownloadUrl}
                        download
                        className="inline-flex items-center gap-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] px-3 py-1.5 text-[11px] text-gray-300 hover:text-white hover:bg-white/[0.08]"
                      >
                        Download Video
                      </a>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-amber-300">{videoResult}</p>
            )}
          </div>
        )}
      </div>

      <div className="rounded-xl border border-border-subtle bg-surface-raised p-6">
        <h3 className="text-sm font-semibold text-content-primary mb-1">Video from Image</h3>
        <p className="text-xs text-content-muted mb-4">Upload or select an image to animate into video.</p>
        <input
          ref={videoImageInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleVideoImageSelect(file);
          }}
        />
        {/* Motion prompt */}
        <input
          value={videoMotionPrompt}
          onChange={(e) => setVideoMotionPrompt(e.target.value)}
          className="w-full rounded-lg border border-border-default bg-surface-hover px-4 py-2 text-sm text-content-secondary placeholder:text-content-muted outline-none focus:border-purple-500/50 mb-3"
          placeholder="Describe the motion: slow zoom in, hair blowing in wind, walking forward..."
        />
        <div className="flex gap-3">
          <div
            onClick={() => videoImageInputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleVideoImageDrop}
            className="flex-1 rounded-lg border-2 border-dashed border-border-strong bg-surface-hover p-8 text-center cursor-pointer hover:border-purple-500/30"
          >
            {videoImagePreview ? (
              <div className="space-y-2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={videoImagePreview} alt="Video source image preview" className="mx-auto h-20 w-20 rounded-lg object-cover" />
                <p className="text-xs text-content-secondary">{videoImageFile?.name}</p>
              </div>
            ) : (
              <>
                <ImageIcon className="h-8 w-8 text-content-muted mx-auto mb-2" />
                <p className="text-xs text-content-muted">Drop an image here or click to upload</p>
              </>
            )}
          </div>
          <button
            onClick={handleAnimateImage}
            disabled={!videoImageFile || videoImageLoading}
            className="self-end rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 flex items-center gap-2 disabled:opacity-50"
          >
            {videoImageLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
            {videoImageLoading ? "Uploading..." : "Animate"}
          </button>
        </div>
        {videoImageResult && (
          <div className="mt-3 rounded-lg border border-border-subtle bg-surface-hover p-3">
            <p className="text-xs text-content-secondary">{videoImageResult}</p>
          </div>
        )}
      </div>
    </div>
  );
}
