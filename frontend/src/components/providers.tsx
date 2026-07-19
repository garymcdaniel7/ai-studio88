"use client";

import { useEffect } from "react";
import { ToastProvider } from "@/components/toast";
import { ErrorBoundary } from "@/components/error-boundary";
import { initGlobalErrorHandler } from "@/lib/error-logger";

export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    initGlobalErrorHandler();
  }, []);

  return (
    <ErrorBoundary>
      <ToastProvider>{children}</ToastProvider>
    </ErrorBoundary>
  );
}
