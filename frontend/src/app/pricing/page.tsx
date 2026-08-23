import type { Metadata } from "next";

import { PricingView } from "./pricing-view";

export const metadata: Metadata = {
  title: "Pricing — AI Studio",
  description:
    "Five tiers from free screen tests to dedicated showrunner capacity. Founding members lock lifetime rate parity. Join the waitlist — payments are not live yet.",
};

export default function PricingPage() {
  return <PricingView />;
}
