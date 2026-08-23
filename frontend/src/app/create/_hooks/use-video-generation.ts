"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Video generation state + handlers for the Create page
 * (text-to-video and image-to-video).
 */
export function useVideoGeneration({ selectedTalents }: { selectedTalents: string[] }) {
  const [videoPrompt, setVideoPrompt] = useState("");
  const [videoLoading, setVideoLoading] = useState(false);
  const [videoResult, setVideoResult] = useState<string | null>(null);
  const [selectedVideoModel, setSelectedVideoModel] = useState("wan2.2-5b");
  const [videoDownloadUrl, setVideoDownloadUrl] = useState<string | null>(null);
  const [videoDuration, setVideoDuration] = useState("2");

  // Video advanced options
  const [videoWidth, setVideoWidth] = useState(832);
  const [videoHeight, setVideoHeight] = useState(480);
  const [videoSteps, setVideoSteps] = useState(20);
  const [videoGuidance, setVideoGuidance] = useState(7.5);
  const [videoFps, setVideoFps] = useState(16);
  const [videoSeed, setVideoSeed] = useState(-1);

  // Video from Image state
  const [videoImageFile, setVideoImageFile] = useState<File | null>(null);
  const [videoImagePreview, setVideoImagePreview] = useState<string | null>(null);
  const [videoImageLoading, setVideoImageLoading] = useState(false);
  const [videoImageResult, setVideoImageResult] = useState<string | null>(null);
  const [videoMotionPrompt, setVideoMotionPrompt] = useState("");

  async function handleGenerateVideo() {
    if (!videoPrompt.trim() || videoLoading) return;
    setVideoLoading(true);
    setVideoResult(null);
    setVideoDownloadUrl(null);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/generate/video`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: videoPrompt,
          model: selectedVideoModel,
          width: videoWidth,
          height: videoHeight,
          duration_seconds: parseFloat(videoDuration),
          steps: videoSteps,
          guidance: videoGuidance,
          fps: videoFps,
          seed: videoSeed,
          talent_ids: selectedTalents,
        }),
      });
      const data = await resp.json();
      if (data.success) {
        setVideoResult(`Video generated in ${data.generation_time}s — ${data.frames} frames • ${data.filename}`);
        if (data.download_url) setVideoDownloadUrl(data.download_url);
      } else {
        setVideoResult(data.detail || "Video generation failed. Ensure WAN 2.2 model is loaded on GPU.");
      }
    } catch {
      setVideoResult("Video generation is taking longer than expected. It may still be processing on the GPU — check back in a few minutes.");
    } finally {
      setVideoLoading(false);
    }
  }

  function handleVideoImageSelect(file: File) {
    setVideoImageFile(file);
    setVideoImageResult(null);
    const reader = new FileReader();
    reader.onload = (e) => setVideoImagePreview(e.target?.result as string);
    reader.readAsDataURL(file);
  }

  function handleVideoImageDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("image/")) handleVideoImageSelect(file);
  }

  async function handleAnimateImage() {
    if (!videoImageFile || videoImageLoading) return;
    setVideoImageLoading(true);
    setVideoImageResult(null);
    try {
      // Upload image first, then generate video with it as starting frame
      const formData = new FormData();
      formData.append("file", videoImageFile);
      formData.append("motion_prompt", videoMotionPrompt || "gentle camera movement, cinematic");

      const resp = await fetch(`${API_BASE}/api/v1/generate/video-from-image`, {
        method: "POST",
        body: formData,
      });
      const data = await resp.json();
      if (data.success) {
        setVideoImageResult(`Video generated in ${data.generation_time}s — ${data.frames} frames • ${data.filename}`);
      } else {
        setVideoImageResult(data.detail || "Image-to-video generation failed. Ensure WAN 2.2 model is loaded.");
      }
    } catch {
      setVideoImageResult("Video generation in progress... This takes several minutes. Check back shortly.");
    } finally {
      setVideoImageLoading(false);
    }
  }

  return {
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
  };
}
