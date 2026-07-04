import { Settings, Server, Cloud, HardDrive, Brain, Mic, DollarSign, Shield } from "lucide-react";

const services = [
  { name: "ComfyUI", status: "Offline", desc: "Launch a worker to connect", connected: false },
  { name: "Vast.ai", status: "Connected", desc: "$22.72 balance", connected: true },
  { name: "Backblaze B2", status: "Online", desc: "ai-studio88 bucket", connected: true },
  { name: "HuggingFace", status: "Online", desc: "chachi88 (authenticated)", connected: true },
  { name: "Supabase", status: "Online", desc: "Tables accessible", connected: true },
  { name: "ElevenLabs", status: "Pending", desc: "Plan activation needed", connected: false },
  { name: "Model Cache", status: "Online", desc: "2 models (11.2GB)", connected: true },
  { name: "RunPod", status: "Not configured", desc: "Future provider", connected: false },
];

export default function AdminPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Admin</h1>
        <p className="text-sm text-gray-500">Provider connections, infrastructure, and platform settings.</p>
      </div>

      {/* Service Status Grid */}
      <div>
        <h3 className="text-sm font-semibold text-white mb-3">Service Connections</h3>
        <div className="grid grid-cols-4 gap-3">
          {services.map((svc) => (
            <div key={svc.name} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-white">{svc.name}</span>
                <span className={`h-2 w-2 rounded-full ${svc.connected ? "bg-green-500" : "bg-gray-600"}`} />
              </div>
              <p className={`text-xs ${svc.connected ? "text-green-400" : "text-gray-500"}`}>{svc.status}</p>
              <p className="text-[10px] text-gray-500 mt-1">{svc.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <Server className="h-6 w-6 text-purple-400 mb-3" />
          <h3 className="text-sm font-semibold text-white">GPU Workers</h3>
          <p className="text-xs text-gray-500 mt-1">Launch, monitor, and manage GPU fleet</p>
          <button className="mt-3 rounded-lg bg-purple-600/20 px-3 py-1.5 text-xs text-purple-400 hover:bg-purple-600/30">
            Manage Workers
          </button>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <DollarSign className="h-6 w-6 text-green-400 mb-3" />
          <h3 className="text-sm font-semibold text-white">Cost Controls</h3>
          <p className="text-xs text-gray-500 mt-1">Budget limits, spend tracking, alerts</p>
          <button className="mt-3 rounded-lg bg-green-600/20 px-3 py-1.5 text-xs text-green-400 hover:bg-green-600/30">
            View Costs
          </button>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <Shield className="h-6 w-6 text-amber-400 mb-3" />
          <h3 className="text-sm font-semibold text-white">Provider Reputation</h3>
          <p className="text-xs text-gray-500 mt-1">Host reliability, blacklist, preferred hosts</p>
          <button className="mt-3 rounded-lg bg-amber-600/20 px-3 py-1.5 text-xs text-amber-400 hover:bg-amber-600/30">
            View Reputation
          </button>
        </div>
      </div>
    </div>
  );
}
