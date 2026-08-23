"use client";

interface CreateTalentFormProps {
  name: string;
  bio: string;
  onNameChange: (value: string) => void;
  onBioChange: (value: string) => void;
  onCreate: () => void;
  onCancel: () => void;
}

/**
 * Inline "Create New Talent" panel shown at the top of the library.
 */
export function CreateTalentForm({ name, bio, onNameChange, onBioChange, onCreate, onCancel }: CreateTalentFormProps) {
  return (
    <div className="rounded-xl border border-status-info/30 bg-surface-raised p-6">
      <h3 className="text-sm font-semibold text-content-primary mb-4">Create New Talent</h3>
      <div className="space-y-3">
        <input
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder="Name (e.g. Melissa)"
          className="w-full rounded-lg border border-border-default bg-surface-hover px-4 py-2 text-sm text-content-secondary placeholder:text-content-muted outline-none focus:border-purple-500/50"
        />
        <textarea
          value={bio}
          onChange={(e) => onBioChange(e.target.value)}
          placeholder="Bio / description..."
          className="w-full rounded-lg border border-border-default bg-surface-hover px-4 py-2 text-sm text-content-secondary placeholder:text-content-muted outline-none resize-none"
          rows={3}
        />
        <div className="flex gap-2">
          <button
            onClick={onCreate}
            className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700"
          >
            Create
          </button>
          <button
            onClick={onCancel}
            className="rounded-lg border border-border-default px-4 py-2 text-sm text-content-tertiary hover:bg-surface-hover"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
