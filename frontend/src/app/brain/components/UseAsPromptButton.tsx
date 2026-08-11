"use client";

import { useState } from "react";
import { Sparkles, ArrowRight } from "lucide-react";

const GENERATION_TYPES = [
  { key: "image", label: "Image", icon: "🖼️", tab: "image" },
  { key: "video", label: "Video", icon: "🎬", tab: "video" },
  { key: "voice", label: "Voice", icon: "🎙️", tab: "audio" },
  { key: "music", label: "Music", icon: "🎵", tab: "audio" },
];

interface UseAsPromptButtonProps {
  content: string;
}

/**
 * "Use as Prompt" button that appears on hover over brain messages.
 * Injects the message content into the Create page as a generation prompt.
 */
export function UseAsPromptButton({ content }: UseAsPromptButtonProps) {
  const [showPopup, setShowPopup] = useState(false);

  function handleSelect(tab: string) {
    sessionStorage.setItem("injected_prompt", content);
    sessionStorage.setItem("injected_tab", tab);
    window.location.href = `/create?tab=${tab}&prompt=${encodeURIComponent(content.slice(0, 500))}`;
  }

  return (
    <div className="relative">
      <button
        onClick={() => setShowPopup(!showPopup)}
        className="flex items-center gap-1 rounded-full bg-purple-600/80 px-2.5 py-1 text-[10px] font-medium text-white shadow-lg hover:bg-purple-600 transition-colors"
      >
        <Sparkles className="h-3 w-3" />
        Use as Prompt
      </button>

      {showPopup && (
        <div className="absolute bottom-8 right-0 z-50 w-48 rounded-xl border border-white/[0.1] bg-[#12122a] p-2 shadow-2xl">
          <p className="px-2 py-1 text-[10px] font-semibold text-gray-400 uppercase">Generate as...</p>
          {GENERATION_TYPES.map((type) => (
            <button
              key={type.key}
              onClick={() => handleSelect(type.tab)}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-gray-300 hover:bg-purple-600/20 hover:text-white transition-colors"
            >
              <span>{type.icon}</span>
              <span>{type.label}</span>
              <ArrowRight className="h-3 w-3 ml-auto text-gray-600" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
