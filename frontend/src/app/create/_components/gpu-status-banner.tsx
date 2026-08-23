"use client";

/**
 * GPU worker status banners for the image tab — offline, no models loaded,
 * or selected model not loaded (with one-click switch).
 */
export function GpuStatusBanners({
  gpuOnline,
  gpuReadyModels,
  selectedModel,
  onSelectModel,
}: {
  gpuOnline: boolean | null;
  gpuReadyModels: Set<string>;
  selectedModel: string;
  onSelectModel: (modelId: string) => void;
}) {
  return (
    <>
      {gpuOnline === false && (
        <div className="mb-2 rounded-lg border border-orange-500/30 bg-orange-500/5 px-4 py-3">
          <div className="flex items-center gap-2 mb-1">
            <span className="h-2 w-2 rounded-full bg-orange-400 animate-pulse" />
            <span className="text-sm font-medium text-orange-300">GPU Worker Offline</span>
          </div>
          <p className="text-xs text-orange-300/70 ml-4">
            No GPU connected — image generation unavailable. To generate images:
          </p>
          <ol className="text-[11px] text-orange-300/60 ml-8 mt-1 list-decimal space-y-0.5">
            <li>Launch a GPU worker from <a href="/admin/fleet" className="text-purple-400 underline">Admin → Fleet</a></li>
            <li>Wait for it to boot (~2 min) and load models</li>
            <li>Establish SSH tunnel: <code className="bg-black/30 px-1 rounded">ssh -N -L 8188:localhost:8188 -p PORT root@HOST</code></li>
          </ol>
        </div>
      )}
      {gpuOnline === true && gpuReadyModels.size === 0 && (
        <div className="mb-2 flex items-center gap-2 rounded-lg border border-yellow-500/30 bg-yellow-500/5 px-3 py-2">
          <span className="h-2 w-2 rounded-full bg-yellow-400" />
          <span className="text-xs text-yellow-300">GPU worker connected but no models loaded. Deploy a model from Admin → Models.</span>
        </div>
      )}
      {gpuOnline === true && gpuReadyModels.size > 0 && !gpuReadyModels.has(selectedModel) && (
        <div className="mb-2 flex items-center gap-2 rounded-lg border border-yellow-500/30 bg-yellow-500/5 px-3 py-2">
          <span className="h-2 w-2 rounded-full bg-yellow-400" />
          <span className="text-xs text-yellow-300">
            Selected model not loaded on GPU. Available: {[...gpuReadyModels].join(", ")}.
          </span>
          <button
            onClick={() => { const first = [...gpuReadyModels][0]; if (first) onSelectModel(first); }}
            className="ml-auto text-xs text-purple-400 hover:text-purple-300 underline"
          >
            Switch
          </button>
        </div>
      )}
    </>
  );
}
