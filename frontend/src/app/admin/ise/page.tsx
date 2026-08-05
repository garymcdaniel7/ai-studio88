"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * /admin/ise now redirects to /admin/health.
 * The Ise governance features (stuck jobs, budget alerts, AI decisions)
 * have been merged into the Health dashboard page.
 */
export default function IsePage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/admin/health");
  }, [router]);

  return (
    <div className="flex items-center justify-center h-64">
      <p className="text-sm text-gray-400">Redirecting to Health Dashboard...</p>
    </div>
  );
}
