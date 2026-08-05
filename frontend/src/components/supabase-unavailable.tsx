/**
 * SupabaseUnavailable — Displayed when Supabase auth is not configured.
 *
 * Provides a clear, non-crashing UI state instead of a broken page.
 * Used by pages that require authentication when the Supabase client
 * cannot be initialized (missing env vars, build-time rendering, etc.).
 */

"use client";

import { AlertTriangle } from "lucide-react";

interface SupabaseUnavailableProps {
  /** What the user was trying to do (e.g., "sign in", "access your account") */
  action?: string;
  /** Whether to show dev-mode instructions */
  showDevHint?: boolean;
}

export function SupabaseUnavailable({
  action = "authenticate",
  showDevHint = process.env.NODE_ENV === "development",
}: SupabaseUnavailableProps) {
  return (
    <div className="flex min-h-[400px] items-center justify-center p-8">
      <div className="w-full max-w-md rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-6 text-center">
        <AlertTriangle className="mx-auto h-10 w-10 text-yellow-500 mb-4" />
        <h2 className="text-lg font-semibold text-white mb-2">
          Authentication Unavailable
        </h2>
        <p className="text-sm text-gray-400 mb-4">
          Unable to {action}. The authentication service is not configured for
          this environment.
        </p>
        {showDevHint && (
          <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-3 text-left">
            <p className="text-xs font-medium text-gray-300 mb-1">
              Developer Setup
            </p>
            <p className="text-xs text-gray-500">
              Set <code className="text-purple-400">NEXT_PUBLIC_SUPABASE_URL</code>{" "}
              and{" "}
              <code className="text-purple-400">NEXT_PUBLIC_SUPABASE_ANON_KEY</code>{" "}
              in <code className="text-purple-400">frontend/.env.local</code> to
              enable authentication.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
