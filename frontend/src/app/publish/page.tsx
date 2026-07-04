import { Send, Calendar, Plus } from "lucide-react";

export default function PublishPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Publish</h1>
          <p className="text-sm text-gray-500">Social publishing, scheduling, campaigns, and content calendar.</p>
        </div>
        <button className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700">
          <Plus className="h-4 w-4" /> Schedule Post
        </button>
      </div>
      <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-8 text-center">
        <Calendar className="h-12 w-12 text-gray-600 mx-auto mb-3" />
        <p className="text-sm text-gray-400">Content calendar coming soon</p>
        <p className="text-xs text-gray-600 mt-1">Schedule posts across Instagram, TikTok, YouTube, and more.</p>
      </div>
    </div>
  );
}
