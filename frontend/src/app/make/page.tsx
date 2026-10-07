"use client";

import { useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Sparkles } from "lucide-react";
import { PromptWorkshop } from "@/app/create/_components/prompt-workshop";
import { useCreateData } from "@/app/create/_hooks/use-create-data";

/**
 * Canonical MAKE generation studio.
 *
 * The PromptWorkshop remains page-local to the creation lane while this route
 * provides the stable destination for new generation links and migrated URLs.
 *
 * Supports ?model=h3-video query param for deep-linking from Title Sequence
 * and other planning pages.
 */
function MakeContent() {
  const searchParams = useSearchParams();
  const modelParam = searchParams.get("model") || "flux2-klein";
  const [selectedModel, setSelectedModel] = useState(modelParam);
  const data = useCreateData({ selectedModel, setSelectedModel });

  return (
    <div className="space-y-6">
      <header className="flex items-start gap-3">
        <Sparkles className="mt-1 h-5 w-5 text-purple-300" aria-hidden="true" />
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-purple-300">MAKE</p>
          <h1 className="mt-1 text-2xl font-semibold text-content-primary">Generation studio</h1>
          <p className="mt-1 max-w-2xl text-sm text-content-muted">
            Build a production-ready prompt, inspect every generation tier, and send cost-gated work to the async queue.
          </p>
        </div>
      </header>
      <PromptWorkshop modelOptions={data.imageModelList.map((model) => ({ id: model.id, name: model.name }))} />
    </div>
  );
}

export default function MakePage() {
  return (
    <Suspense fallback={null}>
      <MakeContent />
    </Suspense>
  );
}
