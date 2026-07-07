"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

import { useEffect, useState } from "react";
import { Cpu, ArrowRight, Loader2 } from "lucide-react";

interface WorkflowSummary {
  id: string;
  name: string;
  description: string;
  node_count: number;
  requires: string[];
}

interface WorkflowNode {
  id: string;
  class_type: string;
  title: string;
  inputs: Record<string, unknown>;
}

interface WorkflowConnection {
  from_node: string;
  from_output: number;
  to_node: string;
  to_input: string;
}

interface WorkflowDetail {
  id: string;
  meta: Record<string, unknown>;
  nodes: WorkflowNode[];
  connections: WorkflowConnection[];
  node_count: number;
}

// Node type → color mapping
const NODE_COLORS: Record<string, string> = {
  CheckpointLoaderSimple: "border-purple-500/50 bg-purple-500/10",
  CLIPTextEncode: "border-blue-500/50 bg-blue-500/10",
  KSampler: "border-green-500/50 bg-green-500/10",
  EmptyLatentImage: "border-amber-500/50 bg-amber-500/10",
  VAEDecode: "border-pink-500/50 bg-pink-500/10",
  SaveImage: "border-cyan-500/50 bg-cyan-500/10",
  LoraLoader: "border-orange-500/50 bg-orange-500/10",
  UNETLoader: "border-purple-500/50 bg-purple-500/10",
  DualCLIPLoader: "border-blue-500/50 bg-blue-500/10",
};

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowDetail | null>(null);
  const [viewLoading, setViewLoading] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/workflows`)
      .then((r) => r.json())
      .then((data) => { if (Array.isArray(data)) setWorkflows(data); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function viewWorkflow(id: string) {
    setViewLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/workflows/${id}`);
      const data = await resp.json();
      setSelectedWorkflow(data);
    } catch {
      setSelectedWorkflow(null);
    } finally {
      setViewLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-purple-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Workflow Viewer</h1>
        <p className="text-sm text-gray-500">
          Read-only visualization of ComfyUI workflow templates used for generation.
        </p>
      </div>

      {/* Workflow List */}
      {!selectedWorkflow && (
        <div className="grid grid-cols-2 gap-4">
          {workflows.map((wf) => (
            <button
              key={wf.id}
              onClick={() => viewWorkflow(wf.id)}
              className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5 text-left hover:border-purple-500/30 transition-all"
            >
              <div className="flex items-center gap-3 mb-2">
                <Cpu className="h-5 w-5 text-purple-400" />
                <h3 className="text-sm font-semibold text-white">{wf.name}</h3>
              </div>
              <p className="text-xs text-gray-500 mb-3">{wf.description}</p>
              <div className="flex items-center gap-3 text-[10px] text-gray-600">
                <span>{wf.node_count} nodes</span>
                {wf.requires.length > 0 && (
                  <span>Requires: {wf.requires.join(", ")}</span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Workflow Detail View */}
      {viewLoading && (
        <div className="flex items-center justify-center h-32">
          <Loader2 className="h-6 w-6 animate-spin text-purple-500" />
        </div>
      )}

      {selectedWorkflow && !viewLoading && (
        <div className="space-y-4">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-white">
                {(selectedWorkflow.meta.name as string) || selectedWorkflow.id}
              </h2>
              <p className="text-xs text-gray-500">
                {selectedWorkflow.node_count} nodes · {selectedWorkflow.connections.length} connections
              </p>
            </div>
            <button
              onClick={() => setSelectedWorkflow(null)}
              className="rounded-lg border border-white/[0.08] px-3 py-1.5 text-xs text-gray-300 hover:bg-white/[0.04]"
            >
              ← Back to list
            </button>
          </div>

          {/* Pipeline Visualization */}
          <div className="rounded-xl border border-white/[0.06] bg-[#0a0a1a] p-6 overflow-x-auto">
            <div className="flex items-start gap-4 min-w-max">
              {/* Render nodes in topological order (simplified: by ID) */}
              {selectedWorkflow.nodes
                .sort((a, b) => parseInt(a.id) - parseInt(b.id))
                .map((node, idx) => {
                  const colorClass = NODE_COLORS[node.class_type] || "border-gray-500/50 bg-gray-500/10";
                  const incomingConnections = selectedWorkflow.connections.filter(
                    (c) => c.to_node === node.id
                  );
                  const outgoingConnections = selectedWorkflow.connections.filter(
                    (c) => c.from_node === node.id
                  );

                  return (
                    <div key={node.id} className="flex items-center gap-3">
                      {/* Node Card */}
                      <div className={`rounded-lg border p-3 min-w-[180px] ${colorClass}`}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[9px] text-gray-500 font-mono">#{node.id}</span>
                          {outgoingConnections.length > 0 && (
                            <span className="text-[8px] text-gray-600">{outgoingConnections.length} out</span>
                          )}
                        </div>
                        <p className="text-xs font-semibold text-white mb-0.5">{node.title}</p>
                        <p className="text-[10px] text-gray-500 font-mono">{node.class_type}</p>

                        {/* Show non-connection inputs */}
                        {Object.keys(node.inputs).length > 0 && (
                          <div className="mt-2 space-y-0.5">
                            {Object.entries(node.inputs).slice(0, 3).map(([key, val]) => (
                              <div key={key} className="flex items-center gap-1">
                                <span className="text-[8px] text-gray-600">{key}:</span>
                                <span className="text-[8px] text-gray-400 truncate max-w-[100px]">
                                  {String(val).slice(0, 30)}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Connection dots */}
                        {incomingConnections.length > 0 && (
                          <div className="mt-1.5 flex gap-1">
                            {incomingConnections.map((c, i) => (
                              <span key={i} className="text-[8px] text-purple-400">
                                ←#{c.from_node}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Arrow to next node */}
                      {idx < selectedWorkflow.nodes.length - 1 && (
                        <ArrowRight className="h-4 w-4 text-gray-600 shrink-0" />
                      )}
                    </div>
                  );
                })}
            </div>
          </div>

          {/* Connections Table */}
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
            <h3 className="text-sm font-semibold text-white mb-3">Connections</h3>
            <div className="space-y-1">
              {selectedWorkflow.connections.map((conn, idx) => {
                const fromNode = selectedWorkflow.nodes.find((n) => n.id === conn.from_node);
                const toNode = selectedWorkflow.nodes.find((n) => n.id === conn.to_node);
                return (
                  <div key={idx} className="flex items-center gap-2 text-[10px] text-gray-400">
                    <span className="text-purple-400 font-mono">#{conn.from_node}</span>
                    <span className="text-gray-600">{fromNode?.title || conn.from_node}</span>
                    <ArrowRight className="h-3 w-3 text-gray-600" />
                    <span className="text-blue-400 font-mono">#{conn.to_node}</span>
                    <span className="text-gray-600">{toNode?.title || conn.to_node}</span>
                    <span className="text-gray-600 ml-auto">.{conn.to_input}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
