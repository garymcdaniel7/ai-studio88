"use client";

/**
 * ErrorBoundary — Page-level React Error Boundary.
 *
 * Catches rendering errors and displays a recovery UI with:
 * - Heading
 * - Truncated error message (200 chars max)
 * - "Try Again" button that resets the boundary
 * - "Go Home" link for navigation escape
 * - Sidebar/topbar remain navigable (page-content isolation)
 *
 * Validates: Requirements R23.1, R23.2, R23.3, R23.6
 */

import { Component, type ReactNode } from "react";
import { AlertTriangle, RefreshCw, Home } from "lucide-react";

// =============================================================================
// Types
// =============================================================================

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Optional fallback component. If not provided, uses the default error UI. */
  fallback?: ReactNode;
  /** Whether this is the page-level boundary (isolates to page-content, not full screen) */
  pageLevel?: boolean;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

// =============================================================================
// Constants
// =============================================================================

const MAX_MESSAGE_LENGTH = 200;
const IS_DEV = process.env.NODE_ENV === "development";

// =============================================================================
// Error Boundary Class Component
// =============================================================================

/**
 * React Error Boundary that catches rendering errors in the subtree.
 *
 * Designed to wrap page-level content so that the sidebar and topbar
 * remain navigable when an error occurs (R23.6).
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // R23.4: In development, log error + component stack to console
    if (IS_DEV) {
      console.error("[ErrorBoundary] Caught error:", error);
      console.error("[ErrorBoundary] Component stack:", errorInfo.componentStack);
    }

    // R23.5: In production, send error to reporting service
    if (!IS_DEV && typeof window !== "undefined") {
      this.reportError(error, errorInfo);
    }
  }

  /** Report error to external service (within 5 seconds per R23.5) */
  private reportError(error: Error, errorInfo: React.ErrorInfo) {
    try {
      // Dispatch to error reporting — uses global handler from error-logger
      window.dispatchEvent(
        new CustomEvent("app:error:boundary", {
          detail: {
            error: {
              name: error.name,
              message: error.message,
              stack: error.stack,
            },
            componentStack: errorInfo.componentStack,
            timestamp: Date.now(),
          },
        })
      );
    } catch {
      // Silently fail — don't cause more errors in the error handler
    }
  }

  /** Reset boundary state — allows children to re-render (R23.2 "Try Again") */
  private handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  /** Navigate to home page */
  private handleGoHome = () => {
    if (typeof window !== "undefined") {
      window.location.href = "/";
    }
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    // Custom fallback provided
    if (this.props.fallback) {
      return this.props.fallback;
    }

    const errorMessage = this.state.error?.message || "An unexpected error occurred.";
    const truncatedMessage =
      errorMessage.length > MAX_MESSAGE_LENGTH
        ? `${errorMessage.slice(0, MAX_MESSAGE_LENGTH)}...`
        : errorMessage;

    // Page-level boundary: renders within the page content area (R23.6)
    if (this.props.pageLevel) {
      return (
        <div
          className="flex flex-col items-center justify-center py-16 px-4 text-center"
          role="alert"
          aria-live="assertive"
          data-testid="error-boundary-page"
        >
          <div className="max-w-md">
            <div className="flex justify-center mb-4">
              <div className="h-14 w-14 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center">
                <AlertTriangle className="h-7 w-7 text-red-400" />
              </div>
            </div>
            <h2 className="text-lg font-bold text-white mb-2">Something went wrong</h2>
            <p className="text-sm text-gray-400 mb-4 break-words">
              {truncatedMessage}
            </p>
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={this.handleReset}
                className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500"
                aria-label="Try again"
              >
                <RefreshCw className="h-4 w-4" />
                Try Again
              </button>
              <button
                onClick={this.handleGoHome}
                className="inline-flex items-center gap-2 rounded-lg border border-white/[0.08] px-4 py-2 text-sm text-gray-300 hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500"
                aria-label="Go to home page"
              >
                <Home className="h-4 w-4" />
                Go Home
              </button>
            </div>
          </div>
        </div>
      );
    }

    // App-level boundary: full screen (wraps entire app including sidebar)
    return (
      <div
        className="min-h-screen bg-[#0a0a1a] flex items-center justify-center px-4"
        role="alert"
        aria-live="assertive"
        data-testid="error-boundary-app"
      >
        <div className="max-w-md text-center">
          <div className="flex justify-center mb-4">
            <div className="h-16 w-16 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center">
              <AlertTriangle className="h-8 w-8 text-red-400" />
            </div>
          </div>
          <h1 className="text-xl font-bold text-white mb-2">Something went wrong</h1>
          <p className="text-sm text-gray-400 mb-4 break-words">
            {truncatedMessage}
          </p>
          <div className="flex items-center justify-center gap-3">
            <button
              onClick={this.handleReset}
              className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-purple-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500"
              aria-label="Try again"
            >
              <RefreshCw className="h-4 w-4" />
              Try Again
            </button>
            <button
              onClick={this.handleGoHome}
              className="inline-flex items-center gap-2 rounded-lg border border-white/[0.08] px-5 py-2.5 text-sm text-gray-300 hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500"
              aria-label="Go to home page"
            >
              <Home className="h-4 w-4" />
              Go Home
            </button>
          </div>
          <p className="mt-6 text-[10px] text-gray-600">
            If this keeps happening, check the browser console or contact support.
          </p>
        </div>
      </div>
    );
  }
}
