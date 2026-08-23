/**
 * Worker Services status grid — availability tracks the GPU worker state.
 */
export function WorkerServicesGrid({ gpuActive }: { gpuActive: boolean }) {
  const isOnline = gpuActive; // These are available when GPU worker is active
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-raised p-5">
      <h3 className="text-sm font-semibold text-content-primary mb-3">Worker Services</h3>
      <p className="text-[10px] text-content-muted mb-3">These services run on the GPU worker. Status shown when a worker is active.</p>
      <div className="grid grid-cols-3 gap-3">
        {[
          { name: "FFmpeg", desc: "Video editing & assembly", check: "ffmpeg", port: null },
          { name: "SimpleTuner", desc: "LoRA training engine", check: "simpletuner", port: null },
          { name: "MOSS-TTS", desc: "Voice generation & cloning", check: "moss-tts", port: "18083" },
        ].map((svc) => {
          return (
            <div key={svc.name} className="rounded-lg border border-border-subtle bg-white/[0.02] p-3">
              <div className="flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${isOnline ? "bg-amber-400" : "bg-gray-600"}`} />
                <p className="text-xs font-medium text-content-primary">{svc.name}</p>
              </div>
              <p className="text-[10px] text-content-muted mt-1">{svc.desc}</p>
              <p className="text-[10px] text-content-muted mt-0.5">
                {isOnline ? "Available on worker" : "Requires GPU worker"}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
