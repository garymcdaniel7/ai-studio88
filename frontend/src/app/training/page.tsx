"use client";

import { useState, useEffect } from "react";
import { Upload, Play, Clock, CheckCircle2, XCircle, Loader2 } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

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
  const [talentId, setTalentId] = useState<string | null>(null);
  const [talentName, setTalentName] = useState<string | null>(null);
  const [talentImages, setTalentImages] = useState<{id: string; url: string; filename: string}[]>([]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [optimizer, setOptimizer] = useState("adamw_bf16");
  const [scheduler, setScheduler] = useState("polynomial");
  const [resolution, setResolution] = useState(1024);
  const [batchSize, setBatchSize] = useState(1);
  const [trainingPreset, setTrainingPreset] = useState("standard");

  // Training presets — users pick quality level, system handles the rest
  function applyPreset(preset: string) {
    setTrainingPreset(preset);
    switch (preset) {
      case "quick":
        setSteps(500); setRank(8); setResolution(512); setBatchSize(2);
        break;
      case "standard":
        setSteps(1000); setRank(16); setResolution(1024); setBatchSize(1);
        break;
      case "quality":
        setSteps(2000); setRank(32); setResolution(1024); setBatchSize(1);
        break;
    }
  }
  const [learningRate, setLearningRate] = useState("1e-4");
  const [captionMethod, setCaptionMethod] = useState("filename");
  const [provider, setProvider] = useState("simpletuner");

  // Read talent_id from URL params (navigated from Talent page "Train LoRA" button)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tid = params.get("talent_id");
    if (tid) {
      setTalentId(tid);
      fetch(`${API_BASE}/api/v1/talent/${tid}`)
        .then((r) => r.json())
        .then((d) => { if (d.name) setTalentName(d.name); })
        .catch(() => {});
      // Auto-load talent's training images
      fetch(`${API_BASE}/api/v1/talent/${tid}/media`)
        .then((r) => r.json())
        .then((images) => {
          if (Array.isArray(images) && images.length > 0) {
            setTalentImages(images.map((img: Record<string, unknown>) => ({
              id: img.id as string,
              url: `${API_BASE}${img.public_url as string}`,
              filename: (img.original_filename as string) || "photo.png",
            })));
          }
        })
        .catch(() => {});
    }
  }, []);

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

    // Poll for job status updates every 5s when there are running/queued jobs
    const interval = setInterval(async () => {
      if (!active) return;
      try {
        const resp = await fetch(`${API_BASE}/api/v1/training/jobs`);
        if (resp.ok) {
          const data = await resp.json();
          const jobList = Array.isArray(data) ? data : data.jobs || [];
          setJobs(jobList);
          // Stop polling if no active jobs
          const hasActive = jobList.some((j: TrainingJob) => j.status === "running" || j.status === "queued");
          if (!hasActive) clearInterval(interval);
        }
      } catch {}
    }, 5000);

    return () => { active = false; clearInterval(interval); };
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
    if ((files.length === 0 && talentImages.length === 0) || !triggerWord.trim()) return;
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
      if (talentId) formData.append("talent_id", talentId);
      // If no new files uploaded but talent images exist, pass their IDs
      if (files.length === 0 && talentImages.length > 0) {
        formData.append("use_talent_media", "true");
        talentImages.forEach((img) => formData.append("talent_image_ids", img.id));
      }

      const resp = await fetch(`${API_BASE}/api/v1/training/start`, {
        method: "POST",
        body: formData,
      });
      if (resp.ok) {
        setFiles([]);
        setTriggerWord("");
        await fetchJobs();
      } else {
        const err = await resp.json().catch(() => ({}));
        alert((err as Record<string, string>).detail || "Training submission failed");
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
        {talentName && (
          <p className="text-xs text-purple-400 mt-1">Training for talent: {talentName}</p>
        )}
      </div>

      {/* Upload + Configuration */}
      <div className="grid grid-cols-2 gap-6">
        {/* Upload Area */}
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
          <h3 className="text-sm font-semibold text-white mb-3">Training Images</h3>
          {/* Pre-loaded talent images */}
          {talentImages.length > 0 && files.length === 0 && (
            <div className="mb-4 rounded-lg border border-green-500/20 bg-green-500/5 p-3">
              <p className="text-xs text-green-400 font-medium mb-2">
                {talentImages.length} images loaded from {talentName || "talent"}
              </p>
              <div className="flex flex-wrap gap-2">
                {talentImages.slice(0, 12).map((img) => (
                  <div key={img.id} className="w-12 h-12 rounded overflow-hidden border border-white/[0.08]">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={img.url} alt={img.filename} className="w-full h-full object-cover" />
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-gray-500 mt-2">These images will be used for training. Upload more below if needed.</p>
            </div>
          )}
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

          {/* Quality Preset — the human-friendly way to configure training */}
          <div>
            <label className="text-xs text-gray-400 block mb-2">Quality Level</label>
            <div className="grid grid-cols-3 gap-3">
              {[
                { id: "quick", name: "Quick", desc: "15 min • $1.50 • Good for testing", badge: "Fast" },
                { id: "standard", name: "Standard", desc: "45 min • $3.00 • Recommended", badge: "Best" },
                { id: "quality", name: "Quality", desc: "2 hrs • $8.00 • Maximum detail", badge: "Pro" },
              ].map((preset) => (
                <button
                  key={preset.id}
                  onClick={() => applyPreset(preset.id)}
                  className={`rounded-lg border p-3 text-left transition-all ${
                    trainingPreset === preset.id
                      ? "border-purple-500/50 bg-purple-600/10"
                      : "border-white/[0.08] bg-white/[0.03] hover:border-white/[0.15]"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-white">{preset.name}</span>
                    <span className={`text-[9px] px-1.5 py-0.5 rounded ${
                      preset.id === "standard" ? "bg-purple-600/20 text-purple-400" : "bg-white/[0.06] text-gray-500"
                    }`}>{preset.badge}</span>
                  </div>
                  <p className="text-[10px] text-gray-500">{preset.desc}</p>
                </button>
              ))}
            </div>
          </div>

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
              <option value={16}>16 (Default)</option>
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

          {/* Advanced Settings Toggle */}
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-xs text-purple-400 hover:text-purple-300 transition-colors"
          >
            {showAdvanced ? "▾ Hide Advanced" : "▸ Advanced Settings"}
          </button>

          {showAdvanced && (
            <div className="space-y-3 rounded-lg border border-purple-500/20 bg-purple-500/5 p-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-gray-400 block mb-1">Provider</label>
                  <select
                    value={provider}
                    onChange={(e) => setProvider(e.target.value)}
                    className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-200 outline-none"
                  >
                    <option value="simpletuner">SimpleTuner (Recommended)</option>
                    <option value="vast">Vast.ai (Legacy)</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-gray-400 block mb-1">Learning Rate</label>
                  <select
                    value={learningRate}
                    onChange={(e) => setLearningRate(e.target.value)}
                    className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-200 outline-none"
                  >
                    <option value="1e-5">1e-5 (Conservative)</option>
                    <option value="5e-5">5e-5</option>
                    <option value="1e-4">1e-4 (Default)</option>
                    <option value="3e-4">3e-4 (Aggressive)</option>
                    <option value="1e-3">1e-3 (Fast)</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-gray-400 block mb-1">Optimizer</label>
                  <select
                    value={optimizer}
                    onChange={(e) => setOptimizer(e.target.value)}
                    className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-200 outline-none"
                  >
                    <option value="adamw_bf16">AdamW BF16 (Default)</option>
                    <option value="prodigy">Prodigy (Auto LR)</option>
                    <option value="adafactor">Adafactor (Low Memory)</option>
                    <option value="adam8bit">Adam 8-bit</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-gray-400 block mb-1">Scheduler</label>
                  <select
                    value={scheduler}
                    onChange={(e) => setScheduler(e.target.value)}
                    className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-200 outline-none"
                  >
                    <option value="polynomial">Polynomial (Default)</option>
                    <option value="cosine">Cosine</option>
                    <option value="constant">Constant</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-[10px] text-gray-400 block mb-1">Resolution</label>
                  <select
                    value={resolution}
                    onChange={(e) => setResolution(Number(e.target.value))}
                    className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-200 outline-none"
                  >
                    <option value={512}>512px</option>
                    <option value={768}>768px</option>
                    <option value={1024}>1024px (Default)</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-gray-400 block mb-1">Batch Size</label>
                  <select
                    value={batchSize}
                    onChange={(e) => setBatchSize(Number(e.target.value))}
                    className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-200 outline-none"
                  >
                    <option value={1}>1 (Default)</option>
                    <option value={2}>2 (Faster, more VRAM)</option>
                    <option value={4}>4 (Fast, 48GB+ VRAM)</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-gray-400 block mb-1">Captioning</label>
                  <select
                    value={captionMethod}
                    onChange={(e) => setCaptionMethod(e.target.value)}
                    className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-200 outline-none"
                  >
                    <option value="filename">From Filename</option>
                    <option value="textfile">From .txt Files</option>
                    <option value="blip">Auto (BLIP)</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          <button
            onClick={handleStartTraining}
            disabled={submitting || (files.length === 0 && talentImages.length === 0) || !triggerWord.trim()}
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {submitting ? "Starting..." : "Start Training"}
          </button>
          <p className="text-[10px] text-gray-600 text-center mt-1">
            Estimated: ~{Math.round(steps / 60)} min · ~${((steps / 3600) * 1.5).toFixed(2)} GPU cost · Provider: {provider}
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
