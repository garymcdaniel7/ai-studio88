"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth-context";
import { StartDashboard, StartLoadingSkeleton } from "./_components/start-dashboard";

function StartRouteRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace(`/login?redirect=${encodeURIComponent("/start")}`);
  }, [router]);

  return (
    <main aria-live="polite" className="mx-auto flex min-h-[50vh] max-w-xl items-center justify-center text-center">
      <div>
        <p className="text-sm text-gray-400">Your session is required to open START.</p>
        <p className="mt-2 text-xs text-gray-600">Redirecting to sign in…</p>
      </div>
    </main>
  );
}

/** Protected START project dashboard; the public landing page remains at /. */
export default function StartPage() {
  const { status } = useAuth();

  if (status === "loading") return <StartLoadingSkeleton />;
  if (status !== "authenticated") return <StartRouteRedirect />;
  return <StartDashboard />;
}
