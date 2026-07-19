"use client";

import { useState } from "react";
import { ThumbsUp, ThumbsDown, Star } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * FeedbackButtons — Universal rating component for any agent output.
 *
 * Appears on: generated images, storyboard shots, voice clips, etc.
 * Sends feedback to the learning engine so agents improve over time.
 *
 * Usage:
 *   <FeedbackButtons agent="akose" outputType="recipe_generation" context={{recipe: "magazine-cover"}} />
 */

interface FeedbackButtonsProps {
  agent: string;         // akose, oya, araye, osun, etc
  outputType: string;    // generation, storyboard_shot, voice, etc
  context?: Record<string, unknown>;  // relevant context for learning
  compact?: boolean;     // small version (just thumbs)
}

export function FeedbackButtons({ agent, outputType, context = {}, compact = false }: FeedbackButtonsProps) {
  const [rated, setRated] = useState<number | null>(null);
  const [sending, setSending] = useState(false);

  async function submitRating(rating: number) {
    if (rated !== null || sending) return;
    setSending(true);
    setRated(rating);

    try {
      await fetch(`${API_BASE}/api/v1/learn/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent, output_type: outputType, rating, context }),
      });
    } catch {
      // Silent fail — don't interrupt UX for learning
    } finally {
      setSending(false);
    }
  }

  if (rated !== null) {
    return (
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] text-gray-500">
          {rated >= 4 ? "Thanks! This helps the AI learn." : "Noted — we'll improve."}
        </span>
        {rated >= 4 ? (
          <ThumbsUp className="h-3 w-3 text-green-400" />
        ) : (
          <ThumbsDown className="h-3 w-3 text-amber-400" />
        )}
      </div>
    );
  }

  if (compact) {
    return (
      <div className="flex items-center gap-1">
        <button
          onClick={() => submitRating(5)}
          className="p-1 rounded text-gray-500 hover:text-green-400 hover:bg-green-400/10 transition-colors"
          title="Good result"
        >
          <ThumbsUp className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={() => submitRating(2)}
          className="p-1 rounded text-gray-500 hover:text-amber-400 hover:bg-amber-400/10 transition-colors"
          title="Needs improvement"
        >
          <ThumbsDown className="h-3.5 w-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-gray-600">Rate this:</span>
      <div className="flex gap-0.5">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            onClick={() => submitRating(star)}
            className="p-0.5 text-gray-600 hover:text-yellow-400 transition-colors"
            title={`${star} star${star > 1 ? "s" : ""}`}
          >
            <Star className="h-3.5 w-3.5" fill={star <= (rated || 0) ? "currentColor" : "none"} />
          </button>
        ))}
      </div>
    </div>
  );
}
