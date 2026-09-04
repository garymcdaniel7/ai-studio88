/**
 * Live grid of backend service connection cards.
 */
export function ServiceConnectionsGrid({
  services,
  gpuActive,
  thunderApiConnected,
}: {
  services: Record<string, Record<string, unknown>>;
  gpuActive: boolean;
  thunderApiConnected: boolean;
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-content-primary mb-3">Service Connections</h3>
      <div className="grid grid-cols-4 gap-3">
        {Object.entries(services).map(([name, info]: [string, Record<string, unknown>]) => {
          const isConnected = Boolean(info.connected);
          // Determine dot color: green=active, amber=API connected but no instance, gray=offline
          let dotColor = "bg-gray-600";
          if (name === "thunder" || name === "thundercompute" || name === "thunder_compute") {
            if (gpuActive) dotColor = "bg-green-500";
            else if (thunderApiConnected) dotColor = "bg-amber-400";
          } else if (info.connected) {
            dotColor = "bg-green-500";
          }

          return (
            <div key={name} className="rounded-xl border border-border-subtle bg-surface-raised p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-content-primary capitalize">
                  {name.replace(/_/g, " ")}
                </span>
                <span className={`h-2.5 w-2.5 rounded-full ${dotColor}`} />
              </div>
              <p className={`text-xs font-medium ${isConnected ? "text-status-success" : (name.includes("thunder") && thunderApiConnected) ? "text-status-warning" : "text-content-muted"}`}>
                {isConnected ? "Connected" : (name.includes("thunder") && thunderApiConnected) ? "API Ready" : String(info.mode || "Offline")}
              </p>
              <p className="text-[10px] text-content-muted mt-1">
                {isConnected
                  ? String(info.username || info.bucket || info.version || (info.voices_available ? `${info.voices_available} voices` : "") || (info.cached_models ? `${info.cached_models} models` : "") || info.tier || "OK")
                  : String(info.error || info.note || "Not configured")}
              </p>
              {info.response_ms !== undefined && (
                <p className="text-[10px] text-gray-600 mt-1">{(info.response_ms as number).toFixed(0)}ms response</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
