"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const API = "/api/v1";

function getQualityColor(v: number) {
  if (v >= 0.8) return "text-green-600";
  if (v >= 0.6) return "text-yellow-600";
  return "text-red-600";
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ name: string; count: number } | null>(null);
  const [deleting, setDeleting] = useState(false);

  const loadProjects = () => {
    fetch(`${API}/traces/projects`)
      .then((r) => r.json())
      .then((d) => setProjects(d.projects || []))
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await fetch(`${API}/traces/projects/${encodeURIComponent(deleteTarget.name)}/purge`, { method: "DELETE" });
      setDeleteTarget(null);
      loadProjects();
    } catch {
      // leave the confirm dialog open with its existing content on failure
    } finally {
      setDeleting(false);
    }
  };

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) {
      setCreateError("Project name is required");
      return;
    }
    setCreating(true);
    setCreateError("");
    try {
      const r = await fetch(`${API}/traces/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description: newDesc.trim() }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        setCreateError(err.detail || `Failed (HTTP ${r.status})`);
        return;
      }
      setShowCreate(false);
      setNewName("");
      setNewDesc("");
      loadProjects();
    } catch (e: any) {
      setCreateError(e.message || "Network error");
    } finally {
      setCreating(false);
    }
  };

  const totalTraces = projects.reduce((s, p) => s + p.count, 0);
  const totalCost = projects.reduce((s, p) => s + (p.total_cost_usd || 0), 0);

  return (
    <div className="max-w-6xl mx-auto">
      {/* Stats Row */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="card">
          <p className="text-xs text-gray-500 mb-1">Total Projects</p>
          <p className="text-3xl font-bold text-gray-900">{projects.length}</p>
        </div>
        <div className="card">
          <p className="text-xs text-gray-500 mb-1">Total Traces</p>
          <p className="text-3xl font-bold text-gray-900">{totalTraces}</p>
        </div>
        <div className="card">
          <p className="text-xs text-gray-500 mb-1">Total Cost</p>
          <p className="text-3xl font-bold text-gray-900">${totalCost.toFixed(4)}</p>
        </div>
      </div>

      {/* Project Cards */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Your Projects</h2>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors flex items-center gap-2"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Project
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <svg className="animate-spin w-6 h-6 text-indigo-500" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        </div>
      ) : projects.length === 0 ? (
        <div className="card text-center py-16">
          <div className="w-16 h-16 bg-gray-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-gray-700 mb-2">No projects yet</h3>
          <p className="text-sm text-gray-500 max-w-md mx-auto mb-5">
            Create a project to start logging traces, prompts, and datasets — or run your RAG pipeline with ObTrac decorators and a project will be created automatically.
          </p>
          <button
            onClick={() => setShowCreate(true)}
            className="px-5 py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors inline-flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Create Your First Project
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {projects.map((p) => {
            const hasTraces = p.count > 0;
            const successRate = hasTraces ? (p.success / p.count) * 100 : null;
            const hasQuality = p.avg_quality_score !== null && p.avg_quality_score !== undefined;
            return (
              <Link
                key={p.name}
                href={`/dashboard?project=${encodeURIComponent(p.name)}`}
                className="card group cursor-pointer hover:border-indigo-300 animate-fade-in relative"
              >
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setDeleteTarget({ name: p.name, count: p.count });
                  }}
                  title="Delete project"
                  className="absolute top-3 right-9 p-1 rounded text-gray-300 opacity-0 group-hover:opacity-100 hover:text-red-500 hover:bg-red-50 transition-all"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>

                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="text-base font-semibold text-gray-900 group-hover:text-indigo-600 transition-colors">
                      {p.name}
                    </h3>
                    <p className="text-xs text-gray-400 mt-0.5">
                      Last activity: {p.last_activity ? new Date(p.last_activity).toLocaleString() : "—"}
                    </p>
                  </div>
                  <svg className="w-5 h-5 text-gray-300 group-hover:text-indigo-500 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </div>

                <div className="grid grid-cols-5 gap-2">
                  <div>
                    <p className="text-[10px] text-gray-400 uppercase">Traces</p>
                    <p className="text-lg font-bold text-gray-900">{p.count}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-gray-400 uppercase">Success</p>
                    <p className={`text-lg font-bold ${
                      successRate === null ? "text-gray-300"
                      : successRate >= 90 ? "text-green-600" : successRate >= 70 ? "text-yellow-600" : "text-red-600"
                    }`}>
                      {successRate === null ? "—" : `${successRate.toFixed(0)}%`}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] text-gray-400 uppercase" title="Average evaluation score across evaluated traces — distinct from Success (did the code run without erroring)">Quality</p>
                    <p className={`text-lg font-bold ${hasQuality ? getQualityColor(p.avg_quality_score) : "text-gray-300"}`}>
                      {hasQuality ? `${(p.avg_quality_score * 100).toFixed(0)}%` : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] text-gray-400 uppercase">Latency</p>
                    <p className="text-lg font-bold text-gray-900">{hasTraces ? `${p.avg_latency_ms.toFixed(0)}ms` : "—"}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-gray-400 uppercase">Cost</p>
                    <p className="text-lg font-bold text-gray-900">{hasTraces ? `$${p.total_cost_usd.toFixed(4)}` : "—"}</p>
                  </div>
                </div>

                <div className="mt-3 w-full bg-gray-100 rounded-full h-1.5">
                  <div
                    className="h-1.5 rounded-full bg-gradient-to-r from-green-500 to-emerald-400 transition-all"
                    style={{ width: `${successRate ?? 0}%` }}
                  />
                </div>
              </Link>
            );
          })}
        </div>
      )}

      {/* Create Project Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => !creating && setShowCreate(false)}
          />
          <div className="relative w-full max-w-md bg-white rounded-xl shadow-2xl overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-bold text-gray-900">Create New Project</h2>
              <p className="text-xs text-gray-500 mt-1">
                Use this name in <code className="text-indigo-600">obtrac_config(project=...)</code> in your code.
              </p>
            </div>

            <div className="px-6 py-4 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Project Name *</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. langgraph-agent"
                  className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleCreate();
                    if (e.key === "Escape") setShowCreate(false);
                  }}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Description (optional)</label>
                <textarea
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="What does this project track?"
                  rows={3}
                  className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              {createError && (
                <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1.5">
                  {createError}
                </div>
              )}
            </div>

            <div className="px-6 py-3 border-t border-gray-200 bg-gray-50 flex justify-end gap-2">
              <button
                onClick={() => setShowCreate(false)}
                disabled={creating}
                className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={creating || !newName.trim()}
                className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50"
              >
                {creating ? "Creating..." : "Create Project"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Project Confirmation */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => !deleting && setDeleteTarget(null)}
          />
          <div className="relative w-full max-w-md bg-white rounded-xl shadow-2xl overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-bold text-gray-900">Delete "{deleteTarget.name}"?</h2>
            </div>
            <div className="px-6 py-4">
              <p className="text-sm text-gray-700">
                This permanently deletes{" "}
                <strong>{deleteTarget.count} trace{deleteTarget.count !== 1 ? "s" : ""}</strong>{" "}
                and all their spans, metrics, and annotations. This cannot be undone.
              </p>
              <p className="text-xs text-gray-500 mt-2">
                Prompts (global) and any budgets/alert channels referencing this project name are not affected.
              </p>
            </div>
            <div className="px-6 py-3 border-t border-gray-200 bg-gray-50 flex justify-end gap-2">
              <button
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
                className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 disabled:opacity-50"
              >
                {deleting ? "Deleting..." : "Delete Permanently"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
