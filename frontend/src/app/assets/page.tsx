import { Image, Upload, Search, Filter, LayoutGrid } from "lucide-react";

export default function AssetsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Assets</h1>
          <p className="text-sm text-gray-500">Manage images, videos, objects, backgrounds, and brand assets.</p>
        </div>
        <button className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700">
          <Upload className="h-4 w-4" /> Upload Asset
        </button>
      </div>

      <div className="flex gap-3">
        {["All", "Images", "Videos", "Objects", "Backgrounds", "Wardrobe", "Products", "Brand"].map((t) => (
          <button key={t} className="rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-1.5 text-xs text-gray-400 hover:text-white hover:bg-white/[0.06] first:bg-purple-600/20 first:text-purple-400 first:border-purple-500/30">
            {t}
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-8 text-center">
        <Image className="h-12 w-12 text-gray-600 mx-auto mb-3" />
        <p className="text-sm text-gray-400">Upload assets to get started</p>
        <p className="text-xs text-gray-600 mt-1">Every asset gets Object DNA — the AI understands what it is and how to use it.</p>
      </div>
    </div>
  );
}
