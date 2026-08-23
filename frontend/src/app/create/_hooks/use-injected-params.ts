"use client";

import { useEffect } from "react";

/**
 * Reads injected prompt/tab/remix params on mount (from Brain page links and
 * Library remix links, via query string or sessionStorage hand-off).
 */
export function useInjectedParams({
  setActiveTab,
  setPrompt,
  setVoiceText,
  setVideoPrompt,
  setSelectedModel,
  setSeed,
  setWidth,
  setHeight,
}: {
  setActiveTab: (tab: "image" | "video" | "audio") => void;
  setPrompt: (text: string) => void;
  setVoiceText: (text: string) => void;
  setVideoPrompt: (text: string) => void;
  setSelectedModel: (model: string) => void;
  setSeed: (seed: number) => void;
  setWidth: (width: number) => void;
  setHeight: (height: number) => void;
}) {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const injectedPrompt = params.get("prompt") || sessionStorage.getItem("injected_prompt");
    const injectedTab = params.get("tab") || sessionStorage.getItem("injected_tab");
    if (injectedPrompt) {
      const decoded = decodeURIComponent(injectedPrompt);
      // Route prompt to the correct field based on tab
      if (injectedTab === "audio") {
        setVoiceText(decoded);
      } else if (injectedTab === "video") {
        setVideoPrompt(decoded);
      } else {
        setPrompt(decoded);
      }
      sessionStorage.removeItem("injected_prompt");
      sessionStorage.removeItem("injected_tab");
    }
    if (injectedTab && ["image", "video", "audio"].includes(injectedTab)) {
      setActiveTab(injectedTab as "image" | "video" | "audio");
    }
    // Remix params from Library re-generate
    const injectedModel = params.get("model");
    const injectedSeed = params.get("seed");
    const injectedWidth = params.get("width");
    const injectedHeight = params.get("height");
    if (injectedModel) setSelectedModel(injectedModel);
    if (injectedSeed) setSeed(parseInt(injectedSeed));
    if (injectedWidth) setWidth(parseInt(injectedWidth));
    if (injectedHeight) setHeight(parseInt(injectedHeight));
  }, [setActiveTab, setPrompt, setVoiceText, setVideoPrompt, setSelectedModel, setSeed, setWidth, setHeight]);
}
