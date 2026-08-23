/**
 * Integration status cards: ElevenLabs, Social Login, Ollama B2 cache.
 */
export function IntegrationsSection({ ollamaLocal }: { ollamaLocal: boolean }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-content-primary mb-3">Integrations</h3>
      <div className="grid grid-cols-3 gap-4">
        {/* ElevenLabs */}
        <div className="rounded-xl border border-amber-500/20 bg-surface-raised p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-content-primary">ElevenLabs</span>
            <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
          </div>
          <p className="text-xs text-status-warning font-medium">Paid Plan Required</p>
          <p className="text-[10px] text-content-muted mt-1">
            Free tier cannot use API voices. Upgrade at elevenlabs.io to enable voice generation.
          </p>
          <a href="https://elevenlabs.io/pricing" target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-[10px] text-purple-400 hover:text-purple-300 underline">
            View pricing →
          </a>
        </div>
        {/* Social Login */}
        <div className="rounded-xl border border-amber-500/20 bg-surface-raised p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-content-primary">Social Login (OAuth)</span>
            <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
          </div>
          <p className="text-xs text-status-warning font-medium">Setup Required</p>
          <p className="text-[10px] text-content-muted mt-1">
            Instagram/TikTok SSO needs a Meta Developer App. Register at developers.facebook.com, create an app, and add your OAuth credentials to .env.
          </p>
          <p className="text-[10px] text-gray-600 mt-1 font-mono">
            META_APP_ID=... META_APP_SECRET=...
          </p>
        </div>
        {/* Ollama B2 Cache */}
        <div className="rounded-xl border border-border-subtle bg-surface-raised p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-content-primary">Ollama → B2 Cache</span>
            <span className={`h-2.5 w-2.5 rounded-full ${ollamaLocal ? "bg-green-500" : "bg-gray-600"}`} />
          </div>
          <p className={`text-xs font-medium ${ollamaLocal ? "text-status-success" : "text-content-muted"}`}>
            {ollamaLocal ? "Ollama detected locally" : "Not detected"}
          </p>
          <p className="text-[10px] text-content-muted mt-1">
            Upload llama3.2 to B2 for GPU workers. Triggered from /models page or run manually.
          </p>
          <p className="text-[10px] text-gray-600 mt-1 font-mono">
            uv run python scripts/vast/cache_ollama_model.py --model llama3.2
          </p>
        </div>
      </div>
    </div>
  );
}
