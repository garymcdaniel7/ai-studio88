import { Film, Server, Cpu, DollarSign, Plus } from "lucide-react";

export default function ProductionPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Production</h1>
          <p className="text-sm text-gray-500">Jobs, workers, render fleet, execution engine, and queue management.</p>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 hover:bg-white/[0.06]">
            <Server className="h-4 w-4" /> Launch Worker
          </button>
          <button className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700">
            <Plus className="h-4 w-4" /> New Job
          </button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Active Workers", value: "0", icon: Server, color: "bg-purple-600" },
          { label: "Jobs in Queue", value: "0", icon: Cpu, color: "bg-blue-600" },
          { label: "GPU Spend Today", value: "$0.00", icon: DollarSign, color: "bg-green-600" },
          { label: "Fleet Status", value: "Idle", icon: Film, color: "bg-amber-600" },
        ].map((m) => (
          <div key={m.label} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 flex items-center gap-3">
            <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${m.color}`}>
              <m.icon className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="text-xs text-gray-500">{m.label}</p>
              <p className="text-lg font-bold text-white">{m.value}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-8 text-center">
        <Cpu className="h-12 w-12 text-gray-600 mx-auto mb-3" />
        <p className="text-sm text-gray-400">No active workers</p>
        <p className="text-xs text-gray-600 mt-1">Launch a GPU worker to start generating content.</p>
      </div>
    </div>
  );
}
