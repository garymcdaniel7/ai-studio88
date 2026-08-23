"use client";

import { useState } from "react";

// ---------------------------------------------------------------------------
// Talent Edit Modal — Full editing form for a talent record
// ---------------------------------------------------------------------------

export function TalentEditModal({
  talent,
  onClose,
  onSave,
}: {
  talent: Record<string, unknown>;
  onClose: () => void;
  onSave: (data: Record<string, unknown>) => Promise<void>;
}) {
  const [form, setForm] = useState({
    name: (talent.name as string) || "",
    bio: (talent.bio as string) || "",
    age: (talent.age as string) || "",
    height: (talent.height as string) || "",
    ethnicity: (talent.ethnicity as string) || "",
    default_style: (talent.default_style as string) || "model",
    gender: (talent.gender as string) || "",
    hair_color: (talent.hair_color as string) || "",
    eye_color: (talent.eye_color as string) || "",
    body_type: (talent.body_type as string) || "",
    visual_style: (talent.visual_style as string) || "",
    best_for: (talent.best_for as string) || "",
    persona: (talent.persona as string) || "",
    trigger_words: (talent.trigger_words as string) || "",
    negative_prompt: (talent.negative_prompt as string) || "",
    // Wardrobe fields
    garment_type: (talent.garment_type as string) || "",
    fabric: (talent.fabric as string) || "",
    color: (talent.color as string) || "",
    brand: (talent.brand as string) || "",
    size_range: (talent.size_range as string) || "",
    season: (talent.season as string) || "",
    category: (talent.category as string) || "",
    // Product fields
    product_name: (talent.product_name as string) || "",
    dimensions: (talent.dimensions as string) || "",
    sku: (talent.sku as string) || "",
    // Background/Set fields
    location_type: (talent.location_type as string) || "",
    lighting: (talent.lighting as string) || "",
    time_of_day: (talent.time_of_day as string) || "",
    mood: (talent.mood as string) || "",
  });
  const [saving, setSaving] = useState(false);

  function update(key: string, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    setSaving(true);
    const creative_dna = {
      visual_style: form.visual_style,
      best_for: form.best_for,
      persona: form.persona,
    };
    const payload: Record<string, unknown> = {
      name: form.name,
      bio: form.bio,
      default_style: form.default_style,
      visual_style: form.visual_style || null,
      best_for: form.best_for || null,
      persona: form.persona || null,
      trigger_words: form.trigger_words || null,
      negative_prompt: form.negative_prompt || null,
      creative_dna,
    };
    const type = form.default_style;
    if (type === "model" || type === "influencer" || type === "character" || type === "voice") {
      payload.age = form.age || null;
      payload.height = form.height || null;
      payload.ethnicity = form.ethnicity || null;
      payload.gender = form.gender || null;
      payload.hair_color = form.hair_color || null;
      payload.eye_color = form.eye_color || null;
      payload.body_type = form.body_type || null;
    } else if (type === "wardrobe") {
      payload.garment_type = form.garment_type || null;
      payload.fabric = form.fabric || null;
      payload.color = form.color || null;
      payload.brand = form.brand || null;
      payload.size_range = form.size_range || null;
      payload.season = form.season || null;
      payload.category = form.category || null;
    } else if (type === "product") {
      payload.product_name = form.product_name || null;
      payload.brand = form.brand || null;
      payload.category = form.category || null;
      payload.dimensions = form.dimensions || null;
      payload.sku = form.sku || null;
      payload.color = form.color || null;
    } else if (type === "background") {
      payload.location_type = form.location_type || null;
      payload.lighting = form.lighting || null;
      payload.time_of_day = form.time_of_day || null;
      payload.mood = form.mood || null;
    }
    await onSave(payload);
    setSaving(false);
  }

  const inputClass = "w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-white placeholder:text-content-muted focus:border-purple-500 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-2xl border border-border-default bg-surface-overlay p-6 shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold text-content-primary">Edit Talent</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg text-content-tertiary hover:text-content-primary hover:bg-surface-hover">
            <span className="text-lg">&times;</span>
          </button>
        </div>

        <div className="space-y-4">
          {/* Basic Info */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Name</label>
              <input value={form.name} onChange={(e) => update("name", e.target.value)} placeholder="Full name" className={inputClass} />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Type / Style</label>
              <select value={form.default_style} onChange={(e) => update("default_style", e.target.value)} className={inputClass}>
                <option value="model">Model / Person</option>
                <option value="character">Character</option>
                <option value="voice">Voice</option>
                <option value="influencer">Influencer</option>
                <option value="wardrobe">Wardrobe / Clothing</option>
                <option value="product">Product</option>
                <option value="background">Background / Set</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Bio / Description</label>
            <textarea value={form.bio} onChange={(e) => update("bio", e.target.value)} placeholder="Describe this talent..." className={inputClass + " resize-none"} rows={3} />
          </div>

          {/* Physical Attributes — only for person types */}
          {(form.default_style === "model" || form.default_style === "influencer" || form.default_style === "character" || form.default_style === "voice") && (
          <div className="rounded-lg border border-border-subtle p-4">
            <p className="text-xs font-semibold text-content-secondary mb-3">Physical Attributes</p>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Age</label>
                <input value={form.age} onChange={(e) => update("age", e.target.value)} placeholder="28" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Height</label>
                <input value={form.height} onChange={(e) => update("height", e.target.value)} placeholder="5&apos;9&quot;" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Ethnicity</label>
                <input value={form.ethnicity} onChange={(e) => update("ethnicity", e.target.value)} placeholder="e.g. Mediterranean" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Gender</label>
                <input value={form.gender} onChange={(e) => update("gender", e.target.value)} placeholder="Female" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Hair Color</label>
                <input value={form.hair_color} onChange={(e) => update("hair_color", e.target.value)} placeholder="Dark brown" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Eye Color</label>
                <input value={form.eye_color} onChange={(e) => update("eye_color", e.target.value)} placeholder="Hazel" className={inputClass} />
              </div>
            </div>
          </div>
          )}

          {/* Wardrobe Details */}
          {form.default_style === "wardrobe" && (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4">
            <p className="text-xs font-semibold text-amber-300 mb-3">Wardrobe Details</p>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Garment Type</label>
                <select value={form.garment_type} onChange={(e) => update("garment_type", e.target.value)} className={inputClass}>
                  <option value="">Select...</option>
                  <option value="dress">Dress</option>
                  <option value="top">Top / Blouse</option>
                  <option value="bottom">Bottom / Pants</option>
                  <option value="outerwear">Outerwear / Jacket</option>
                  <option value="shoes">Shoes</option>
                  <option value="accessory">Accessory</option>
                  <option value="jewelry">Jewelry</option>
                  <option value="bag">Bag / Purse</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Color</label>
                <input value={form.color} onChange={(e) => update("color", e.target.value)} placeholder="Black, gold" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Fabric</label>
                <input value={form.fabric} onChange={(e) => update("fabric", e.target.value)} placeholder="Silk" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Brand</label>
                <input value={form.brand} onChange={(e) => update("brand", e.target.value)} placeholder="Brand name" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Season</label>
                <select value={form.season} onChange={(e) => update("season", e.target.value)} className={inputClass}>
                  <option value="">Any</option>
                  <option value="spring">Spring</option>
                  <option value="summer">Summer</option>
                  <option value="fall">Fall</option>
                  <option value="winter">Winter</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Size Range</label>
                <input value={form.size_range} onChange={(e) => update("size_range", e.target.value)} placeholder="XS-XL" className={inputClass} />
              </div>
            </div>
          </div>
          )}

          {/* Product Details */}
          {form.default_style === "product" && (
          <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-4">
            <p className="text-xs font-semibold text-cyan-300 mb-3">Product Details</p>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Product Name</label>
                <input value={form.product_name} onChange={(e) => update("product_name", e.target.value)} placeholder="Product name" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Brand</label>
                <input value={form.brand} onChange={(e) => update("brand", e.target.value)} placeholder="Brand" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Category</label>
                <input value={form.category} onChange={(e) => update("category", e.target.value)} placeholder="Beauty, Tech, etc." className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Color</label>
                <input value={form.color} onChange={(e) => update("color", e.target.value)} placeholder="Rose gold" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Dimensions</label>
                <input value={form.dimensions} onChange={(e) => update("dimensions", e.target.value)} placeholder="8oz, 10x5cm" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">SKU</label>
                <input value={form.sku} onChange={(e) => update("sku", e.target.value)} placeholder="SKU-12345" className={inputClass} />
              </div>
            </div>
          </div>
          )}

          {/* Background / Set Details */}
          {form.default_style === "background" && (
          <div className="rounded-lg border border-green-500/20 bg-green-500/5 p-4">
            <p className="text-xs font-semibold text-green-300 mb-3">Background / Set Details</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Location Type</label>
                <select value={form.location_type} onChange={(e) => update("location_type", e.target.value)} className={inputClass}>
                  <option value="">Select...</option>
                  <option value="studio">Studio</option>
                  <option value="outdoor">Outdoor</option>
                  <option value="urban">Urban</option>
                  <option value="interior">Interior</option>
                  <option value="beach">Beach</option>
                  <option value="abstract">Abstract</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Lighting</label>
                <select value={form.lighting} onChange={(e) => update("lighting", e.target.value)} className={inputClass}>
                  <option value="">Select...</option>
                  <option value="natural">Natural</option>
                  <option value="golden_hour">Golden Hour</option>
                  <option value="studio">Studio</option>
                  <option value="neon">Neon</option>
                  <option value="dramatic">Dramatic</option>
                  <option value="soft">Soft</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Time of Day</label>
                <select value={form.time_of_day} onChange={(e) => update("time_of_day", e.target.value)} className={inputClass}>
                  <option value="">Any</option>
                  <option value="morning">Morning</option>
                  <option value="golden_hour">Golden Hour</option>
                  <option value="sunset">Sunset</option>
                  <option value="night">Night</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Mood</label>
                <input value={form.mood} onChange={(e) => update("mood", e.target.value)} placeholder="Warm, luxurious" className={inputClass} />
              </div>
            </div>
          </div>
          )}

          {/* Creative DNA */}
          <div className="rounded-lg border border-purple-500/20 bg-purple-500/5 p-4">
            <p className="text-xs font-semibold text-purple-300 mb-3">Creative DNA</p>
            <div className="space-y-3">
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Visual Style (comma-separated)</label>
                <input value={form.visual_style} onChange={(e) => update("visual_style", e.target.value)} placeholder="Elegant, Confident, Sophisticated" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Best For (comma-separated)</label>
                <input value={form.best_for} onChange={(e) => update("best_for", e.target.value)} placeholder="Luxury, Fashion, Beauty" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Persona (comma-separated)</label>
                <input value={form.persona} onChange={(e) => update("persona", e.target.value)} placeholder="Confident, Modern, Empowered" className={inputClass} />
              </div>
            </div>
          </div>

          {/* Generation Settings */}
          <div className="rounded-lg border border-border-subtle p-4">
            <p className="text-xs font-semibold text-content-secondary mb-3">Generation Settings</p>
            <div className="space-y-3">
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Trigger Words (for LoRA prompts)</label>
                <input value={form.trigger_words} onChange={(e) => update("trigger_words", e.target.value)} placeholder="ohwx, melissa_style" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Negative Prompt (always exclude)</label>
                <input value={form.negative_prompt} onChange={(e) => update("negative_prompt", e.target.value)} placeholder="blurry, low quality, deformed" className={inputClass} />
              </div>
            </div>
          </div>

          {/* Save */}
          <button
            onClick={handleSave}
            disabled={saving || !form.name.trim()}
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
