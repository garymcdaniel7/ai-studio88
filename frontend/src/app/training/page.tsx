"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

import { useState, useEffect } from "react";
import { Upload, Play, Clock, CheckCircle2, XCircle, Loader2 } from "lucide-react";

interface TrainingJob {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  base_model: string;
  steps: number;
  rank: number;
  trigger_word: string;
  created_at: string;
  progress?: number;
}

export default function TrainingPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [baseModel, setBaseModel] = useState("flux-dev");
  const [steps, setSteps] = useState(1000);
  const [rank, setRank] = useState(16);
  const [triggerWord, setTriggerWord] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [optimizer, setOptimizer] = useState("adamw_bf16");
  const [scheduler, setScheduler] = useState("polynomial");
  const [resolution, setResolution] = useState(1024);
  const [batchSize, setBatchSize] = useState(1);
  const [learningRate, setLearningRate] = useState("1e-4");
  const [captionMethod, setCaptionMethod] = useState("filename");
  const [provider, setProvider] = useState("simpletuner");

  const fetchJobs = async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/training/jobs`);
      if (resp.ok) {
        const data = await resp.json();
        setJobs(Array.isArray(data) ? data : data.jobs || []);
      }
    } catch {
      // backend not available
    }
  };

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const resp = await fetch(`${API_BASE}/api/v1/training/jobs`);
        if (!active) return;
        if (resp.ok) {
          const data = await resp.json();
          setJobs(Array.isArray(data) ? data : data.jobs || []);
        }
      } catch {
        // backend not available
      }
    })();
    return () => { active = false; };
  }, []);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const dropped = Array.from(e.dataTransfer.files).filter((f) =>
      f.type.startsWith("image/")
    );
    setFiles((prev) => [...prev, ...dropped]);
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    if (!e.target.files) return;
    const selected = Array.from(e.target.files).filter((f) =>
      f.type.startsWith("image/")
    );
    setFiles((prev) => [...prev, ...selected]);
  }

  async function handleStartTraining() {
    if (files.length === 0 || !triggerWord.trim()) return;
    setSubmitting(true);

    try {
      const formData = new FormData();
      files.forEach((f) => formData.append("images", f));
      formData.append("base_model", baseModel);
      formData.append("steps", String(steps));
      formData.append("rank", String(rank));
      formData.append("trigger_word", triggerWord);
      formData.append("provider", provider);
      formData.append("optimizer", optimizer);
      formData.append("scheduler", scheduler);
      formData.append("resolution", String(resolution));
      formData.append("batch_size", String(batchSize));
      formData.append("learning_rate", learningRate);
      formData.append("caption_method", captionMethod);

      const resp = await fetch(`${API_BASE}/api/v1/training/jobs`, {
        method: "POST",
        body: formData,
      });
      if (resp.ok) {
        setFiles([]);
        setTriggerWord("");
        await fetchJobs();
      } else {
        const err = await resp.json().catch(() => ({}));
        alert(err.detail || "Failed to start training job");
      }
    } catch {
      alert("Cannot reach backend. Is the training service running?");
    } finally {
      setSubmitting(false);
    }
  }

  function statusIcon(status: TrainingJob["status"]) {
    switch (status) {
      case "queued":
        return <Clock className="h-4 w-4 text-yellow-400" />;
      case "running":
        return <Loader2 className="h-4 w-4 text-blue-400 animate-spin" />;
      case "completed":
        return <CheckCircle2 className="h-4 w-4 text-green-400" />;
      case "failed":
        return <XCircle className="h-4 w-4 text-red-400" />;
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Training</h1>
        <p className="text-sm text-gray-500">Fine-tune LoRA models on your own images.</p>
      </div>

      {/* Upload + Configuration */}
      <div className="grid grid-cols-2 gap-6">
        {/* Upload Area */}
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
          <h3 className="text-sm font-semibold text-white mb-3">Training Images</h3>
          <div
            onDrop={handleDrop}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            className={`rounded-lg border-2 border-dashed p-8 text-center cursor-pointer transition-colors ${
              dragOver
                ? "border-purple-500 bg-purple-600/10"
                : "border-white/[0.1] bg-white/[0.02] hover:border-purple-500/30"
            }`}
            onClick={() => document.getElementById("training-file-input")?.click()}
          >
            <Upload className="h-10 w-10 text-gray-600 mx-auto mb-3" />
            <p className="text-sm text-gray-400">Drop images here or click to browse</p>
            <p className="text-xs text-gray-600 mt-1">PNG, JPG — 10-50 images recommended</p>
            <input
              id="training-file-input"
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={handleFileInput}
            />
          </div>
          {files.length > 0 && (
            <div className="mt-3">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-gray-400">{files.length} image{files.length !== 1 ? "s" : ""} selected</p>
                <button
                  onClick={() => setFiles([])}
                  className="text-[10px] text-red-400 hover:text-red-300"
                >
                  Clear all
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {files.map((f, i) => (
                  <div key={i} className="relative w-14 h-14 group">
                    <div className="w-14 h-14 rounded bg-white/[0.05] border border-white/[0.08] overflow-hidden">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={URL.createObjectURL(f)}
                        alt={f.name}
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <button
                      onClick={() => setFiles((prev) => prev.filter((_, idx) => idx !== i))}
                      className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-red-500 text-white text-[8px] flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Configuration */}
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6 space-y-4">
          <h3 className="text-sm font-semibold text-white mb-1">Configuration</h3>

          <div>
            <label className="text-xs text-gray-400 block mb-1">Base Model</label>
            <select
              value={baseModel}
              onChange={(e) => setBaseModel(e.target.value)}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none"
            >
              <option value="flux-dev">Flux Dev</option>
              <option value="sdxl">SDXL 1.0</option>
              <option value="sd15">SD 1.5</option>
            </select>
          </div>

          <div>
            <label className="text-xs text-gray-400 block mb-1">Training Steps</label>
            <input
              type="number"
              value={steps}
              onChange={(e) => setSteps(Number(e.target.value))}
              min={100}
              max={10000}
              step={100}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none"
            />
          </div>

          <div>
            <label className="text-xs text-gray-400 block mb-1">LoRA Rank</label>
            <select
              value={rank}
              onChange={(e) => setRank(Number(e.target.value))}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none"
            >
              <option value={4}>4 (Smallest)</option>
              <option value={8}>8</option>
              <option value={16}>16 (Recommended)</option>
              <option value={32}>32</option>
              <option value={64}>64 (Largest)</option>
            </select>
          </div>

          <div>
            <label className="text-xs text-gray-400 block mb-1">Trigger Word</label>
            <input
              type="text"
              value={triggerWord}
              onChange={(e) => setTriggerWord(e.target.value)}
              placeholder="e.g. sks, ohwx"
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 placeholder:text-gray-600 outline-none"
            />
          </div>

          <button
            onClick={handleStartTraining}
            disabled={submitting || files.length === 0 || !triggerWord.trim()}
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {submitting ? "Starting..." : "Start Training"}
          </button>
          <p className="text-[10px] text-gray-600 text-center mt-1">
            Estimated: ~{Math.round(steps / 60)} min · ~${((steps / 3600) * 1.5).toFixed(2)} GPU cost
          </p>
        </div>
      </div>

      {/* Training Job History */}
      <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
        <h3 className="text-sm font-semibold text-white mb-4">Training History</h3>
        {jobs.length === 0 ? (
          <p className="text-sm text-gray-500 text-center py-6">No training jobs yet. Upload images and start training to see history here.</p>
        ) : (
          <div className="space-y-2">
            {jobs.map((job) => (
              <div key={job.id} className="flex items-center gap-4 rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-3">
                {statusIcon(job.status)}
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-200 truncate">
                    {job.trigger_word} — {job.base_model}
                  </p>
                  <p className="text-xs text-gray-500">
                    {job.steps} steps • rank {job.rank} • {new Date(job.created_at).toLocaleDateString()}
                  </p>
                </div>
                <span className="text-xs text-gray-500 capitalize">{job.status}</span>
                {job.progress !== undefined && job.status === "running" && (
                  <div className="w-20 h-1.5 bg-white/[0.05] rounded-full overflow-hidden">
                    <div className="h-full bg-blue-500 rounded-full" style={{ width: `${job.progress}%` }} />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
