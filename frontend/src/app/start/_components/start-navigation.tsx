import type { LucideIcon } from "lucide-react";
import { Check, ChevronDown, ChevronLeft, ChevronRight, Circle } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

export type StartStepKey = "start" | "cast" | "write" | "make" | "publish";
export type StartStepState = "active" | "completed" | "future";

export interface StartNavStep {
  key: StartStepKey;
  label: string;
  href: string;
  icon: LucideIcon;
}

export const START_NAV_STEPS: readonly StartNavStep[] = [
  { key: "start", label: "START", href: "/start", icon: Circle },
  { key: "cast", label: "CAST", href: "/cast", icon: Circle },
  { key: "write", label: "WRITE", href: "/write", icon: Circle },
  { key: "make", label: "MAKE", href: "/make", icon: Circle },
  { key: "publish", label: "PUBLISH", href: "/publish", icon: Circle },
];

/** Breakpoint contract for the Phase 1 five-step navigation. */
export const START_NAV_BREAKPOINTS = {
  mobileMax: 767,
  tabletMin: 768,
  tabletMax: 1023,
  desktopMin: 1024,
} as const;

export function getCurrentStartStep(pathname: string): StartStepKey {
  const matchingStep = START_NAV_STEPS.find(
    (step) => pathname === step.href || pathname.startsWith(`${step.href}/`),
  );
  return matchingStep?.key ?? "start";
}

export function getStartStepState(
  step: StartStepKey,
  current: StartStepKey,
): StartStepState {
  const stepIndex = START_NAV_STEPS.findIndex((item) => item.key === step);
  const currentIndex = START_NAV_STEPS.findIndex((item) => item.key === current);

  if (stepIndex === currentIndex) return "active";
  return stepIndex < currentIndex ? "completed" : "future";
}

function stepClasses(state: StartStepState): string {
  if (state === "active") {
    return "border-purple-400/50 bg-purple-500/15 text-white";
  }
  if (state === "completed") {
    return "border-emerald-400/30 bg-emerald-500/10 text-emerald-200";
  }
  return "border-white/[0.08] bg-white/[0.02] text-gray-500";
}

function StepMark({ state }: { state: StartStepState }) {
  if (state === "completed") {
    return <Check aria-hidden="true" className="h-3.5 w-3.5" />;
  }
  return <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />;
}

function StepLink({ step, current }: { step: StartNavStep; current: StartStepKey }) {
  const state = getStartStepState(step.key, current);
  return (
    <Link
      aria-current={state === "active" ? "step" : undefined}
      className={`flex shrink-0 items-center gap-2 rounded-lg border px-4 py-2 text-xs font-semibold tracking-[0.16em] transition-colors hover:border-purple-400/40 hover:text-white ${stepClasses(state)}`}
      data-step-state={state}
      href={step.href}
    >
      <StepMark state={state} />
      {step.label}
    </Link>
  );
}

/**
 * Lane-owned navigation adapter. The integration lane can lift this into the
 * shared AppShell without changing the route contract or step-state logic.
 */
export function StartStepNavigation() {
  const pathname = usePathname();
  const current = getCurrentStartStep(pathname);
  const currentStep = START_NAV_STEPS.find((step) => step.key === current) ?? START_NAV_STEPS[0];
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <nav aria-label="Production steps" className="mb-8" data-navigation="phase-1-steps">
      <div className="hidden items-center gap-2 lg:flex" data-viewport="desktop">
        {START_NAV_STEPS.map((step) => (
          <StepLink current={current} key={step.key} step={step} />
        ))}
      </div>

      <div className="hidden items-center gap-2 md:flex lg:hidden" data-viewport="tablet">
        <button
          aria-label="Scroll steps left"
          className="rounded-md border border-white/[0.08] p-2 text-gray-400 hover:text-white"
          onClick={() => document.getElementById("phase-1-step-tabs")?.scrollBy({ left: -180, behavior: "smooth" })}
          type="button"
        >
          <ChevronLeft aria-hidden="true" className="h-4 w-4" />
        </button>
        <div className="flex min-w-0 gap-2 overflow-x-auto py-1" id="phase-1-step-tabs">
          {START_NAV_STEPS.map((step) => (
            <StepLink current={current} key={step.key} step={step} />
          ))}
        </div>
        <button
          aria-label="Scroll steps right"
          className="rounded-md border border-white/[0.08] p-2 text-gray-400 hover:text-white"
          onClick={() => document.getElementById("phase-1-step-tabs")?.scrollBy({ left: 180, behavior: "smooth" })}
          type="button"
        >
          <ChevronRight aria-hidden="true" className="h-4 w-4" />
        </button>
      </div>

      <div className="relative md:hidden" data-viewport="mobile">
        <button
          aria-expanded={mobileOpen}
          aria-haspopup="menu"
          className="flex w-full items-center justify-between rounded-lg border border-white/[0.1] bg-white/[0.03] px-4 py-3 text-left text-sm font-semibold tracking-[0.14em] text-white"
          onClick={() => setMobileOpen((open) => !open)}
          type="button"
        >
          <span>Steps: {currentStep.label}</span>
          <ChevronDown aria-hidden="true" className={`h-4 w-4 transition-transform ${mobileOpen ? "rotate-180" : ""}`} />
        </button>
        {mobileOpen && (
          <div className="absolute left-0 right-0 top-full z-20 mt-2 space-y-1 rounded-lg border border-white/[0.1] bg-[#12122a] p-2 shadow-xl" role="menu">
            {START_NAV_STEPS.map((step) => (
              <div key={step.key} onClick={() => setMobileOpen(false)} role="none">
                <StepLink current={current} step={step} />
              </div>
            ))}
          </div>
        )}
      </div>
    </nav>
  );
}
