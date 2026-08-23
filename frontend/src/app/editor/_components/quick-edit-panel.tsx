"use client";

/**
 * Quick Edit Panel — Upload video, apply ffmpeg transforms, export.
 * Extracted verbatim from editor/page.tsx.
 */

import { useRef, useState } from "react";
import {
  Download,
  Film,
  Gauge,
  Loader2,
  Palette,
  Scissors,
  Type,
  Upload,
} from "lucide-react";
import { authFetch } from "@/lib/api";
import { API_BASE } from "./editor-types";

export function QuickEditPanel() {
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Transform settings
  const [trimStart, setTrimStart] = useState("0");
  const [trimEnd, setTrimEnd] = useState("");
  const [speed, setSpeed] = useState("1.0");
  const [resolution, setResolution] = useState("original");
  const [colorGrade, setColorGrade] = useState("none");
  const [textOverlay, setTextOverlay] = useState("");
  const [textFont, setTextFont] = useState("Arial");

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file && file.type.startsWith("video/")) {
      setVideoFile(file);
      setVideoUrl(URL.createObjectURL(file));
      setResult(null);
    }
  }

  async function handleProcess() {
    if (!videoFile) return;
    setProcessing(true);
    setResult(null);

    try {
      // Upload the video first
      const formData = new FormData();
      formData.append("file", videoFile);
      formData.append("asset_type", "video");

      const uploadResp = await authFetch(`${API_BASE}/api/v1/assets`, {
        method: "POST",
        body: formData,
      });
      const uploadData = await uploadResp.json();
      const assetId = uploadData?.id || uploadData?.asset_id;

      // Submit transform job
      const transformResp = await authFetch(`${API_BASE}/api/v1/video/transform`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          asset_id: assetId,
          transform: {
            trim_start: trimStart,
            trim_end: trimEnd || undefined,
            speed: parseFloat(speed),
            resolution: resolution !== "original" ? resolution : undefined,
            color_grade: colorGrade !== "none" ? colorGrade : undefined,
            text_overlay: textOverlay || undefined,
            text_font: textFont || undefined,
          },
          output_format: "mp4",
        }),
      });
      const data = await transformResp.json();
      setResult(data.output_url || data.message || "Processing complete");
    } catch {
      setResult("Processing failed. Is the backend running?");
    } finally {
      setProcessing(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Quick Edit</h2>
        <p className="text-sm text-gray-500">Upload a video → apply transforms → export via FFmpeg on GPU.</p>
      </div>

      <div className="grid grid-cols-[1fr_350px] gap-6">
        {/* Preview / Upload Area */}
        <div className="space-y-4">
          <div
            onClick={() => fileRef.current?.click()}
            className="aspect-video rounded-xl border-2 border-dashed border-white/[0.1] bg-[#0a0a1a] flex items-center justify-center cursor-pointer hover:border-purple-500/30 transition-colors overflow-hidden"
          >
            {videoUrl ? (
              <video src={videoUrl} controls className="w-full h-full object-contain rounded-lg" />
            ) : (
              <div className="text-center">
                <Upload className="h-12 w-12 text-gray-600 mx-auto mb-3" />
                <p className="text-sm text-gray-400">Drop a video or click to upload</p>
                <p className="text-xs text-gray-600 mt-1">MP4, MOV, WEBM — processed via FFmpeg on GPU</p>
              </div>
            )}
          </div>
          <input ref={fileRef} type="file" accept="video/*" className="hidden" onChange={handleFileSelect} />

          {videoFile && (
            <div className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-[#12122a] px-4 py-2">
              <div>
                <p className="text-sm text-white">{videoFile.name}</p>
                <p className="text-xs text-gray-500">{(videoFile.size / (1024 * 1024)).toFixed(1)} MB</p>
              </div>
              <button
                onClick={handleProcess}
                disabled={processing}
                className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
              >
                {processing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                {processing ? "Processing..." : "Export"}
              </button>
            </div>
          )}

          {result && (
            <div className="rounded-lg border border-green-500/20 bg-green-500/5 px-4 py-3 space-y-2">
              <p className="text-sm text-green-300">Export Complete</p>
              {result.startsWith("http") ? (
                <div className="space-y-2">
                  <video src={result} controls className="w-full rounded-lg max-h-48" />
                  <a href={result} download className="inline-flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-xs font-medium text-white hover:bg-green-700">
                    <Download className="h-3.5 w-3.5" /> Download Video
                  </a>
                </div>
              ) : (
                <p className="text-xs text-gray-400">{result}</p>
              )}
            </div>
          )}
        </div>

        {/* Transform Controls */}
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5 space-y-4">
          <h3 className="text-sm font-semibold text-white">Transforms</h3>

          {/* Trim */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Scissors className="h-3.5 w-3.5 text-purple-400" />
              <label className="text-xs font-medium text-gray-300">Trim</label>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <span className="text-[10px] text-gray-500">Start (s)</span>
                <input type="number" step="0.1" min="0" value={trimStart} onChange={(e) => setTrimStart(e.target.value)} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-gray-300 outline-none" />
              </div>
              <div>
                <span className="text-[10px] text-gray-500">End (s)</span>
                <input type="number" step="0.1" min="0" value={trimEnd} onChange={(e) => setTrimEnd(e.target.value)} placeholder="end" className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-gray-300 outline-none placeholder:text-gray-600" />
              </div>
            </div>
          </div>

          {/* Speed */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Gauge className="h-3.5 w-3.5 text-blue-400" />
              <label className="text-xs font-medium text-gray-300">Speed: {speed}x</label>
            </div>
            <input type="range" min="0.25" max="4" step="0.25" value={speed} onChange={(e) => setSpeed(e.target.value)} className="w-full accent-purple-500" />
            <div className="flex justify-between text-[9px] text-gray-600 mt-0.5">
              <span>0.25x (slow-mo)</span><span>4x (timelapse)</span>
            </div>
          </div>

          {/* Resolution */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Film className="h-3.5 w-3.5 text-green-400" />
              <label className="text-xs font-medium text-gray-300">Resolution</label>
            </div>
            <select value={resolution} onChange={(e) => setResolution(e.target.value)} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-gray-300 outline-none">
              <option value="original">Original</option>
              <option value="1920x1080">1080p (1920×1080)</option>
              <option value="1280x720">720p (1280×720)</option>
              <option value="3840x2160">4K (3840×2160)</option>
              <option value="1080x1920">Vertical 1080p (9:16)</option>
              <option value="1080x1080">Square (1:1)</option>
            </select>
          </div>

          {/* Color Grade */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Palette className="h-3.5 w-3.5 text-amber-400" />
              <label className="text-xs font-medium text-gray-300">Color Grade</label>
            </div>
            <select value={colorGrade} onChange={(e) => setColorGrade(e.target.value)} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-gray-300 outline-none">
              <option value="none">None</option>
              <option value="cinematic">Cinematic (Teal & Orange)</option>
              <option value="vintage">Vintage Film</option>
              <option value="bw">Black & White</option>
              <option value="warm">Warm / Golden Hour</option>
              <option value="cool">Cool / Blue Hour</option>
              <option value="high-contrast">High Contrast</option>
              <option value="desaturated">Desaturated</option>
            </select>
          </div>

          {/* Text Overlay */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Type className="h-3.5 w-3.5 text-pink-400" />
              <label className="text-xs font-medium text-gray-300">Text Overlay</label>
            </div>
            <input type="text" value={textOverlay} onChange={(e) => setTextOverlay(e.target.value)} placeholder="Add text..." className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-gray-300 outline-none placeholder:text-gray-600" />
            <select value={textFont} onChange={(e) => setTextFont(e.target.value)} className="w-full mt-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-gray-300 outline-none">
              <option value="Arial">Arial (Clean)</option>
              <option value="Helvetica">Helvetica (Modern)</option>
              <option value="Georgia">Georgia (Serif)</option>
              <option value="Courier">Courier (Monospace)</option>
              <option value="Impact">Impact (Bold)</option>
              <option value="Comic Sans MS">Comic Sans (Casual)</option>
              <option value="Times New Roman">Times New Roman (Classic)</option>
              <option value="Futura">Futura (Geometric)</option>
            </select>
          </div>

          {/* Info */}
          <div className="rounded-lg border border-white/[0.04] bg-white/[0.01] p-3">
            <p className="text-[10px] text-gray-500">
              Transforms are applied server-side via FFmpeg on the GPU worker. Upload → process → download the result.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
