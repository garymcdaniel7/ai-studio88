export type ProviderId =
  | "thunder_compute"
  | "runcomfy"
  | "gemini"
  | "elevenlabs"
  | "openai"
  | "replicate"
  | "ollama";

export type ProviderConnection = {
  id: string;
  provider_name: string;
  display_name: string;
  ownership: "user" | "workspace";
  category: "ai_provider" | "compute" | "storage" | "social" | "developer" | "business";
  lifecycle_state: "connecting" | "connected" | "degraded" | "reauth_required" | "disconnected" | "revoked";
  capabilities: string[];
  last_health_check_at?: string | null;
  health_status?: string | null;
  expires_at?: string | null;
};

export type ProviderDefinition = {
  id: ProviderId;
  name: string;
  category: "ai_provider" | "compute";
  lane: string;
  capabilityCopy: string;
  costCopy: string;
  ownershipCopy: string;
  keyPlaceholder: string;
  docsUrl: string;
  requiresKey: boolean;
  healthNames: string[];
};

export const PROVIDER_DEFINITIONS: ProviderDefinition[] = [
  {
    id: "thunder_compute",
    name: "Thunder Compute",
    category: "compute",
    lane: "MAKE · image, video, and training",
    capabilityCopy: "Batch GPU rendering and training workloads.",
    costCopy: "You pay Thunder Compute directly for GPU runtime; AI Studio records provider usage for job cost evidence.",
    ownershipCopy: "Workspace key is shared with permitted workspace roles; personal keys stay private to your user connection.",
    keyPlaceholder: "Paste a Thunder Compute API key",
    docsUrl: "https://www.thundercompute.com/",
    requiresKey: true,
    healthNames: ["thunder", "thunder_compute"],
  },
  {
    id: "runcomfy",
    name: "RunComfy",
    category: "compute",
    lane: "MAKE · quick renders and workflow execution",
    capabilityCopy: "Managed ComfyUI execution, queue progress, and webhook delivery.",
    costCopy: "RunComfy charges your account per provider usage; review estimates before dispatching a job.",
    ownershipCopy: "Workspace key is shared only with configured workload roles; AI Studio never displays it again.",
    keyPlaceholder: "Paste a RunComfy API key",
    docsUrl: "https://www.runcomfy.com/",
    requiresKey: true,
    healthNames: ["runcomfy", "run_comfy"],
  },
  {
    id: "gemini",
    name: "Gemini",
    category: "ai_provider",
    lane: "WRITE · research and multimodal assistance",
    capabilityCopy: "Multimodal reasoning and research assistance for story and prompt work.",
    costCopy: "Google bills your Gemini project; usage remains outside the AI Studio subscription.",
    ownershipCopy: "Use a workspace key for shared Brain access, or a personal key for your own requests.",
    keyPlaceholder: "Paste a Gemini API key",
    docsUrl: "https://ai.google.dev/",
    requiresKey: true,
    healthNames: ["gemini", "google_gemini"],
  },
  {
    id: "elevenlabs",
    name: "ElevenLabs",
    category: "ai_provider",
    lane: "CAST · voice identity and TTS",
    capabilityCopy: "Voice generation and approved voice identity workflows.",
    costCopy: "ElevenLabs bills your account according to its plan and character usage.",
    ownershipCopy: "Workspace keys enable shared voice work; personal keys are limited to your user connection.",
    keyPlaceholder: "Paste an ElevenLabs API key",
    docsUrl: "https://elevenlabs.io/",
    requiresKey: true,
    healthNames: ["elevenlabs"],
  },
  {
    id: "openai",
    name: "OpenAI",
    category: "ai_provider",
    lane: "WRITE · Brain cloud fallback",
    capabilityCopy: "Cloud language-model fallback for Brain and prompt assistance.",
    costCopy: "OpenAI bills your account by usage; fallback can create paid requests.",
    ownershipCopy: "Choose workspace ownership only when your team should share this key.",
    keyPlaceholder: "Paste an OpenAI API key",
    docsUrl: "https://platform.openai.com/api-keys",
    requiresKey: true,
    healthNames: ["openai"],
  },
  {
    id: "replicate",
    name: "Replicate",
    category: "ai_provider",
    lane: "MAKE · hosted model execution",
    capabilityCopy: "Hosted model execution for supported generation workloads.",
    costCopy: "Replicate bills your account for model runtime; AI Studio does not absorb provider charges.",
    ownershipCopy: "Workspace ownership makes the key available to approved workload roles.",
    keyPlaceholder: "Paste a Replicate API token",
    docsUrl: "https://replicate.com/account/api-tokens",
    requiresKey: true,
    healthNames: ["replicate"],
  },
  {
    id: "ollama",
    name: "Ollama / local",
    category: "ai_provider",
    lane: "WRITE · private local Brain",
    capabilityCopy: "Local or managed Ollama inference without a provider API key.",
    costCopy: "Local Ollama uses your machine and electricity; managed hosting may have a separate infrastructure cost.",
    ownershipCopy: "No secret is collected. The server decides whether the configured local endpoint is available.",
    keyPlaceholder: "No API key required",
    docsUrl: "https://ollama.com/",
    requiresKey: false,
    healthNames: ["ollama", "local_ollama", "gpu_ollama"],
  },
];

export function getProviderDefinition(providerName: string): ProviderDefinition | undefined {
  return PROVIDER_DEFINITIONS.find((provider) => provider.id === providerName);
}
