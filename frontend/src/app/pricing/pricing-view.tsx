"use client";

import { useEffect, useState } from "react";
import {
  Check,
  Clapperboard,
  Crown,
  Gem,
  Sparkles,
  Star,
  Sun,
} from "lucide-react";

/**
 * Pricing — five tiers, content-lane aware, waitlist-only.
 *
 * Payments are deferred indefinitely: every CTA on this page is a waitlist
 * capture (stored locally until a backend endpoint exists). There are no
 * checkout, buy, or subscribe controls anywhere on this route by design.
 *
 * Each tier carries `contentLane` as data — the compliance lane the tier's
 * output is cleared for — rendered as a subtle badge per card.
 */

type ContentLane = "sfw" | "nsfw" | "both";

type Tier = {
  id: string;
  name: string;
  tagline: string;
  icon: React.ElementType;
  /** Monthly price in USD; null = custom / by application. */
  monthly: number | null;
  priceNote: string;
  credits: string;
  contentLane: ContentLane;
  features: string[];
  highlight?: boolean;
  cta: string;
};

const TIERS: Tier[] = [
  {
    id: "screen_test",
    name: "Screen Test",
    tagline: "Kick the tires. Free.",
    icon: Clapperboard,
    monthly: 0,
    priceNote: "free forever",
    credits: "250 credits / month",
    contentLane: "sfw",
    features: [
      "250 credits every month",
      "Core image models",
      "Watermarked downloads",
      "1 talent persona",
      "Community support",
    ],
    cta: "Join the waitlist",
  },
  {
    id: "day_player",
    name: "Day Player",
    tagline: "For steady side gigs.",
    icon: Sun,
    monthly: 29,
    priceNote: "per month",
    credits: "2,000 credits / month",
    contentLane: "sfw",
    features: [
      "2,000 credits every month",
      "Image + short video generation",
      "3 talent personas",
      "Standard render queue",
      "Email support",
    ],
    cta: "Join the waitlist",
  },
  {
    id: "series_regular",
    name: "Series Regular",
    tagline: "The working creator's tier.",
    icon: Star,
    monthly: 99,
    priceNote: "per month",
    credits: "8,000 credits / month",
    contentLane: "both",
    features: [
      "8,000 credits every month",
      "Watermark-free output",
      "All image & video models",
      "10 talent personas",
      "Publishing tools included",
    ],
    highlight: true,
    cta: "Join the waitlist",
  },
  {
    id: "showrunner",
    name: "Showrunner",
    tagline: "Run full productions.",
    icon: Crown,
    monthly: 249,
    priceNote: "per month",
    credits: "25,000 credits / month",
    contentLane: "both",
    features: [
      "25,000 credits every month",
      "Priority render queue",
      "Continuity suite across scenes",
      "Unlimited talent personas",
      "Early access to new models",
    ],
    cta: "Join the waitlist",
  },
  {
    id: "hefner",
    name: "Hefner",
    tagline: "Studio-grade, by application.",
    icon: Gem,
    monthly: null,
    priceNote: "~$999+/mo · by application",
    credits: "Dedicated capacity",
    contentLane: "nsfw",
    features: [
      "Dedicated GPU capacity",
      "Concierge production support",
      "Private LoRA training",
      "Custom pipelines & SLAs",
      "White-glove onboarding",
    ],
    cta: "Request an invite",
  },
];

/** Annual billing = 2 months free (10x the monthly rate). */
function annualPrice(monthly: number): number {
  return monthly * 10;
}

const LANE_BADGE: Record<ContentLane, { label: string; className: string }> = {
  sfw: {
    label: "SFW",
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  },
  both: {
    label: "SFW · 18+",
    className: "border-purple-500/30 bg-purple-500/10 text-purple-300",
  },
  nsfw: {
    label: "18+",
    className: "border-pink-500/30 bg-pink-500/10 text-pink-400",
  },
};

const WAITLIST_KEY = "ai_studio_pricing_waitlist";

type WaitlistEntry = { tier: string; email: string; at: string };

