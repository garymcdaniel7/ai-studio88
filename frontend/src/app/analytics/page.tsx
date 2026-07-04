import { BarChart3, TrendingUp } from "lucide-react";

export default function AnalyticsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Analytics</h1>
        <p className="text-sm text-gray-500">Performance, costs, usage, provider reputation, and generation history.</p>
      </div>
      <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-8 text-center">
        <BarChart3 className="h-12 w-12 text-gray-600 mx-auto mb-3" />
        <p className="text-sm text-gray-400">Analytics dashboard coming soon</p>
        <p className="text-xs text-gray-600 mt-1">Track generation performance, costs, and content engagement across all platforms.</p>
      </div>
    </div>
  );
}
