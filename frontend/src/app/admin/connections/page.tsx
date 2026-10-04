"use client";

/**
 * Connections Hub — Unified surface for all integration connections.
 *
 * Displays connected services grouped by category (AI, Storage, Social,
 * Compute, Developer). Supports OAuth and API key connection flows.
 *
 * Features:
 * - List connections grouped by category
 * - Connect button initiates OAuth flow (backend handles dance)
 * - Connection status indicators (CONNECTED, DEGRADED, REAUTH_REQUIRED)
 * - Progressive disclosure: basic shows connect buttons, Advanced expands tool_policy
 *
 * Validates: Requirements R85.1, R85.2, R77.1, R77.3, R77.4, R77.7
 */

import { useState, useCallback } from "react";
import {
  Plug2,
  Brain,
  HardDrive,
  Share2,
  Cpu,
  Code2,
  ChevronDown,
  ChevronRight,
  Plus,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Loader2,
  Shield,
} from "lucide-react";
import { useSWRFetch } from "@/hooks/useSWRFetch";
import { api } from "@/lib/api";
import { useToast } from "@/components/toast";
import { PageLoading, PageEmpty } from "@/components/page-state";
import { StatusBadge, type StatusTone } from "../_components/status-badge";

// =============================================================================
// Types (matching backend schemas)
// =============================================================================

type ConnectionCategory = "ai_provider" | "storage" | "social" | "compute" | "developer" | "business";
type ConnectionLifecycle = "connecting" | "connected" | "degraded" | "reauth_required" | "disconnected" | "revoked";
type ConnectionOwnership = "user" | "workspace";

interface Connection {
  id: string;
  org_id: string;
  user_id: string | null;
  ownership: ConnectionOwnership;
  category: ConnectionCategory;
  provider_name: string;
  display_name: string;
  lifecycle_state: ConnectionLifecycle;
  auth_method: string;
  capabilities: string[];
  allowed_roles: string[];
  tool_policy: Record<string, unknown>;
  last_health_check_at: string | null;
  health_status: string | null;
  created_at: string;
  updated_at: string;
}

interface ConnectionListResponse {
  items: Connection[];
  total: number;
  limit: number;
  offset: number;
}

// =============================================================================
// Category metadata
// =============================================================================

const CATEGORY_META: Record<ConnectionCategory, { label: string; icon: typeof Brain; description: string }> = {
  ai_provider: {
    label: "AI Providers",
    icon: Brain,
    description: "Language models and AI services",
  },
  storage: {
    label: "Storage",
    icon: HardDrive,
    description: "File and asset storage providers",
  },
  social: {
    label: "Social Platforms",
    icon: Share2,
    description: "Social media and publishing platforms",
  },
  compute: {
    label: "Compute",
    icon: Cpu,
    description: "GPU and compute infrastructure",
  },
  developer: {
    label: "Developer Tools",
    icon: Code2,
    description: "Code, MCP servers, and developer integrations",
  },
  business: {
    label: "Business",
    icon: Shield,
    description: "Business and enterprise integrations",
  },
};

const CATEGORY_ORDER: ConnectionCategory[] = [
  "ai_provider",
  "storage",
  "social",
  "compute",
  "developer",
  "business",
];

// =============================================================================
// Available providers (what users can connect)
// =============================================================================

interface ProviderOption {
  name: string;
  display_name: string;
  category: ConnectionCategory;
  auth_method: "oauth" | "api_key";
  description: string;
}