export function PricingView() {
  const [billing, setBilling] = useState<"monthly" | "annual">("monthly");
  const [openTier, setOpenTier] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [joinedTiers, setJoinedTiers] = useState<string[]>([]);
  const [error, setError] = useState("");

  // Load existing signups after mount (avoids SSR hydration mismatch)
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(WAITLIST_KEY);
      if (!raw) return;
      const parsed: unknown = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && Array.isArray((parsed as { entries?: unknown }).entries)) {
        const tiers = ((parsed as { entries: WaitlistEntry[] }).entries || [])
          .map((e) => e?.tier)
          .filter((t): t is string => typeof t === "string");
        setJoinedTiers(tiers);
      }
    } catch {
      // Corrupt local storage — ignore
    }
  }, []);

  function handleWaitlistSubmit(tierId: string) {
    const value = email.trim();
    if (!value || !value.includes("@") || !value.includes(".")) {
      setError("Enter a valid email address.");
      return;
    }
    try {
      const raw = window.localStorage.getItem(WAITLIST_KEY);
      const parsed: unknown = raw ? JSON.parse(raw) : {};
      const entries: WaitlistEntry[] =
        parsed && typeof parsed === "object" && Array.isArray((parsed as { entries?: unknown }).entries)
          ? ((parsed as { entries: WaitlistEntry[] }).entries)
          : [];
      entries.push({ tier: tierId, email: value, at: new Date().toISOString() });
      window.localStorage.setItem(WAITLIST_KEY, JSON.stringify({ entries }));
    } catch {
      // Storage unavailable — still confirm intent in UI
    }
    setJoinedTiers((prev) => (prev.includes(tierId) ? prev : [...prev, tierId]));
    setOpenTier(null);
    setEmail("");
    setError("");
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Pricing</h1>
          <p className="text-sm text-gray-500">
            Five tiers from free screen tests to dedicated studio capacity. Pick your lane.
          </p>
        </div>

        {/* Billing toggle */}
        <div className="flex items-center gap-3">
          <div className="flex rounded-lg border border-white/[0.08] overflow-hidden">
            <button
              type="button"
              onClick={() => setBilling("monthly")}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                billing === "monthly"
                  ? "bg-purple-600 text-white"
                  : "bg-white/[0.02] text-gray-400 hover:text-gray-200 hover:bg-white/[0.04]"
              }`}
            >
              Monthly
            </button>
            <button
              type="button"
              onClick={() => setBilling("annual")}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                billing === "annual"
                  ? "bg-purple-600 text-white"
                  : "bg-white/[0.02] text-gray-400 hover:text-gray-200 hover:bg-white/[0.04]"
              }`}
            >
              Annual · 2 months free
            </button>
          </div>
        </div>
      </div>

      {/* Founding-member callout */}
      <div className="flex items-start gap-4 rounded-xl border border-purple-500/20 bg-gradient-to-r from-purple-900/10 to-blue-900/10 p-5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-purple-600/20">
          <Sparkles className="h-5 w-5 text-purple-400" />
        </div>
        <div>
          <p className="text-sm font-semibold text-white">Founding members — first 100 only</p>
          <p className="mt-0.5 text-xs text-gray-400 leading-relaxed">
            The first 100 members lock lifetime rate parity: whatever your rate is when you join
            is what you keep forever — it never goes up as prices rise.
          </p>
        </div>
      </div>

      {/* Tier cards */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
        {TIERS.map((tier) => {
          const joined = joinedTiers.includes(tier.id);
          const open = openTier === tier.id;
          const badge = LANE_BADGE[tier.contentLane];
          const Icon = tier.icon;

          return (
            <div
              key={tier.id}
              className={`relative flex flex-col rounded-xl border p-6 ${
                tier.highlight
                  ? "border-purple-500/40 bg-purple-500/5"
                  : "border-white/[0.06] bg-[#12122a]"
              }`}
            >
              {tier.highlight && (
                <span className="absolute -top-3 left-6 rounded-full bg-purple-600 px-3 py-1 text-[10px] font-medium text-white">
                  Most popular
                </span>
              )}

              {/* Lane badge — compliance lane for this tier, as data */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-600/20">
                  <Icon className="h-5 w-5 text-purple-400" />
                </div>
                <span
                  title={`Content lane: ${tier.contentLane}`}
                  className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${badge.className}`}
                >
                  {badge.label}
                </span>
              </div>

              <h3 className="text-base font-semibold text-white">{tier.name}</h3>
              <p className="text-xs text-gray-500">{tier.tagline}</p>

              {/* Price */}
              <div className="mt-4 mb-1">
                {tier.monthly === null ? (
                  <>
                    <span className="text-3xl font-bold text-white">~$999+</span>
                    <span className="ml-1 text-sm text-gray-400">/mo</span>
                    <p className="mt-1 text-xs text-gray-500">By application · annual terms custom</p>
                  </>
                ) : tier.monthly === 0 ? (
                  <>
                    <span className="text-3xl font-bold text-white">$0</span>
                    <span className="ml-1 text-sm text-gray-400">/month</span>
                    <p className="mt-1 text-xs text-gray-500">Free screen test · no card required</p>
                  </>
                ) : billing === "monthly" ? (
                  <>
                    <span className="text-3xl font-bold text-white">${tier.monthly}</span>
                    <span className="ml-1 text-sm text-gray-400">/month</span>
                    <p className="mt-1 text-xs text-gray-500">Billed monthly · switch to annual for 2 months free</p>
                  </>
                ) : (
                  <>
                    <span className="text-3xl font-bold text-white">${annualPrice(tier.monthly)}</span>
                    <span className="ml-1 text-sm text-gray-400">/year</span>
                    <p className="mt-1 text-xs text-green-400">
                      = ${(annualPrice(tier.monthly) / 12).toFixed(2)}/mo · 2 months free
                    </p>
                  </>
                )}
              </div>
              <p className="mb-4 text-xs font-medium text-purple-300">{tier.credits}</p>

              {/* Features */}
              <ul className="mb-6 space-y-2">
                {tier.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2 text-xs text-gray-300">
                    <Check className="h-3.5 w-3.5 shrink-0 text-purple-400 mt-0.5" />
                    {feature}
                  </li>
                ))}
              </ul>

              {/* Waitlist CTA — the only CTA on this page. No checkout anywhere. */}
              <div className="mt-auto">
                {joined ? (
                  <div className="rounded-lg border border-green-500/20 bg-green-500/5 px-3 py-2.5 text-center">
                    <p className="text-xs font-medium text-green-400">You are on the list for {tier.name}.</p>
                  </div>
                ) : open ? (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      handleWaitlistSubmit(tier.id);
                    }}
                    className="space-y-2"
                  >
                    <label htmlFor={`waitlist-email-${tier.id}`} className="sr-only">
                      Email for {tier.name} waitlist
                    </label>
                    <input
                      id={`waitlist-email-${tier.id}`}
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white placeholder:text-gray-600 outline-none focus:border-purple-500/50"
                    />
                    {error && <p className="text-[11px] text-red-400">{error}</p>}
                    <button
                      type="submit"
                      className="block w-full rounded-lg bg-purple-600 py-2.5 text-center text-sm font-medium text-white transition-colors hover:bg-purple-700"
                    >
                      {tier.cta}
                    </button>
                  </form>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      setError("");
                      setOpenTier(tier.id);
                      setEmail("");
                    }}
                    className={`block w-full rounded-lg py-2.5 text-center text-sm font-medium transition-colors ${
                      tier.highlight
                        ? "bg-purple-600 text-white hover:bg-purple-700"
                        : "border border-white/[0.08] bg-white/[0.03] text-gray-200 hover:bg-white/[0.06]"
                    }`}
                  >
                    {tier.cta}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Fine print */}
      <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <p className="text-xs font-semibold text-white">Credits</p>
            <p className="mt-1 text-[11px] leading-relaxed text-gray-500">
              Every tier includes a monthly credit allowance. Generations draw down credits
              by model and output type.
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold text-white">Annual billing</p>
            <p className="mt-1 text-[11px] leading-relaxed text-gray-500">
              Pay for 10 months, get 12. Annual = 2 months free on every paid tier.
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold text-white">Content lanes</p>
            <p className="mt-1 text-[11px] leading-relaxed text-gray-500">
              SFW everywhere. 18+ output unlocks at Series Regular and above; Hefner is the
              dedicated adult-lane production tier.
            </p>
          </div>
        </div>
        <p className="mt-4 border-t border-white/[0.06] pt-3 text-[11px] text-gray-600">
          Payments are not live yet — joining the waitlist is free and commits you to nothing.
          Founding-member rate parity applies to whichever tier you join first.
        </p>
      </div>
    </div>
  );
}
