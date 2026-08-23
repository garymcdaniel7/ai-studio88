/**
 * Editor domain types, option constants, and shot factory.
 * Shared by the editor page and its colocated components.
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Shot {
  id: string;
  order: number;
  prompt: string;
  model: string;
  duration: number; // seconds
  camera_motion: string;
  transition: string;
  aspect_ratio: string;
  status: "draft" | "generating" | "completed" | "failed";
  asset_id?: string;
  thumbnail_url?: string;
  error?: string;
}

export type TransitionType = "cut" | "crossfade" | "fade_black" | "fade_white" | "wipe_left";
export type CameraMotion = "static" | "pan_left" | "pan_right" | "dolly_in" | "dolly_out" | "tilt_up" | "tilt_down" | "orbit";

export const MODELS = [
  { id: "wan-2.1-t2v", name: "WAN 2.1 T2V", type: "text-to-video" },
  { id: "wan-2.1-i2v", name: "WAN 2.1 I2V", type: "image-to-video" },
  { id: "flux-dev", name: "Flux Dev (Image)", type: "text-to-image" },
  { id: "sdxl-turbo", name: "SDXL Turbo (Image)", type: "text-to-image" },
];

export const TRANSITIONS: { value: TransitionType; label: string }[] = [
  { value: "cut", label: "Hard Cut" },
  { value: "crossfade", label: "Crossfade" },
  { value: "fade_black", label: "Fade to Black" },
  { value: "fade_white", label: "Fade to White" },
  { value: "wipe_left", label: "Wipe Left" },
];

export const CAMERA_MOTIONS: { value: CameraMotion; label: string }[] = [
  { value: "static", label: "Static" },
  { value: "pan_left", label: "Pan Left" },
  { value: "pan_right", label: "Pan Right" },
  { value: "dolly_in", label: "Dolly In" },
  { value: "dolly_out", label: "Dolly Out" },
  { value: "tilt_up", label: "Tilt Up" },
  { value: "tilt_down", label: "Tilt Down" },
  { value: "orbit", label: "Orbit" },
];

export const ASPECT_RATIOS = ["16:9", "9:16", "1:1", "4:3", "21:9"];

export function createShot(order: number, prompt = ""): Shot {
  return {
    id: crypto.randomUUID(),
    order,
    prompt,
    model: "wan-2.1-t2v",
    duration: 3,
    camera_motion: "static",
    transition: "crossfade",
    aspect_ratio: "16:9",
    status: "draft",
  };
}
