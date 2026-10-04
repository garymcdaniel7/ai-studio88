import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "API — AI Studio",
  description: "AI Studio API information and backend service links.",
};

function configuredUrl(variable: string, fallbackPath: string): string | null {
  const value = process.env[variable]?.trim().replace(/\/$/, "");
  if (value) return value;
  const apiBase = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "");
  return apiBase ? `${apiBase}${fallbackPath}` : null;
}

export default function ApiLandingPage() {
  const docsUrl = configuredUrl("NEXT_PUBLIC_API_DOCS_URL", "/docs");
  const healthUrl = configuredUrl("NEXT_PUBLIC_API_HEALTH_URL", "/api/v1/health");

  return (
    <main className="min-h-screen bg-[#090918] px-5 py-16 text-white sm:px-8">
      <div className="mx-auto max-w-2xl rounded-3xl border border-white/[0.08] bg-white/[0.035] p-8 shadow-2xl shadow-black/20 sm:p-12">
        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-purple-300">AI Studio API</p>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">The API is served by the Railway backend.</h1>
        <p className="mt-5 text-base leading-7 text-white/60">This frontend route is an orientation page, not a proxy. API credentials stay on the backend and are never exposed here.</p>

        <div className="mt-8 grid gap-3 sm:grid-cols-2">
          {docsUrl ? (
            <a href={docsUrl} target="_blank" rel="noreferrer" className="rounded-xl border border-purple-400/30 bg-purple-500/10 p-4 transition hover:bg-purple-500/20">
              <span className="block text-sm font-medium text-purple-100">API documentation</span>
              <span className="mt-1 block break-all text-xs text-purple-200/60">{docsUrl}</span>
            </a>
          ) : (
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <span className="block text-sm font-medium text-white/80">API documentation</span>
              <span className="mt-1 block text-xs text-white/45">Configure NEXT_PUBLIC_API_URL or NEXT_PUBLIC_API_DOCS_URL.</span>
            </div>
          )}
          {healthUrl ? (
            <a href={healthUrl} target="_blank" rel="noreferrer" className="rounded-xl border border-white/10 bg-white/[0.03] p-4 transition hover:border-white/25">
              <span className="block text-sm font-medium text-white/80">Backend health</span>
              <span className="mt-1 block break-all text-xs text-white/45">{healthUrl}</span>
            </a>
          ) : (
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <span className="block text-sm font-medium text-white/80">Backend health</span>
              <span className="mt-1 block text-xs text-white/45">Configure NEXT_PUBLIC_API_URL or NEXT_PUBLIC_API_HEALTH_URL.</span>
            </div>
          )}
        </div>

        <Link href="/" className="mt-10 inline-flex text-sm text-purple-300 transition hover:text-purple-200">← Back to AI Studio</Link>
      </div>
    </main>
  );
}