const AVAILABLE_PROVIDERS: ProviderOption[] = [
  { name: "openai", display_name: "OpenAI", category: "ai_provider", auth_method: "api_key", description: "GPT-4o, GPT-4, DALL-E" },
  { name: "anthropic", display_name: "Anthropic", category: "ai_provider", auth_method: "api_key", description: "Claude 3.5, Claude 4" },
  { name: "ollama", display_name: "Ollama (Local)", category: "ai_provider", auth_method: "api_key", description: "Local LLM inference" },
  { name: "openrouter", display_name: "OpenRouter", category: "ai_provider", auth_method: "api_key", description: "Multi-model routing" },
  { name: "backblaze_b2", display_name: "Backblaze B2", category: "storage", auth_method: "api_key", description: "S3-compatible object storage" },
  { name: "aws_s3", display_name: "AWS S3", category: "storage", auth_method: "api_key", description: "Amazon S3 storage" },
  { name: "cloudflare_r2", display_name: "Cloudflare R2", category: "storage", auth_method: "api_key", description: "Zero egress storage" },
  { name: "instagram", display_name: "Instagram", category: "social", auth_method: "oauth", description: "Photo and reel publishing" },
  { name: "tiktok", display_name: "TikTok", category: "social", auth_method: "oauth", description: "Short-form video publishing" },
  { name: "youtube", display_name: "YouTube", category: "social", auth_method: "oauth", description: "Video publishing and analytics" },
  { name: "runpod", display_name: "RunPod", category: "compute", auth_method: "api_key", description: "GPU cloud compute" },
  { name: "vast_ai", display_name: "Vast.ai", category: "compute", auth_method: "api_key", description: "GPU marketplace" },
  { name: "github", display_name: "GitHub", category: "developer", auth_method: "oauth", description: "Source code and CI/CD" },
  { name: "huggingface", display_name: "Hugging Face", category: "developer", auth_method: "api_key", description: "Model hub and inference" },
  { name: "elevenlabs", display_name: "ElevenLabs", category: "ai_provider", auth_method: "api_key", description: "Voice synthesis and cloning" },
];

// =============================================================================
// Status indicators
// =============================================================================

const LIFECYCLE_BADGE_CONFIG: Record<
  ConnectionLifecycle,
  { label: string; tone: StatusTone; icon: typeof CheckCircle2 }
> = {
  connected: { label: "Connected", tone: "success", icon: CheckCircle2 },
  degraded: { label: "Degraded", tone: "warning", icon: AlertTriangle },
  reauth_required: { label: "Re-auth Required", tone: "error", icon: XCircle },
  connecting: { label: "Connecting", tone: "info", icon: Loader2 },
  disconnected: { label: "Disconnected", tone: "muted", icon: XCircle },
  revoked: { label: "Revoked", tone: "danger", icon: XCircle },
};

function ConnectionStatusBadge({ state }: { state: ConnectionLifecycle }) {
  const { label, tone, icon } = LIFECYCLE_BADGE_CONFIG[state];

  return (
    <StatusBadge
      label={label}
      tone={tone}
      icon={icon}
      spinIcon={state === "connecting"}
    />
  );
}

// =============================================================================
// Connection Card
// =============================================================================

