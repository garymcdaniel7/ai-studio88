"use client";

import { Component, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * ErrorBoundary — Catches rendering errors and shows a recovery UI.
 *
 * Wraps the entire app in the layout to prevent white screens.
 * Shows the error message + a Retry button.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#0a0a1a] flex items-center justify-center px-4">
          <div className="max-w-md text-center">
            <div className="flex justify-center mb-4">
              <div className="h-16 w-16 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center">
                <AlertTriangle className="h-8 w-8 text-red-400" />
              </div>
            </div>
            <h1 className="text-xl font-bold text-white mb-2">Something went wrong</h1>
            <p className="text-sm text-gray-400 mb-4">
              The app encountered an unexpected error. This is usually temporary.
            </p>
            {this.state.error && (
              <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3 text-left">
                <p className="text-xs text-red-400 font-mono break-all">
                  {this.state.error.message}
                </p>
              </div>
            )}
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
              className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-purple-700"
            >
              <RefreshCw className="h-4 w-4" />
              Reload App
            </button>
            <p className="mt-4 text-[10px] text-gray-600">
              If this keeps happening, check the browser console or contact support.
            </p>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
