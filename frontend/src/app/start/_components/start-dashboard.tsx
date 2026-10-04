"use client";

import { FolderOpen, Plus, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { StartStepNavigation } from "./start-navigation";
import {
  formatProjectDate,
  getStartViewState,
  normalizeStartProjects,
  toStartRequestError,
  type StartProjectSummary,
  type StartProjectsResponse,
  type StartRequestError,
} from "./start-state";

function StartLoadingSkeleton() {
  return (
    <div aria-label="Loading project dashboard" className="space-y-6" data-testid="start-loading-skeleton">
      <div className="h-8 w-56 animate-pulse rounded bg-white/[0.08]" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {["projects", "assets", "generations"].map((label) => (
          <div className="h-24 animate-pulse rounded-xl border border-white/[0.06] bg-white/[0.03]" key={label} />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {["project-a", "project-b"].map((label) => (
          <div className="h-40 animate-pulse rounded-xl border border-white/[0.06] bg-white/[0.03]" key={label} />
        ))}
      </div>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
      <p className="text-xs uppercase tracking-[0.14em] text-gray-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
    </div>
  );
}

function StartError({ error, onRetry }: { error: StartRequestError; onRetry: () => void }) {
  return (
    <section aria-live="polite" className="rounded-xl border border-red-400/20 bg-red-500/[0.06] p-6" data-testid="start-error-state">
      <p className="text-sm font-semibold text-red-200">{error.message}</p>
      <p className="mt-2 text-sm text-gray-400">{error.detail}</p>
      <dl className="mt-4 grid gap-1 text-xs text-gray-500 sm:grid-cols-2">
        <div>
          <dt className="inline">Error code: </dt>
          <dd className="inline font-mono text-gray-300">{error.code}</dd>
        </div>
        <div>
          <dt className="inline">X-Request-ID: </dt>
          <dd className="inline font-mono text-gray-300">{error.requestId}</dd>
        </div>
      </dl>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        {error.retryable && (
          <button
            className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700"
            onClick={onRetry}
            type="button"
          >
            <RefreshCw aria-hidden="true" className="h-4 w-4" />
            Retry
          </button>
        )}
        <Link className="text-sm text-gray-400 underline underline-offset-4 hover:text-white" href="/login">
          Contact support or sign in again
        </Link>
      </div>
    </section>
  );
}

function StartEmptyState() {
  return (
    <section className="rounded-xl border border-dashed border-white/[0.12] bg-[#12122a] p-10 text-center" data-testid="start-empty-state">
      <FolderOpen aria-hidden="true" className="mx-auto h-10 w-10 text-gray-600" />
      <h2 className="mt-4 text-lg font-semibold text-white">Create your first project</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-gray-500">
        Projects keep your cast, story, generations, and published work organized in one place.
      </p>
      <Link className="mt-6 inline-flex items-center gap-2 rounded-lg bg-purple-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-purple-700" href="/projects">
        <Plus aria-hidden="true" className="h-4 w-4" />
        Create your first project
      </Link>
    </section>
  );
}

export function StartDashboard() {
  const [projects, setProjects] = useState<StartProjectSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<StartRequestError | null>(null);

  const loadProjects = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.get<StartProjectsResponse | StartProjectSummary[]>("/api/v1/projects");
      setProjects(normalizeStartProjects(response));
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.code === "UNAUTHORIZED") return;
      setError(toStartRequestError(requestError));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => {
      void loadProjects();
    }, 0);
    return () => window.clearTimeout(initialLoad);
  }, [loadProjects]);

  const activeProjects = useMemo(
    () => projects.filter((project) => project.status === "active"),
    [projects],
  );
  const totalAssets = activeProjects.reduce((sum, project) => sum + (project.asset_count ?? 0), 0);
  const totalGenerations = activeProjects.reduce((sum, project) => sum + (project.generation_count ?? 0), 0);
  const viewState = getStartViewState({ error, isLoading, projects });

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6" data-testid="start-dashboard">
      <StartStepNavigation />
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-purple-400">START</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Your creative workspace</h1>
          <p className="mt-2 text-sm text-gray-500">Open a project or create a new one to begin.</p>
        </div>
        <Link className="inline-flex items-center justify-center gap-2 rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-purple-700" href="/projects">
          <Plus aria-hidden="true" className="h-4 w-4" />
          New project
        </Link>
      </header>

      {viewState === "loading" && <StartLoadingSkeleton />}
      {viewState === "error" && error && <StartError error={error} onRetry={() => void loadProjects()} />}

      {viewState !== "loading" && viewState !== "error" && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3" data-testid="start-summary">
            <SummaryCard label="Active projects" value={activeProjects.length} />
            <SummaryCard label="Assets" value={totalAssets} />
            <SummaryCard label="Generations" value={totalGenerations} />
          </div>

          {viewState === "empty" ? (
            <StartEmptyState />
          ) : (
            <section aria-label="Active projects" className="grid grid-cols-1 gap-4 md:grid-cols-2" data-testid="start-projects">
              {activeProjects.map((project) => (
                <Link
                  className="group rounded-xl border border-white/[0.06] bg-[#12122a] p-5 transition-colors hover:border-purple-400/40"
                  href={`/projects/${project.id}`}
                  key={project.id}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <p className="truncate text-base font-semibold text-white">{project.name}</p>
                      <p className="mt-1 truncate text-sm text-gray-500">{project.description || project.category || "Creative project"}</p>
                    </div>
                    <span className="rounded-full bg-emerald-500/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-emerald-300">{project.status}</span>
                  </div>
                  <div className="mt-6 flex items-center justify-between border-t border-white/[0.06] pt-3 text-xs text-gray-500">
                    <span>{project.asset_count ?? 0} assets · {project.generation_count ?? 0} generations</span>
                    <span>{formatProjectDate(project.created_at)}</span>
                  </div>
                </Link>
              ))}
            </section>
          )}
        </>
      )}
    </div>
  );
}

export { StartLoadingSkeleton };
