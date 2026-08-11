"use client";

import { useState, useEffect } from "react";
import type { TalentRecord } from "../_hooks/use-talent-data";

interface EditTalentModalProps {
  open: boolean;
  talent: TalentRecord | null;
  onClose: () => void;
  onSave: (id: string, updates: Record<string, unknown>) => Promise<boolean>;
}

const EDITABLE_FIELDS = [
  { key: "name", label: "Name", type: "text" as const, required: true },
  { key: "bio", label: "Bio / Description", type: "textarea" as const },
  { key: "height", label: "Height", type: "text" as const },
  { key: "hair_color", label: "Hair Color", type: "text" as const },
  { key: "eye_color", label: "Eye Color", type: "text" as const },
  { key: "body_type", label: "Body Type", type: "text" as const },
  { key: "visual_style", label: "Visual Style", type: "text" as const },
  { key: "persona", label: "Persona", type: "textarea" as const },
  { key: "negative_prompt", label: "Negative Prompt", type: "textarea" as const },
  { key: "trigger_word", label: "LoRA Trigger Word", type: "text" as const },
];

/**
 * Modal for editing an existing talent's attributes.
 */
export function EditTalentModal({ open, talent, onClose, onSave }: EditTalentModalProps) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (talent && open) {
      const initial: Record<string, string> = {};
      for (const field of EDITABLE_FIELDS) {
        initial[field.key] = String(talent[field.key] || "");
      }
      setValues(initial);
    }
  }, [talent, open]);

  if (!open || !talent) return null;

  async function handleSave() {
    setSubmitting(true);
    const updates: Record<string, unknown> = {};
    for (const field of EDITABLE_FIELDS) {
      const val = values[field.key]?.trim();
      if (val !== String(talent![field.key] || "").trim()) {
        updates[field.key] = val || null;
      }
    }
    const success = await onSave(talent!.id as string, updates);
    setSubmitting(false);
    if (success) onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-lg max-h-[80vh] overflow-y-auto rounded-2xl border border-white/[0.08] bg-[#0f0f24] p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-bold text-white mb-4">Edit {values.name || "Talent"}</h2>
        <div className="space-y-3">
          {EDITABLE_FIELDS.map((field) => (
            <div key={field.key}>
              <label className="text-xs text-gray-400 block mb-1">
                {field.label} {field.required && <span className="text-red-400">*</span>}
              </label>
              {field.type === "textarea" ? (
                <textarea
                  value={values[field.key] || ""}
                  onChange={(e) => setValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                  rows={2}
                  className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none resize-none focus:border-purple-500/50"
                />
              ) : (
                <input
                  value={values[field.key] || ""}
                  onChange={(e) => setValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                  className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none focus:border-purple-500/50"
                />
              )}
            </div>
          ))}
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="px-4 py-2 text-xs text-gray-400 hover:text-white">Cancel</button>
          <button
            onClick={handleSave}
            disabled={!values.name?.trim() || submitting}
            className="px-4 py-2 rounded-lg bg-purple-600 text-xs font-medium text-white hover:bg-purple-700 disabled:opacity-50"
          >
            {submitting ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
