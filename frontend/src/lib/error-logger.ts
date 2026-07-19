/**
 * Error Logger — Captures and reports errors across the frontend.
 *
 * Records: timestamp, component/button, what happened, what was expected.
 * Stores locally and sends to backend for Ise to analyze.
 *
 * Usage:
 *   import { logError, logInteraction, getErrorLog } from "@/lib/error-logger";
 *   logError("Generate button", "Network error: timeout", "Expected image result");
 *   logInteraction("Launch Worker", "clicked", { page: "/admin" });
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

export interface ErrorEntry {
  id: string;
  timestamp: string;
  page: string;
  component: string;
  action: string;
  error: string;
  expected: string;
  stack?: string;
  metadata?: Record<string, unknown>;
}

export interface InteractionEntry {
  id: string;
  timestamp: string;
  page: string;
  component: string;
  action: string;
  result: "success" | "error" | "pending";
  duration_ms?: number;
  metadata?: Record<string, unknown>;
}

// In-memory log (survives page navigation but not refresh)
const errorLog: ErrorEntry[] = [];
const interactionLog: InteractionEntry[] = [];
const MAX_LOG_SIZE = 100;

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function getCurrentPage(): string {
  if (typeof window === "undefined") return "server";
  return window.location.pathname;
}

/**
 * Log an error that occurred during user interaction.
 */
export function logError(
  component: string,
  error: string,
  expected: string,
  metadata?: Record<string, unknown>
): void {
  const entry: ErrorEntry = {
    id: generateId(),
    timestamp: new Date().toISOString(),
    page: getCurrentPage(),
    component,
    action: "error",
    error: error.slice(0, 500),
    expected,
    stack: new Error().stack?.split("\n").slice(2, 5).join("\n"),
    metadata,
  };

  errorLog.push(entry);
  if (errorLog.length > MAX_LOG_SIZE) errorLog.shift();

  // Console log for development
  console.error(`[ErrorLogger] ${component}: ${error}`, entry);

  // Send to backend (fire-and-forget)
  sendToBackend(entry);
}

/**
 * Log a user interaction (button click, form submit, etc.)
 * Use this to track what users DO — helps with debugging and UX analysis.
 */
export function logInteraction(
  component: string,
  action: string,
  metadata?: Record<string, unknown>
): InteractionEntry {
  const entry: InteractionEntry = {
    id: generateId(),
    timestamp: new Date().toISOString(),
    page: getCurrentPage(),
    component,
    action,
    result: "pending",
    metadata,
  };

  interactionLog.push(entry);
  if (interactionLog.length > MAX_LOG_SIZE) interactionLog.shift();

  return entry;
}

/**
 * Mark an interaction as complete (success or error).
 */
export function completeInteraction(
  entry: InteractionEntry,
  result: "success" | "error",
  error?: string
): void {
  entry.result = result;
  entry.duration_ms = Date.now() - new Date(entry.timestamp).getTime();

  if (result === "error" && error) {
    logError(entry.component, error, `Expected ${entry.action} to succeed`, entry.metadata);
  }
}

/**
 * Get all logged errors (for display in Ise dashboard or debug panel).
 */
export function getErrorLog(): ErrorEntry[] {
  return [...errorLog];
}

/**
 * Get all logged interactions.
 */
export function getInteractionLog(): InteractionEntry[] {
  return [...interactionLog];
}

/**
 * Get error summary (for topbar badge).
 */
export function getErrorCount(): number {
  // Count errors from the last hour
  const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
  return errorLog.filter((e) => e.timestamp > oneHourAgo).length;
}

/**
 * Send error to backend for Ise to process.
 */
async function sendToBackend(entry: ErrorEntry): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/v1/errors/log`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(entry),
    });
  } catch {
    // Silent fail — don't create error loops
  }
}

/**
 * Global error handler — catches unhandled errors and promise rejections.
 * Call once in your root layout or providers component.
 */
export function initGlobalErrorHandler(): void {
  if (typeof window === "undefined") return;

  // Unhandled errors
  window.addEventListener("error", (event) => {
    logError(
      "Global",
      event.message || "Unknown error",
      "No error expected",
      {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
      }
    );
  });

  // Unhandled promise rejections
  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason instanceof Error
      ? event.reason.message
      : String(event.reason);
    logError(
      "Global (Promise)",
      reason,
      "Promise should have resolved",
      { type: "unhandledrejection" }
    );
  });
}