function ConnectionCard({ connection, onRefresh }: { connection: Connection; onRefresh: () => void }) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const { show } = useToast();

  const category = CATEGORY_META[connection.category];
  const CategoryIcon = category?.icon ?? Plug2;

  async function handleReconnect() {
    try {
      await api.post("/api/v1/connections/initiate", {
        provider_name: connection.provider_name,
        category: connection.category,
        ownership: connection.ownership,
        display_name: connection.display_name,
      });
      show("Reconnection initiated", "success");
      onRefresh();
    } catch {
      show("Failed to reconnect", "error");
    }
  }

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-raised p-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-sunken">
            <CategoryIcon className="h-4 w-4 text-content-muted" />
          </div>
          <div>
            <h4 className="text-sm font-medium text-content-primary">{connection.display_name}</h4>
            <p className="text-xs text-content-muted">
              {connection.provider_name} &middot; {connection.ownership === "workspace" ? "Workspace" : "Personal"}
            </p>
          </div>
        </div>
        <ConnectionStatusBadge state={connection.lifecycle_state} />
      </div>

      {/* Capabilities */}
      {connection.capabilities.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {connection.capabilities.slice(0, 4).map((cap) => (
            <span
              key={cap}
              className="rounded bg-surface-sunken px-2 py-0.5 text-[10px] text-content-muted"
            >
              {cap}
            </span>
          ))}
          {connection.capabilities.length > 4 && (
            <span className="text-[10px] text-content-muted">
              +{connection.capabilities.length - 4} more
            </span>
          )}
        </div>
      )}

      {/* Actions */}
      {connection.lifecycle_state === "reauth_required" && (
        <button
          onClick={handleReconnect}
          className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-700 transition-colors"
        >
          <RefreshCw className="h-3 w-3" />
          Reconnect
        </button>
      )}

      {/* Progressive disclosure: Advanced section */}
      <button
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="mt-3 flex items-center gap-1 text-xs text-content-muted hover:text-content-secondary transition-colors"
      >
        {showAdvanced ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        Advanced
      </button>

      {showAdvanced && (
        <div className="mt-2 rounded-md border border-border-subtle bg-surface-sunken p-3 space-y-2">
          <div>
            <span className="text-[10px] font-medium text-content-muted uppercase tracking-wide">Allowed Roles</span>
            <div className="mt-1 flex gap-1">
              {connection.allowed_roles.map((role) => (
                <span key={role} className="rounded bg-purple-500/10 px-2 py-0.5 text-[10px] text-purple-300">
                  {role}
                </span>
              ))}
            </div>
          </div>
          {Object.keys(connection.tool_policy).length > 0 && (
            <div>
              <span className="text-[10px] font-medium text-content-muted uppercase tracking-wide">Tool Policy</span>
              <pre className="mt-1 rounded bg-black/20 p-2 text-[10px] text-content-muted overflow-x-auto">
                {JSON.stringify(connection.tool_policy, null, 2)}
              </pre>
            </div>
          )}
          {connection.last_health_check_at && (
            <div className="text-[10px] text-content-muted">
              Last health check: {new Date(connection.last_health_check_at).toLocaleString()}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Connect New Dialog
// =============================================================================

function ConnectNewPanel({
  onConnect,
  connecting,
}: {
  onConnect: (provider: ProviderOption) => void;
  connecting: string | null;
}) {
  const [selectedCategory, setSelectedCategory] = useState<ConnectionCategory | "all">("all");

  const filtered = selectedCategory === "all"
    ? AVAILABLE_PROVIDERS
    : AVAILABLE_PROVIDERS.filter((p) => p.category === selectedCategory);

  return (
    <div className="rounded-xl border border-border-subtle bg-surface-raised p-5">
      <h3 className="text-sm font-semibold text-content-primary mb-1">Add Connection</h3>
      <p className="text-xs text-content-muted mb-4">Connect a new service to your workspace.</p>

      {/* Category filter */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        <button
          onClick={() => setSelectedCategory("all")}
          className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
            selectedCategory === "all"
              ? "bg-purple-600 text-white"
              : "bg-surface-sunken text-content-muted hover:text-content-secondary"
          }`}
        >
          All
        </button>
        {CATEGORY_ORDER.map((cat) => (
          <button
            key={cat}
            onClick={() => setSelectedCategory(cat)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              selectedCategory === cat
                ? "bg-purple-600 text-white"
                : "bg-surface-sunken text-content-muted hover:text-content-secondary"
            }`}
          >
            {CATEGORY_META[cat].label}
          </button>
        ))}
      </div>

      {/* Provider grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {filtered.map((provider) => (
          <button
            key={provider.name}
            onClick={() => onConnect(provider)}
            disabled={connecting === provider.name}
            className="flex items-center gap-3 rounded-lg border border-border-subtle bg-surface-sunken p-3 text-left hover:border-purple-500/40 hover:bg-surface-hover transition-colors disabled:opacity-50"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-surface-raised">
              {React.createElement(CATEGORY_META[provider.category].icon, { className: "h-4 w-4 text-content-muted" })}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-content-primary truncate">{provider.display_name}</p>
              <p className="text-[10px] text-content-muted truncate">{provider.description}</p>
            </div>
            {connecting === provider.name ? (
              <Loader2 className="h-4 w-4 animate-spin text-purple-400 flex-shrink-0" />
            ) : (
              <Plus className="h-4 w-4 text-content-muted flex-shrink-0" />
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// Page Component
// =============================================================================

import React from "react";

export default function ConnectionsHubPage() {
  const { data, error, isLoading, mutate } = useSWRFetch<ConnectionListResponse>(
    "/api/v1/connections?limit=100"
  );
  const [connecting, setConnecting] = useState<string | null>(null);
  const [showAddPanel, setShowAddPanel] = useState(false);
  const { show } = useToast();

  const connections = data?.items ?? [];

  // Group connections by category
  const grouped = CATEGORY_ORDER.reduce<Record<ConnectionCategory, Connection[]>>(
    (acc, cat) => {
      acc[cat] = connections.filter((c) => c.category === cat);
      return acc;
    },
    {} as Record<ConnectionCategory, Connection[]>
  );

  const handleConnect = useCallback(async (provider: ProviderOption) => {
    setConnecting(provider.name);
    try {
      if (provider.auth_method === "oauth") {
        // OAuth flow: backend returns redirect_url, we send user there
        const result = await api.post<{ redirect_url: string; connection_id: string; state: string }>(
          "/api/v1/connections/initiate",
          {
            provider_name: provider.name,
            category: provider.category,
            ownership: "workspace",
            display_name: provider.display_name,
          }
        );
        // Redirect user to OAuth consent screen
        window.location.href = result.redirect_url;
      } else {
        // API key connections: prompt for key
        const apiKey = window.prompt(
          `Enter your ${provider.display_name} API key:\n\nThis key is stored securely and never redisplayed.`
        );
        if (!apiKey) {
          setConnecting(null);
          return;
        }
        await api.post("/api/v1/connections", {
          provider_name: provider.name,
          category: provider.category,
          ownership: "workspace",
          display_name: provider.display_name,
          auth_method: "api_key",
          api_key: apiKey,
          allowed_roles: ["owner", "admin", "editor"],
          tool_policy: {},
        });
        show(`${provider.display_name} connected`, "success");
        mutate();
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Connection failed";
      show(message, "error");
    } finally {
      setConnecting(null);
    }
  }, [mutate, show]);

  if (isLoading) return <PageLoading resource="connections" />;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-content-primary">Connections</h1>
          <p className="text-sm text-content-muted">
            Manage integrations with AI, storage, social, compute, and developer services.
          </p>
        </div>
        <button
          onClick={() => setShowAddPanel(!showAddPanel)}
          className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Add Connection
        </button>
      </div>

      {/* Add Connection Panel (progressive disclosure) */}
      {showAddPanel && (
        <ConnectNewPanel onConnect={handleConnect} connecting={connecting} />
      )}

      {/* Connection List by Category */}
      {connections.length === 0 && !showAddPanel ? (
        <PageEmpty
          resource="connections"
          icon={<Plug2 className="h-10 w-10 text-gray-600" />}
          action={{
            label: "Connect Your First Service",
            onClick: () => setShowAddPanel(true),
          }}
        />
      ) : (
        <div className="space-y-6">
          {CATEGORY_ORDER.map((category) => {
            const items = grouped[category];
            if (items.length === 0) return null;

            const meta = CATEGORY_META[category];
            const CategoryIcon = meta.icon;

            return (
              <div key={category}>
                <div className="flex items-center gap-2 mb-3">
                  <CategoryIcon className="h-4 w-4 text-content-muted" />
                  <h2 className="text-sm font-semibold text-content-primary">{meta.label}</h2>
                  <span className="text-xs text-content-muted">({items.length})</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {items.map((conn) => (
                    <ConnectionCard key={conn.id} connection={conn} onRefresh={mutate} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-300">
          Failed to load connections: {error.message}
        </div>
      )}
    </div>
  );
}
