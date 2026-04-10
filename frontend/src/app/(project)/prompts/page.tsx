"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

const API = "http://localhost:8100/api/v1";

function PromptsContent() {
  const searchParams = useSearchParams();
  const project = searchParams.get("project") || "default";
  const [prompts, setPrompts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  // New prompt form
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newTags, setNewTags] = useState("");
  const [newTemplate, setNewTemplate] = useState("");
  const [newCommit, setNewCommit] = useState("Initial version");

  const fetchPrompts = () => {
    setLoading(true);
    fetch(`${API}/prompts`)
      .then(r => r.json())
      .then(d => setPrompts(d.prompts || []))
      .catch(() => setPrompts([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchPrompts(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const res = await fetch(`${API}/prompts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: newName,
        description: newDesc,
        tags: newTags.split(",").map(t => t.trim()).filter(Boolean),
        template: newTemplate,
        commit_message: newCommit,
        created_by: "satyam",
      }),
    });
    if (res.ok) {
      setShowForm(false);
      setNewName(""); setNewDesc(""); setNewTags(""); setNewTemplate(""); setNewCommit("Initial version");
      fetchPrompts();
    } else {
      const err = await res.json();
      alert(err.detail || "Failed to create prompt");
    }
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`Delete prompt '${name}'?`)) return;
    await fetch(`${API}/prompts/${name}`, { method: "DELETE" });
    fetchPrompts();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Prompts</h1>
          <p className="text-sm text-gray-500">{prompts.length} prompt{prompts.length !== 1 ? "s" : ""} — globally accessible across all projects</p>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="btn-primary">
          {showForm ? "Cancel" : "+ New Prompt"}
        </button>
      </div>

      {/* New Prompt Form */}
      {showForm && (
        <form onSubmit={handleCreate} className="card mb-6 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Name</label>
              <input value={newName} onChange={e => setNewName(e.target.value)} required
                className="input-dark" placeholder="rag_answer_prompt" />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Tags (comma separated)</label>
              <input value={newTags} onChange={e => setNewTags(e.target.value)}
                className="input-dark" placeholder="rag, production" />
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">Description</label>
            <input value={newDesc} onChange={e => setNewDesc(e.target.value)}
              className="input-dark" placeholder="Main RAG answer generation prompt" />
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">Template — use {`{variable}`} for variables</label>
            <textarea value={newTemplate} onChange={e => setNewTemplate(e.target.value)} required rows={6}
              className="input-dark font-mono text-xs" placeholder="You are a helpful assistant.&#10;&#10;Context: {context}&#10;&#10;Question: {question}&#10;&#10;Answer:" />
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">Commit message</label>
            <input value={newCommit} onChange={e => setNewCommit(e.target.value)}
              className="input-dark" placeholder="Initial version" />
          </div>
          <button type="submit" className="btn-primary">Create Prompt</button>
        </form>
      )}

      {/* Prompts List */}
      {loading ? (
        <div className="flex justify-center py-20">
          <div className="animate-spin w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full" />
        </div>
      ) : prompts.length === 0 ? (
        <div className="card text-center py-16">
          <h3 className="text-lg font-semibold text-gray-700 mb-2">No prompts yet</h3>
          <p className="text-sm text-gray-500 max-w-md mx-auto mb-4">
            Create your first prompt to start versioning. Use it in code with:
          </p>
          <pre className="bg-gray-50 p-3 rounded-lg text-xs text-left max-w-md mx-auto text-gray-600">
{`from obtrac_sdk import get_prompt

prompt = get_prompt("my_prompt")
text = prompt.render(question="...", context="...")`}
          </pre>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {prompts.map(p => (
            <div key={p.id} className="card hover:border-indigo-300 transition-colors">
              <div className="flex items-start justify-between mb-2">
                <div className="flex-1">
                  <Link href={`/prompts/${p.name}`}
                    className="text-base font-semibold text-gray-900 hover:text-indigo-600">
                    {p.name}
                  </Link>
                  <p className="text-xs text-gray-500 mt-0.5">{p.description || "No description"}</p>
                </div>
                <button onClick={() => handleDelete(p.name)}
                  className="text-xs text-red-500 hover:text-red-600">Delete</button>
              </div>
              <div className="flex items-center gap-2 mb-2">
                <span className="badge badge-info">v{p.active_version}</span>
                <span className="text-[10px] text-gray-400">{p.version_count} version{p.version_count !== 1 ? "s" : ""}</span>
                {(p.tags || []).map((t: string) => (
                  <span key={t} className="badge badge-purple">{t}</span>
                ))}
              </div>
              <p className="text-[10px] text-gray-400">
                Updated {p.updated_at ? new Date(p.updated_at).toLocaleString() : "—"}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PromptsPage() {
  return <Suspense fallback={<div className="text-gray-500">Loading...</div>}><PromptsContent /></Suspense>;
}
