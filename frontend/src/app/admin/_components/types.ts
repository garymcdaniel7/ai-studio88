// Lane-local shared types for the admin dashboard sections.

export interface VastStatus {
  api_connected: boolean;
  instance_active: boolean;
  instance_paused: boolean;
  balance: number;
  instance_info: {
    id: number;
    gpu_name: string;
    price_per_hour: number;
    status: string;
  } | null;
  error?: string;
}

export interface RunPodStatus {
  provider: string;
  api_connected: boolean;
  instance_active: boolean;
  instance_paused: boolean;
  balance: number;
  spend_per_hr?: number;
  instance_info: {
    id: string;
    gpu_name: string;
    price_per_hour: number;
    status: string;
    name?: string;
  } | null;
  total_pods?: number;
  active_pods?: number;
  error?: string;
}

export type GpuWorkerAction =
  | "idle"
  | "launching"
  | "stopping"
  | "pausing"
  | "resuming";

export type OllamaPreference = "auto" | "local" | "remote";
