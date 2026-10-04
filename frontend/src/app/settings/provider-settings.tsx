"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { AlertCircle, CheckCircle2, Info, Loader2, Plus, RefreshCw, ShieldCheck } from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { PROVIDER_DEFINITIONS, type ProviderConnection, type ProviderId } from "./provider-config";
import { ProviderCard } from "./provider-card";

type ConnectionListResponse = { items?: ProviderConnection[] };
type FallbackResponse = { fallback_mode?: "auto" | "ask" | "strict"; denied_providers?: string[] };
type HealthResult = { provider?: string; healthy?: boolean; message?: string; checked_at?: string };
type CapabilityResult = Record<string, unknown> & { provider?: string };

type TestState = { provider: ProviderId; status: "healthy" | "failed"; message: string } | null;

function errorMessage(error: unknown, action: string): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Your session expired. Sign in again to manage provider connections.";
    if (error.status === 403) return "Your role cannot perform this action. Ask a workspace admin to update shared provider settings.";
    if (error.status === 409) return "That provider already has a connection. Revoke or rotate the existing connection first.";
    if (error.status === 422) return `Check the form values and try again${error.detail ? `: ${error.detail}` : "."}`;
    if (error.status >= 500) return `${action} failed on the server. Reference ${error.requestId || "the request ID in your browser"}.`;
    return error.detail || `${action} failed.`;
  }
  return `${action} failed. Check your connection and try again.`;
}

function readConnections(value: unknown): ProviderConnection[] {
  if (Array.isArray(value)) return value as ProviderConnection[];
  if (value && typeof value === "object" && Array.isArray((value as ConnectionListResponse).items)) {
    return (value as ConnectionListResponse).items || [];
  }
  return [];
}

function providerCategory(provider: ProviderId): "compute" | "ai_provider" {
  return PROVIDER_DEFINITIONS.find((definition) => definition.id === provider)?.category || "ai_provider";
}

