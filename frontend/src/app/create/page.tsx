"use client";

import { useState } from "react";
import { CapabilityGate } from "@/components/CapabilityGate";
import { AudioTab } from "./_components/audio-tab";
import { ImageTab } from "./_components/image-tab";
import { MediaTabs } from "./_components/media-tabs";
import { VideoTab } from "./_components/video-tab";
import { useAudioGeneration } from "./_hooks/use-audio-generation";
import { useCreateData } from "./_hooks/use-create-data";
import { useFavoritePrompts } from "./_hooks/use-favorite-prompts";
import { useImageGeneration } from "./_hooks/use-image-generation";
import { useInjectedParams } from "./_hooks/use-injected-params";
import { useVideoGeneration } from "./_hooks/use-video-generation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function CreatePage() {
  const [activeTab, setActiveTab] = useState<"image" | "video" | "audio">("image");
  const [prompt, setPrompt] = useState("");
  const [selectedModel, setSelectedModel] = useState("flux2-klein");
  const [selectedTalents, setSelectedTalents] = useState<string[]>([]);
  const [selectedTalent, setSelectedTalent] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [selectedStyle, setSelectedStyle] = useState("auto");

  // Mount effects fire in this call order: favorites load, catalog bootstrap,
  // image defaults sync + talent LoRA injection, then injected params.
  const favorites = useFavoritePrompts();
  const data = useCreateData({ selectedModel, setSelectedModel });
  const video = useVideoGeneration({ selectedTalents });
  const audio = useAudioGeneration({ elevenlabsVoices: data.elevenlabsVoices });
  const img = useImageGeneration({
    prompt,
    setPrompt,
    setSelectedModel,
    selectedModel,
    selectedStyle,
    selectedTalents,
    gpuReadyModels: data.gpuReadyModels,
    talentList: data.talentList,
  });
  useInjectedParams({
    setActiveTab,
    setPrompt,
    setVoiceText: audio.setVoiceText,
    setVideoPrompt: video.setVideoPrompt,
    setSelectedModel,
    setSeed: img.setSeed,
    setWidth: img.setWidth,
    setHeight: img.setHeight,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-content-primary">Create</h1>
        <p className="text-sm text-content-muted">Generate AI content — images, videos, voice, and music.</p>
      </div>

      {/* Type Tabs */}
      <MediaTabs activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Image Generation — gated by image_generation capability */}
      {activeTab === "image" && (
        <CapabilityGate capability="image_generation" fallback={
          <div className="rounded-xl border border-border-subtle bg-surface-raised p-6 text-center">
            <p className="text-sm text-content-muted">Image generation is not currently available.</p>
          </div>
        }>
          <ImageTab
            apiBase={API_BASE}
            imageModelList={data.imageModelList}
            gpuReadyModels={data.gpuReadyModels}
            gpuOnline={data.gpuOnline}
            presets={data.presets}
            workerVram={data.workerVram}
            generationHistory={data.generationHistory}
            talentList={data.talentList}
            projectList={data.projectList}
            availableLoras={data.availableLoras}
            prompt={prompt}
            setPrompt={setPrompt}
            selectedModel={selectedModel}
            setSelectedModel={setSelectedModel}
            selectedTalent={selectedTalent}
            onSelectTalent={setSelectedTalent}
            selectedProject={selectedProject}
            onSelectProject={setSelectedProject}
            selectedStyle={selectedStyle}
            onSelectStyle={setSelectedStyle}
            selectedTalents={selectedTalents}
            onChangeTalents={setSelectedTalents}
            img={img}
            favorites={favorites}
          />
        </CapabilityGate>
      )}

      {/* Video Generation — gated by video_generation capability */}
      {activeTab === "video" && (
        <CapabilityGate capability="video_generation" fallback={
          <div className="rounded-xl border border-border-subtle bg-surface-raised p-6 text-center">
            <p className="text-sm text-content-muted">Video generation is not currently available.</p>
          </div>
        }>
          <VideoTab
            apiBase={API_BASE}
            videoModelList={data.videoModelList}
            talentList={data.talentList}
            selectedTalents={selectedTalents}
            onChangeTalents={setSelectedTalents}
            video={video}
          />
        </CapabilityGate>
      )}

      {/* Voice & Music */}
      {activeTab === "audio" && (
        <AudioTab
          audio={audio}
          elevenlabsVoices={data.elevenlabsVoices}
          mossVoices={data.mossVoices}
        />
      )}
    </div>
  );
}
