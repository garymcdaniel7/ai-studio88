"use client";

import { useState, useEffect } from "react";
import { Box, Plus, Layers, Package, Copy, Sparkles } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ObjectDNA {
  id: string;
  asset_id: string;
  category?: string;
  name?: string;
  material_type?: string;
  created_at: string;
}

interface ProductDNA {
  id: string;
  name: string;
  product_category?: string;
  brand?: string;
  created_at: string;
}

interface DigitalTwin {
  id: string;
  name: string;
  object_dna_id: string;
  status?: string;
  created_at: string;
}

type Tab = "objects" | "products" | "twins";

export default function ObjectIntelligencePage() {
  const [tab, setTab] = useState<Tab>("objects");
  const [objects, setObjects] = useState<ObjectDNA[]>([]);
  const [products, setProducts] = useState<ProductDNA[]>([]);
  const [twins, setTwins] = useState<DigitalTwin[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch(`${API_BASE}/api/v1/object-intelligence/object-dna`).then((r) => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/v1/object-intelligence/product-dna`).then((r) => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/v1/object-intelligence/digital-twins`).then((r) => r.json()).catch(() => []),
    ]).then(([obj, prod, tw]) => {
      setObjects(Array.isArray(obj) ? obj : []);
      setProducts(Array.isArray(prod) ? prod : []);
      setTwins(Array.isArray(tw) ? tw : []);
      setLoading(false);
    });
  }, []);

  const tabs: { key: Tab; label: string; icon: typeof Box; count: number }[] = [
    { key: "objects", label: "Object DNA", icon: Box, count: objects.length },
    { key: "products", label: "Product DNA", icon: Package, count: products.length },
    { key: "twins", label: "Digital Twins", icon: Copy, count: twins.length },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
            Object Intelligence <Sparkles className="h-5 w-5 text-purple-400" />
          </h1>
          <p className="text-sm text-gray-500">
            Manage Object DNA, Product DNA, and Digital Twins.
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-white/[0.06] pb-0">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-medium border-b-2 transition-colors ${
              tab === t.key
                ? "border-purple-500 text-purple-300"
                : "border-transparent text-gray-500 hover:text-gray-300"
            }`}
          >
            <t.icon className="h-3.5 w-3.5" />
            {t.label}
            <span className="rounded-full bg-white/[0.06] px-1.5 py-0.5 text-[10px]">{t.count}</span>
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <p className="text-xs text-gray-500 py-8 text-center">Loading...</p>
      ) : (
        <>
          {tab === "objects" && <ObjectList items={objects} />}
          {tab === "products" && <ProductList items={products} />}
          {tab === "twins" && <TwinList items={twins} />}
        </>
      )}
    </div>
  );
}

function ObjectList({ items }: { items: ObjectDNA[] }) {
  if (items.length === 0) {
    return (
      <div className="text-center py-12">
        <Box className="h-10 w-10 text-gray-700 mx-auto mb-3" />
        <p className="text-sm text-gray-500">No Object DNA profiles yet.</p>
        <p className="text-xs text-gray-600 mt-1">Create one from an asset to capture its visual properties.</p>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {items.map((obj) => (
        <div key={obj.id} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Box className="h-4 w-4 text-blue-400" />
            <p className="text-sm font-medium text-gray-200">{obj.name || obj.asset_id}</p>
          </div>
          {obj.category && <p className="text-xs text-gray-500">Category: {obj.category}</p>}
          {obj.material_type && <p className="text-xs text-gray-500">Material: {obj.material_type}</p>}
          <p className="text-[10px] text-gray-600 mt-2">{new Date(obj.created_at).toLocaleDateString()}</p>
        </div>
      ))}
    </div>
  );
}

function ProductList({ items }: { items: ProductDNA[] }) {
  if (items.length === 0) {
    return (
      <div className="text-center py-12">
        <Package className="h-10 w-10 text-gray-700 mx-auto mb-3" />
        <p className="text-sm text-gray-500">No Product DNA profiles yet.</p>
        <p className="text-xs text-gray-600 mt-1">Define products for commercial generation and virtual try-on.</p>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {items.map((prod) => (
        <div key={prod.id} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Package className="h-4 w-4 text-amber-400" />
            <p className="text-sm font-medium text-gray-200">{prod.name}</p>
          </div>
          {prod.product_category && <p className="text-xs text-gray-500">Category: {prod.product_category}</p>}
          {prod.brand && <p className="text-xs text-gray-500">Brand: {prod.brand}</p>}
          <p className="text-[10px] text-gray-600 mt-2">{new Date(prod.created_at).toLocaleDateString()}</p>
        </div>
      ))}
    </div>
  );
}

function TwinList({ items }: { items: DigitalTwin[] }) {
  if (items.length === 0) {
    return (
      <div className="text-center py-12">
        <Copy className="h-10 w-10 text-gray-700 mx-auto mb-3" />
        <p className="text-sm text-gray-500">No Digital Twins yet.</p>
        <p className="text-xs text-gray-600 mt-1">Create twins from Object DNA for version-controlled product visualization.</p>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {items.map((twin) => (
        <div key={twin.id} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Copy className="h-4 w-4 text-purple-400" />
            <p className="text-sm font-medium text-gray-200">{twin.name}</p>
          </div>
          {twin.status && (
            <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] ${
              twin.status === "active" ? "bg-green-500/10 text-green-400" : "bg-gray-500/10 text-gray-400"
            }`}>
              {twin.status}
            </span>
          )}
          <p className="text-[10px] text-gray-600 mt-2">{new Date(twin.created_at).toLocaleDateString()}</p>
        </div>
      ))}
    </div>
  );
}