export function ProviderSettings() {
  const [connections, setConnections] = useState<ProviderConnection[]>([]);
  const [healthByProvider, setHealthByProvider] = useState<Record<string, { healthy: boolean; message: string; checkedAt?: string }>>({});
  const [capabilitiesByProvider, setCapabilitiesByProvider] = useState<Record<string, string[]>>({});
  const [fallbackMode, setFallbackMode] = useState<"auto" | "ask" | "strict">("auto");
  const [deniedProviders, setDeniedProviders] = useState<string[]>([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState<string | null>(null);
  const [providerId, setProviderId] = useState<ProviderId>("thunder_compute");
  const [ownership, setOwnership] = useState<"workspace" | "user">("workspace");
  const [displayName, setDisplayName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [savingKey, setSavingKey] = useState(false);
  const [savingFallback, setSavingFallback] = useState(false);
  const [testingProvider, setTestingProvider] = useState<ProviderId | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [testState, setTestState] = useState<TestState>(null);
  const [formMessage, setFormMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);

  const loadProviderData = useCallback(async () => {
    setPageError(null);
    const [connectionResult, fallbackResult, healthResult, capabilityResult] = await Promise.allSettled([
      api.get<ConnectionListResponse>("/api/v1/connections?limit=100"),
      api.get<FallbackResponse>("/api/v1/workspace/fallback"),
      api.get<HealthResult[]>("/api/v1/providers/health"),
      api.get<{ providers?: CapabilityResult[] }>("/api/v1/provider-capabilities"),
    ]);

    if (connectionResult.status === "fulfilled") {
      setConnections(readConnections(connectionResult.value));
    } else {
      setPageError(errorMessage(connectionResult.reason, "Loading provider connections"));
    }
    if (fallbackResult.status === "fulfilled") {
      const fallback = fallbackResult.value;
      if (fallback.fallback_mode === "auto" || fallback.fallback_mode === "ask" || fallback.fallback_mode === "strict") {
        setFallbackMode(fallback.fallback_mode);
      }
      setDeniedProviders(Array.isArray(fallback.denied_providers) ? fallback.denied_providers : []);
    }
    if (healthResult.status === "fulfilled") {
      const nextHealth: Record<string, { healthy: boolean; message: string; checkedAt?: string }> = {};
      for (const result of healthResult.value || []) {
        if (!result.provider) continue;
        nextHealth[result.provider] = {
          healthy: Boolean(result.healthy),
          message: result.message || (result.healthy ? "Provider is healthy" : "Provider is unavailable"),
          checkedAt: result.checked_at,
        };
      }
      setHealthByProvider(nextHealth);
    }
    if (capabilityResult.status === "fulfilled") {
      const nextCapabilities: Record<string, string[]> = {};
      for (const result of capabilityResult.value.providers || []) {
        if (!result.provider) continue;
        const labels = Object.entries(result)
          .filter(([key, value]) => key.startsWith("supports_") && value === true)
          .map(([key]) => key.replace("supports_", ""));
        if (Array.isArray(result.supported_models)) {
          labels.push(...result.supported_models.filter((model): model is string => typeof model === "string").slice(0, 6));
        }
        if (labels.length) nextCapabilities[result.provider] = labels;
      }
      setCapabilitiesByProvider(nextCapabilities);
    }
  }, []);

  useEffect(() => {
    let active = true;
    // The API response is the external source of truth for this client component.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- mirror async provider status into page state
    void loadProviderData().then(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [loadProviderData]);

  const refresh = async () => {
    setRefreshing(true);
    await loadProviderData();
    setRefreshing(false);
  };

  const findConnection = (provider: ProviderId) =>
    connections.find((connection) => connection.provider_name === provider && connection.lifecycle_state !== "revoked") ||
    connections.find((connection) => connection.provider_name === provider);

  const connectedProviders = PROVIDER_DEFINITIONS.filter((definition) => Boolean(findConnection(definition.id)));

  const healthFor = (provider: ProviderId) => {
    const definition = PROVIDER_DEFINITIONS.find((item) => item.id === provider);
    if (!definition) return undefined;
    const found = definition.healthNames.map((name) => healthByProvider[name]).find(Boolean);
    return found;
  };

  const capabilitiesFor = (provider: ProviderId) => {
    const definition = PROVIDER_DEFINITIONS.find((item) => item.id === provider);
    if (!definition) return undefined;
    for (const name of [provider, ...(definition.healthNames || [])]) {
      if (capabilitiesByProvider[name]) return capabilitiesByProvider[name];
    }
    return undefined;
  };

  async function addConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormMessage(null);
    const definition = PROVIDER_DEFINITIONS.find((item) => item.id === providerId);
    if (!definition?.requiresKey) {
      setFormMessage({ kind: "error", text: "Ollama/local does not use an API key. Configure its endpoint in the server environment instead." });
      return;
    }
    if (!displayName.trim() || apiKey.trim().length < 8) {
      setFormMessage({ kind: "error", text: "Add a display name and an API key with at least 8 characters. The key is sent once and never returned." });
      return;
    }
    setSavingKey(true);
    try {
      const connection = await api.post<ProviderConnection>("/api/v1/connections", {
        provider_name: providerId,
        category: providerCategory(providerId),
        ownership,
        display_name: displayName.trim(),
        api_key: apiKey.trim(),
        allowed_roles: ownership === "workspace" ? ["owner", "admin", "editor"] : ["owner", "admin", "editor"],
        tool_policy: {},
      });
      setConnections((current) => [...current.filter((item) => item.id !== connection.id), connection]);
      setSelectedConnectionId(connection.id);
      setApiKey("");
      setDisplayName("");
      setFormMessage({ kind: "success", text: "Provider key stored securely. It will not be shown again." });
    } catch (error) {
      setFormMessage({ kind: "error", text: errorMessage(error, "Saving provider key") });
    } finally {
      setSavingKey(false);
    }
  }

  async function testProvider(provider: ProviderId) {
    setTestingProvider(provider);
    setTestState(null);
    try {
      const results = await api.get<HealthResult[]>("/api/v1/providers/health");
      const definition = PROVIDER_DEFINITIONS.find((item) => item.id === provider);
      const result = (results || []).find((item) => definition?.healthNames.includes(item.provider || ""));
      const healthy = Boolean(result?.healthy);
      const message = result?.message || "No provider health result was returned.";
      setHealthByProvider((current) => ({
        ...current,
        ...(definition?.healthNames[0] ? { [definition.healthNames[0]]: { healthy, message, checkedAt: result?.checked_at } } : {}),
      }));
      setTestState({ provider, status: healthy ? "healthy" : "failed", message });
    } catch (error) {
      setTestState({ provider, status: "failed", message: errorMessage(error, "Testing provider health") });
    } finally {
      setTestingProvider(null);
    }
  }

  async function revokeConnection(connection: ProviderConnection) {
    if (!window.confirm(`Revoke the ${connection.display_name} key? This cannot be undone.`)) return;
    setRevokingId(connection.id);
    try {
      await api.delete(`/api/v1/connections/${connection.id}`);
      setConnections((current) => current.filter((item) => item.id !== connection.id));
      if (selectedConnectionId === connection.id) setSelectedConnectionId(null);
      setFormMessage({ kind: "success", text: `${connection.display_name} was revoked. Existing provider access will stop after the server processes the revocation.` });
    } catch (error) {
      setFormMessage({ kind: "error", text: errorMessage(error, "Revoking provider key") });
    } finally {
      setRevokingId(null);
    }
  }

  async function saveFallback(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSavingFallback(true);
    setFormMessage(null);
    try {
      await api.put<FallbackResponse>("/api/v1/workspace/fallback", {
        fallback_mode: fallbackMode,
        denied_providers: deniedProviders,
      });
      setFormMessage({ kind: "success", text: "Fallback policy saved for this workspace." });
    } catch (error) {
      setFormMessage({ kind: "error", text: errorMessage(error, "Saving fallback policy") });
    } finally {
      setSavingFallback(false);
    }
  }

  function toggleDenied(provider: string) {
    setDeniedProviders((current) => current.includes(provider) ? current.filter((item) => item !== provider) : [...current, provider]);
  }

  return (
    <div className="space-y-6" data-testid="byo-provider-settings">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">BYO provider connections</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">
            Add provider keys once, then use them in the workload lane they support. Keys are encrypted by the backend, masked in this view, and never returned to the browser after creation.
          </p>
        </div>
        <button type="button" onClick={refresh} disabled={refreshing || loading} className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/[0.1] px-3 py-2 text-xs text-slate-300 hover:text-white disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-violet-400/70">
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} aria-hidden="true" /> Refresh status
        </button>
      </div>

      <div className="rounded-xl border border-violet-400/20 bg-violet-400/[0.06] p-4 text-xs leading-5 text-violet-100">
        <div className="flex gap-2"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-violet-300" aria-hidden="true" /><p><strong>Ownership and cost:</strong> AI Studio supplies the orchestration UI. Your provider account owns API usage and billing. Every generation still requires a server-side cost estimate and the authenticated workspace policy before dispatch.</p></div>
      </div>

      {pageError && <div className="flex gap-2 rounded-xl border border-red-400/20 bg-red-400/10 p-4 text-sm text-red-100" role="alert"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />{pageError}</div>}
      {formMessage && <div className={`flex gap-2 rounded-xl border p-4 text-sm ${formMessage.kind === "success" ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-100" : "border-red-400/20 bg-red-400/10 text-red-100"}`} role="status">{formMessage.kind === "success" ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" /> : <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />}{formMessage.text}</div>}

      <form onSubmit={addConnection} className="rounded-2xl border border-white/[0.08] bg-[#111827] p-5">
        <div className="flex items-center gap-2"><Plus className="h-4 w-4 text-violet-300" aria-hidden="true" /><h3 className="font-semibold text-white">Add a provider key</h3></div>
        <p className="mt-1 text-xs text-slate-400">The secret is submitted only to the authenticated backend. It is never placed in logs, query strings, or page state after save.</p>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <label className="text-xs text-slate-300">Provider<select value={providerId} onChange={(event) => setProviderId(event.target.value as ProviderId)} className="mt-2 w-full rounded-lg border border-white/[0.1] bg-slate-950 px-3 py-2.5 text-sm text-white focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-400/70">{PROVIDER_DEFINITIONS.map((definition) => <option key={definition.id} value={definition.id}>{definition.name} · {definition.lane}</option>)}</select></label>
          <label className="text-xs text-slate-300">Connection ownership<select value={ownership} onChange={(event) => setOwnership(event.target.value as "workspace" | "user")} className="mt-2 w-full rounded-lg border border-white/[0.1] bg-slate-950 px-3 py-2.5 text-sm text-white focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-400/70"><option value="workspace">Workspace · shared by permitted roles</option><option value="user">Personal · only my user connection</option></select></label>
          <label className="text-xs text-slate-300">Display name<input required value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={200} placeholder="e.g. Production OpenAI" className="mt-2 w-full rounded-lg border border-white/[0.1] bg-slate-950 px-3 py-2.5 text-sm text-white placeholder:text-slate-600 focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-400/70" /></label>
          <label className="text-xs text-slate-300">Provider API key{!PROVIDER_DEFINITIONS.find((definition) => definition.id === providerId)?.requiresKey && <span className="ml-2 text-slate-500">not required for local Ollama</span>}<input required={PROVIDER_DEFINITIONS.find((definition) => definition.id === providerId)?.requiresKey} disabled={!PROVIDER_DEFINITIONS.find((definition) => definition.id === providerId)?.requiresKey} type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} minLength={8} placeholder={PROVIDER_DEFINITIONS.find((definition) => definition.id === providerId)?.keyPlaceholder} className="mt-2 w-full rounded-lg border border-white/[0.1] bg-slate-950 px-3 py-2.5 text-sm text-white placeholder:text-slate-600 focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-400/70 disabled:cursor-not-allowed disabled:opacity-50" /></label>
        </div>
        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs text-slate-500">Choose workspace ownership only when teammates should share this provider account. This form never accepts an organization ID.</p><button type="submit" disabled={savingKey || !PROVIDER_DEFINITIONS.find((definition) => definition.id === providerId)?.requiresKey} className="inline-flex items-center justify-center gap-2 rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-violet-400/70">{savingKey ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}{savingKey ? "Saving securely…" : "Add provider key"}</button></div>
      </form>

      <div className="space-y-4">
        <p className="text-xs leading-5 text-slate-500">Select a connected key for this Settings session to keep the intended workload lane visible. Final provider selection remains server-authoritative and tenant-scoped; this page never sends an organization selector.</p>
        {PROVIDER_DEFINITIONS.map((definition) => {
          const connection = findConnection(definition.id);
          const health = healthFor(definition.id);
          const testForProvider = testState?.provider === definition.id ? testState : null;
          return <div key={definition.id}><ProviderCard definition={definition} connection={connection} selected={connection?.id === selectedConnectionId} health={health || (testForProvider ? { healthy: testForProvider.status === "healthy", message: testForProvider.message } : undefined)} capabilitiesFromApi={capabilitiesFor(definition.id)} testing={testingProvider === definition.id} revoking={revokingId === connection?.id} onSelect={() => connection && setSelectedConnectionId(connection.id)} onTest={() => testProvider(definition.id)} onRevoke={() => connection && revokeConnection(connection)} />{testForProvider && <p className={`mt-2 text-xs ${testForProvider.status === "healthy" ? "text-emerald-200" : "text-red-200"}`} role="status">{definition.name}: {testForProvider.message}</p>}</div>;
        })}
      </div>

      <form onSubmit={saveFallback} className="rounded-2xl border border-white/[0.08] bg-[#111827] p-5">
        <div className="flex items-center gap-2"><Info className="h-4 w-4 text-violet-300" aria-hidden="true" /><h3 className="font-semibold text-white">Fallback and privacy policy</h3></div>
        <p className="mt-1 text-xs leading-5 text-slate-400">Routing remains server-authoritative. This policy controls what happens when the preferred provider is unavailable; it does not move keys between organizations or expose them to the client.</p>
        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
          <label className="text-xs text-slate-300">Fallback mode<select value={fallbackMode} onChange={(event) => setFallbackMode(event.target.value as "auto" | "ask" | "strict")} className="mt-2 w-full rounded-lg border border-white/[0.1] bg-slate-950 px-3 py-2.5 text-sm text-white focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-400/70"><option value="auto">AUTO · use the next allowed healthy provider</option><option value="ask">ASK · request confirmation before switching</option><option value="strict">STRICT · do not switch providers</option></select></label>
          <fieldset><legend className="text-xs text-slate-300">Privacy blocks</legend><div className="mt-2 grid gap-2 sm:grid-cols-2">{connectedProviders.length ? connectedProviders.map((definition) => <label key={definition.id} className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-slate-950/70 px-3 py-2 text-xs text-slate-300"><input type="checkbox" checked={deniedProviders.includes(definition.id)} onChange={() => toggleDenied(definition.id)} className="h-4 w-4 accent-violet-500" />Never use {definition.name}</label>) : <p className="text-xs text-slate-500">Add a provider key to configure privacy blocks.</p>}</div></fieldset>
        </div>
        <div className="mt-4 flex items-center justify-between gap-3"><p className="text-xs text-slate-500">Changing workspace fallback behavior requires an authorized admin role. A 403 is preserved and shown here.</p><button type="submit" disabled={savingFallback} className="inline-flex items-center justify-center gap-2 rounded-lg border border-violet-400/30 px-4 py-2.5 text-sm font-medium text-violet-100 hover:bg-violet-400/10 disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-violet-400/70">{savingFallback && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}Save fallback policy</button></div>
      </form>
    </div>
  );
}
