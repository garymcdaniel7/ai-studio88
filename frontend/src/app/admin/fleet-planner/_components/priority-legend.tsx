import { Lightbulb } from "lucide-react";

const TIERS = [
  {
    id: "P0",
    name: "P0 — Instant",
    desc: "Images · Voice · Music",
    classes: "border-green-500/25 bg-green-500/10 text-green-300",
  },
  {
    id: "P1",
    name: "P1 — Video",
    desc: "Scheduled video renders",
    classes: "border-purple-500/25 bg-purple-500/10 text-purple-300",
  },
  {
    id: "P2",
    name: "P2 — Batch",
    desc: "Batch · Assembly jobs",
    classes: "border-amber-500/25 bg-amber-500/10 text-amber-300",
  },
];

/** Priority tier legend for the demand planner. */
export function PriorityLegend() {
  return (
    <div className="flex flex-col gap-2">
      {TIERS.map((tier) => (
        <div
          key={tier.id}
          className={`flex items-center gap-3 rounded-lg border px-3 py-2 ${tier.classes}`}
        >
          <span className="rounded bg-black/30 px-1.5 py-0.5 text-[10px] font-bold tracking-wide">
            {tier.id}
          </span>
          <div>
            <p className="text-xs font-semibold">{tier.name}</p>
            <p className="text-[10px] opacity-70">{tier.desc}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

/** Rule-of-thumb callout for the demand planner. */
export function RuleOfThumb() {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-amber-500/25 bg-amber-500/10 p-4">
      <Lightbulb className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" />
      <div>
        <p className="text-xs font-semibold text-amber-200">Rule of thumb</p>
        <p className="mt-0.5 text-sm text-amber-100/90">
          Queue speed is nearly free at 4-6x markup; idle is the silent killer.
        </p>
      </div>
    </div>
  );
}
