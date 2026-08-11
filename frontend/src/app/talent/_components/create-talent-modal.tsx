"use client";

import { useState } from "react";

interface CreateTalentModalProps {
  open: boolean;
  onClose: () => void;
  onCreate: (name: string, bio: string) => Promise<boolean>;
}

/**
 * Modal for creating a new talent entity.
 */
export function CreateTalentModal({ open, onClose, onCreate }: CreateTalentModalProps) {
  const [name, setName] = useState("");
  const [bio, setBio] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  async function handleSubmit() {
    if (!name.trim()) return;
    setSubmitting(true);
    const success = await onCreate(name.trim(), bio.trim());
    setSubmitting(false);
    if (success) {
      setName("");
      setBio("");
      onClose();
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-white/[0.08] bg-[#0f0f24] p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-bold text-white mb-4">Create New Talent</h2>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-400 block mb-1">Name *</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Character name..."
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none focus:border-purple-500/50"
              autoFocus
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Bio / Description</label>
            <textarea
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              placeholder="Describe this talent..."
              rows={3}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none resize-none focus:border-purple-500/50"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="px-4 py-2 text-xs text-gray-400 hover:text-white">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!name.trim() || submitting}
            className="px-4 py-2 rounded-lg bg-purple-600 text-xs font-medium text-white hover:bg-purple-700 disabled:opacity-50"
          >
            {submitting ? "Creating..." : "Create Talent"}
          </button>
        </div>
      </div>
    </div>
  );
}
