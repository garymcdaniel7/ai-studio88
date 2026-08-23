"use client";

import type { TalentOption } from "../_hooks/use-create-data";

interface TalentSelectorProps {
  apiBase: string;
  talentList: TalentOption[];
  selectedTalents: string[];
  onChange: (next: string[]) => void;
}

/**
 * "Inject Talent DNA" selector — active talent chips + add dropdown.
 * Shared by the image advanced panel and the video tab.
 */
export function TalentSelector({ apiBase, talentList, selectedTalents, onChange }: TalentSelectorProps) {
  if (talentList.length === 0) return null;
  return (
    <div className="space-y-2">
      <label className="block text-[10px] text-content-muted">Inject Talent DNA</label>
      {selectedTalents.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {selectedTalents.map(id => {
            const t = talentList.find(x => x.id === id);
            return t ? (
              <div key={id} className="flex items-center gap-1.5 rounded-full bg-interactive-muted border border-status-info/30 px-2.5 py-1">
                {t.avatar_url && <img src={`${apiBase}${t.avatar_url}`} className="h-4 w-4 rounded-full object-cover" alt="" />}
                <span className="text-[10px] text-purple-300">{t.name}</span>
                <button onClick={() => onChange(selectedTalents.filter(x => x !== id))} className="text-purple-400 hover:text-status-error text-xs ml-0.5">×</button>
              </div>
            ) : null;
          })}
        </div>
      )}
      <select
        value=""
        onChange={(e) => { if (e.target.value && !selectedTalents.includes(e.target.value)) onChange([...selectedTalents, e.target.value]); }}
        className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-xs text-content-secondary outline-none"
      >
        <option value="">+ Add talent to generation...</option>
        {talentList.filter(t => !selectedTalents.includes(t.id)).map(t => (
          <option key={t.id} value={t.id}>{t.name} {t.trigger_words ? `(${t.trigger_words})` : ""}</option>
        ))}
      </select>
    </div>
  );
}
