/**
 * Brain Page Types — Story 136.a
 *
 * Shared types for the Brain page domain modules.
 */

export interface ChatMessage {
  role: "user" | "brain" | string;
  content: string;
  time: string;
  image?: string; // Base64 data URL
}

export interface Session {
  id: string;
  title: string;
  created_at: string;
  messages?: ChatMessage[];
}

export interface Collection {
  id: string;
  name: string;
  color: string;
  conversationIds: string[];
}

export interface BrainMode {
  name: string;
  desc: string;
  icon: React.ComponentType<{ className?: string }>;
  key: string;
}

export interface ApprovalData {
  tool: string;
  reason: string;
  approval_id: string;
  estimated_cost_usd?: number;
}

export interface BrainMemory {
  favorite_models?: string[];
  favorite_camera_moves?: string[];
  favorite_lighting?: string[];
  favorite_prompts?: string[];
  favorite_workflows?: string[];
  favorite_editing_style?: string[];
  [key: string]: unknown;
}

export type ApprovalStatus = "pending" | "approved" | "rejected";
