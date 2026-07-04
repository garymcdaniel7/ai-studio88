"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Image, Upload, Search, Filter, LayoutGrid } from "lucide-react";

interface Asset {
  id: string;
  filename: string;
  url: string;
  type: string;
  created_at: string;
}

export default function AssetsPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [uploading, setUploading] = useState(false);
  const [activeFilter, setActiveFilter] = useState("All");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchAssets = useCallback(async () => {
    try {
      const resp = await fetch("http://localhost:8000/api/v1/assets");
      if (resp.ok) {
        const data = await resp.json();
        setAssets(Array.isArray(data) ? data : data.assets || []);
      }
    } catch {
      // backend not available
    }
  }, []);

  useEffect(() => {
    fetchAssets();
  }, [fetchAssets]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    if (!e.target.files || e.target.files.length === 0) return;
    setUploading(true);

    try {
      const formData = new FormData();
      Array.from(e.target.files).forEach((file) => {
        formData.append("file", file);
      });

      const resp = await fetch("http://localhost:8000/api/v1/assets", {
        method: "POST",
        body: formData,
      });

      if (resp.ok) {
        await fetchAssets();
      } else {
        const err = await resp.json().catch(() => ({}));
        alert(err.detail || "Upload failed");
      }
    } catch {
      alert("Cannot reach backend. Is the API server running?");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  const filters = ["All", "Images", "Videos", "Objects", "Backgrounds", "Wardrobe", "Products", "Brand"];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Assets</h1>
          <p className="text-sm text-gray-500">Manage images, videos, objects, backgrounds, and brand assets.</p>
        </div>
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
        >
          <Upload className="h-4 w-4" /> {uploading ? "Uploading..." : "Upload Asset"}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,video/*"
          multiple
          className="hidden"
          onChange={handleUpload}
        />
      </div>

      <div className="flex gap-3">
        {filters.map((t) => (
          <button
            key={t}
            onClick={() => setActiveFilter(t)}
            className={`rounded-lg border px-3 py-1.5 text-xs hover:text-white hover:bg-white/[0.06] ${
              activeFilter === t
                ? "bg-purple-600/20 text-purple-400 border-purple-500/30"
                : "border-white/[0.06] bg-white/[0.03] text-gray-400"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {assets.length === 0 ? (
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-8 text-center">
          <Image className="h-12 w-12 text-gray-600 mx-auto mb-3" />
          <p className="text-sm text-gray-400">Upload assets to get started</p>
          <p className="text-xs text-gray-600 mt-1">Every asset gets Object DNA — the AI understands what it is and how to use it.</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {assets.map((asset) => (
            <div
              key={asset.id}
              className="group rounded-xl border border-white/[0.06] bg-[#12122a] overflow-hidden hover:border-purple-500/30 transition-all"
            >
              <div className="aspect-square bg-white/[0.02] flex items-center justify-center overflow-hidden">
                {asset.type?.startsWith("image") ? (
                  <img
                    src={asset.url}
                    alt={asset.filename}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <Image className="h-8 w-8 text-gray-600" />
                )}
              </div>
              <div className="p-2">
                <p className="text-xs text-gray-300 truncate">{asset.filename}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
