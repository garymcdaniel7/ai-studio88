/**
 * Output directory card with inline edit mode.
 * Persistence (PUT + toasts) is owned by the page via `onSave`.
 */
export function OutputDirectoryCard({
  outputDir,
  editing,
  onEditingChange,
  onDirChange,
  onSave,
}: {
  outputDir: string;
  editing: boolean;
  onEditingChange: (editing: boolean) => void;
  onDirChange: (dir: string) => void;
  onSave: () => void;
}) {
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-raised p-5">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-content-primary">Output Directory</h3>
        <button
          onClick={() => onEditingChange(!editing)}
          className="text-[10px] text-status-info hover:text-purple-300"
        >
          {editing ? "Done" : "Change"}
        </button>
      </div>
      <p className="text-xs text-content-muted mb-2">Generated images auto-save here</p>
      {editing ? (
        <div className="flex gap-2">
          <input
            type="text"
            value={outputDir}
            onChange={(e) => onDirChange(e.target.value)}
            className="flex-1 rounded-lg border border-border-default bg-surface-hover px-3 py-1.5 text-xs text-white font-mono focus:border-purple-500 focus:outline-none"
          />
          <button
            onClick={onSave}
            className="rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-700"
          >
            Save
          </button>
        </div>
      ) : (
        <p className="text-xs text-content-secondary font-mono bg-surface-hover rounded-lg px-3 py-2 truncate">
          {outputDir}
        </p>
      )}
    </div>
  );
}
