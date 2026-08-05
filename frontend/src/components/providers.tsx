"use client";

import { useEffect } from "react";
import { ToastProvider } from "@/components/toast";
import { ErrorBoundary } from "@/components/error-boundary";
import { AuthProvider } from "@/lib/auth-context";
import { initGlobalErrorHandler } from "@/lib/error-logger";

/**
 * Application-wide Providers wrapper.
 *
 * Order matters:
 * 1. ErrorBoundary — catches rendering errors
 * 2. AuthProvider — owns session/workspace state (Story 007)
 * 3. ToastProvider — notifications (may reference auth state in future)
 */
export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    initGlobalErrorHandler();
  }, []);

  return (
    <ErrorBoundary>
      <AuthProvider>
        <ToastProvider>{children}</ToastProvider>
      </AuthProvider>
    </ErrorBoundary>
  );
}
