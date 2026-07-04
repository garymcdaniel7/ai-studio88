import {
  FolderOpen,
  Cpu,
  DollarSign,
  Image,
  Calendar,
  Server,
  ArrowUpRight,
  Brain,
  Zap,
  TrendingUp,
} from "lucide-react";

function MetricCard({
  icon: Icon,
  label,
  value,
  subtitle,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  subtitle: string;
  color: string;
}) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
      <div className="flex items-center gap-3">
        <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${color}`}>
          <Icon className="h-5 w-5 text-white" />
        </div>
        <div>
          <p className="text-xs text-gray-500">{label}</p>
          <p className="text-2xl font-bold text-white">{value}</p>
          <p className="text-xs text-gray-500">{subtitle}</p>
        </div>
      </div>
    </div>
  );
}

export default function HomePage() {
  return (
    <div className="space-y-6">
      {/* Hero Greeting */}
      <div>
        <h1 className="text-2xl font-bold text-white">
          Good evening, Gary 👋
        </h1>
        <p className="text-gray-500">
          Your AI Studio is ready to create something amazing.
        </p>
      </div>

      {/* Quick Actions */}
      <div className="flex gap-3">
        <button className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 transition-colors">
          🆕 New Project
        </button>
        <button className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-300 hover:bg-white/[0.06] transition-colors">
          🧠 AI Brain Chat
        </button>
        <button className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-300 hover:bg-white/[0.06] transition-colors">
          📤 Upload Asset
        </button>
        <button className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-300 hover:bg-white/[0.06] transition-colors">
          🎨 Create Image
        </button>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-6 gap-4">
        <MetricCard icon={FolderOpen} label="Active Projects" value="7" subtitle="2 today" color="bg-blue-600" />
        <MetricCard icon={Cpu} label="Jobs Running" value="12" subtitle="View queue" color="bg-purple-600" />
        <MetricCard icon={DollarSign} label="GPU Spend (hr)" value="$0.84" subtitle="↓ 8% vs yesterday" color="bg-green-600" />
        <MetricCard icon={Image} label="Assets" value="1,283" subtitle="+18 today" color="bg-amber-600" />
        <MetricCard icon={Calendar} label="Scheduled Posts" value="18" subtitle="View calendar" color="bg-pink-600" />
        <MetricCard icon={Server} label="Fleet Workers" value="2" subtitle="All healthy" color="bg-teal-600" />
      </div>

      {/* Three Column Grid */}
      <div className="grid grid-cols-3 gap-6">
        {/* Active Productions */}
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-white">Active Productions</h3>
            <button className="text-xs text-purple-400 hover:text-purple-300">View all</button>
          </div>
          <div className="space-y-3">
            {[
              { name: "Dubai Luxury Campaign", type: "Video Commercial", progress: 75 },
              { name: "Melissa Story – Episode 4", type: "Short Film", progress: 42 },
              { name: "Nike Product Launch", type: "Commercial", progress: 90 },
              { name: "New Collection Drop", type: "Social Campaign", progress: 30 },
            ].map((p) => (
              <div key={p.name} className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-white/[0.05]" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-white truncate">{p.name}</p>
                  <p className="text-xs text-gray-500">{p.type}</p>
                </div>
                <span className="text-xs text-gray-400">{p.progress}%</span>
              </div>
            ))}
          </div>
        </div>

        {/* Jobs Overview */}
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-white">Jobs Overview</h3>
          </div>
          <div className="flex items-center justify-center py-4">
            <div className="relative h-32 w-32">
              <div className="absolute inset-0 flex items-center justify-center">
                <div>
                  <p className="text-3xl font-bold text-white text-center">128</p>
                  <p className="text-xs text-gray-500 text-center">Total Jobs</p>
                </div>
              </div>
              {/* Placeholder for donut chart */}
              <svg className="h-32 w-32 -rotate-90" viewBox="0 0 36 36">
                <circle cx="18" cy="18" r="14" fill="none" stroke="#1a1a3e" strokeWidth="4" />
                <circle cx="18" cy="18" r="14" fill="none" stroke="#10b981" strokeWidth="4" strokeDasharray="47 100" />
                <circle cx="18" cy="18" r="14" fill="none" stroke="#6366f1" strokeWidth="4" strokeDasharray="8 100" strokeDashoffset="-47" />
                <circle cx="18" cy="18" r="14" fill="none" stroke="#f59e0b" strokeWidth="4" strokeDasharray="12 100" strokeDashoffset="-55" />
                <circle cx="18" cy="18" r="14" fill="none" stroke="#ef4444" strokeWidth="4" strokeDasharray="5 100" strokeDashoffset="-67" />
              </svg>
            </div>
          </div>
          <div className="mt-2 space-y-1.5">
            {[
              { label: "Completed", value: "68 (53%)", color: "bg-green-500" },
              { label: "Running", value: "12 (9%)", color: "bg-indigo-500" },
              { label: "Queued", value: "18 (14%)", color: "bg-amber-500" },
              { label: "Failed", value: "8 (6%)", color: "bg-red-500" },
              { label: "Cancelled", value: "22 (18%)", color: "bg-gray-500" },
            ].map((s) => (
              <div key={s.label} className="flex items-center gap-2 text-xs">
                <span className={`h-2 w-2 rounded-full ${s.color}`} />
                <span className="text-gray-400">{s.label}</span>
                <span className="ml-auto text-gray-300">{s.value}</span>
              </div>
            ))}
          </div>
          <button className="mt-3 w-full rounded-lg border border-white/[0.08] py-2 text-xs text-gray-400 hover:bg-white/[0.03]">
            Open Job Queue
          </button>
        </div>

        {/* AI Brain Suggestions */}
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-white">AI Brain Suggestions</h3>
            <button className="text-xs text-purple-400 hover:text-purple-300">View all</button>
          </div>
          <div className="space-y-3">
            {[
              { icon: Zap, title: "Reuse FLUX workflow", desc: "You used this workflow in your last 3 image projects." },
              { icon: TrendingUp, title: "Optimize GPU costs", desc: "Switch to Spot instances to save up to 32%." },
              { icon: ArrowUpRight, title: "Upscale ready", desc: "12 assets can be upscaled to improve quality." },
            ].map((s) => (
              <div key={s.title} className="flex items-start gap-3 rounded-lg border border-white/[0.04] bg-white/[0.02] p-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-600/20">
                  <s.icon className="h-4 w-4 text-purple-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-white">{s.title}</p>
                  <p className="text-xs text-gray-500">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
          <button className="mt-3 w-full rounded-lg bg-purple-600/10 py-2 text-xs text-purple-400 hover:bg-purple-600/20">
            Open Brain
          </button>
        </div>
      </div>

      {/* System Status Bar */}
      <div className="flex items-center gap-6 rounded-xl border border-white/[0.06] bg-[#12122a] px-5 py-3">
        <span className="text-xs font-medium text-gray-400">System Status</span>
        {[
          { name: "ComfyUI", status: "Online", color: "text-green-400" },
          { name: "Vast.ai", status: "Connected", color: "text-green-400" },
          { name: "Backblaze", status: "Online", color: "text-green-400" },
          { name: "HuggingFace", status: "Online", color: "text-green-400" },
        ].map((s) => (
          <div key={s.name} className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${s.color.replace("text-", "bg-")}`} />
            <span className="text-xs text-gray-300">{s.name}</span>
            <span className={`text-xs ${s.color}`}>{s.status}</span>
          </div>
        ))}
        <button className="ml-auto text-xs text-purple-400 hover:text-purple-300">
          View all systems →
        </button>
      </div>
    </div>
  );
}
