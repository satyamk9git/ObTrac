"use client";

import { useEffect, useState, Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";

const API = "http://localhost:8100/api/v1";

function PromptDetailContent() {
  const params = useParams();
  const searchParams = useSearchParams();
  const name = params.name as string;
  const project = searchParams.get("project") || "default";

  const [prompt, setPrompt] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("editor");

  // Editor state
  const [template, setTemplate] = useState("");
  const [commitMsg, setCommitMsg] = useState("");
  const [model, setModel] = useState("");
  const [temperature, setTemperature] = useState("");

  // Diff state
  const [versionA, setVersionA] = useState<number | null>(null);
  const [versionB, setVersionB] = useState<number | null>(null);

  // Test/render state
  const [testVars, setTestVars] = useState<Record<string, string>>({});
  const [renderResult, setRenderResult] = useState("");

  const fetchPrompt = () => {
    setLoading(true);
    fetch(`${API}/prompts/${name}?project=${encodeURIComponent(project)}`)
      .then(r => r.json())
      .then(d => {
        setPrompt(d);
        const active = d.active || d.versions?.[0];
        if (active) {
          setTemplate(active.template || "");
          setModel(active.model || "");
          setTemperature(active.temperature?.toString() || "");
        }
      })
      .catch(() => setPrompt(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchPrompt(); }, [name, project]);

  const handleSaveNewVersion = async () => {
    if (!commitMsg.trim()) {
      alert("Please add a commit message");
      return;
    }
    const res = await fetch(`${API}/prompts/${name}/versions?project=${encodeURIComponent(project)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template,
        model: model || null,
        temperature: temperature ? parseFloat(temperature) : null,
        commit_message: commitMsg,
        created_by: "satyam",
      }),
    });
    if (res.ok) {
      setCommitMsg("");
      fetchPrompt();
    }
  };

  const handleActivate = async (version: number) => {
    await fetch(`${API}/prompts/${name}/versions/${version}/activate?project=${encodeURIComponent(project)}`, {
      method: "POST",
    });
    fetchPrompt();
  };

  const handleRender = async () => {
    const res = await fetch(`${API}/prompts/${name}/render?project=${encodeURIComponent(project)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(testVars),
    });
    const data = await res.json();
    setRenderResult(data.rendered || data.detail || "Error");
  };

  if (loading) return <div className="text-gray-500">Loading...</div>;
  if (!prompt) return <div className="text-red-500">Prompt not found</div>;

  const versions = prompt.versions || [];
  const activeVersion = prompt.active || versions[0];
  const variables = activeVersion?.variables || [];

  const versionA_data = versionA != null ? versions.find((v: any) => v.version === versionA) : null;
  const versionB_data = versionB != null ? versions.find((v: any) => v.version === versionB) : null;

  const TABS = [
    { id: "editor", label: "Editor" },
    { id: "versions", label: `Versions (${versions.length})` },
    { id: "diff", label: "Diff" },
    { id: "test", label: "Test / Render" },
    { id: "code", label: "Use in Code" },
  ];

  return (
    <div>
      <div className="flex items-center gap-3 mb-2">
        <Link href={`/prompts?project=${encodeURIComponent(project)}`}
          className="text-xs text-gray-400 hover:text-gray-600">← Prompts</Link>
      </div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{prompt.name}</h1>
          <p className="text-sm text-gray-500">{prompt.description}</p>
          <div className="flex gap-2 mt-1">
            <span className="badge badge-info">v{activeVersion?.version} (active)</span>
            {(prompt.tags || []).map((t: string) => <span key={t} className="badge badge-purple">{t}</span>)}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-gray-200">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t.id ? "border-indigo-600 text-indigo-600" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ============ EDITOR ============ */}
      {tab === "editor" && (
        <div className="space-y-4">
          <div className="card">
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-semibold text-gray-700">Template</label>
              <span className="text-xs text-gray-400">
                Variables auto-detected: {variables.length > 0 ? variables.join(", ") : "none"}
              </span>
            </div>
            <textarea value={template} onChange={e => setTemplate(e.target.value)} rows={14}
              className="w-full font-mono text-xs bg-gray-900 text-green-400 rounded-lg p-4 outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="You are a helpful assistant.&#10;&#10;Context: {context}&#10;&#10;Question: {question}&#10;&#10;Answer:" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Model (optional)</label>
              <input value={model} onChange={e => setModel(e.target.value)}
                className="input-dark" placeholder="gpt-4o" />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Temperature (optional)</label>
              <input type="number" step="0.1" value={temperature} onChange={e => setTemperature(e.target.value)}
                className="input-dark" placeholder="0.3" />
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-600 mb-1">Commit message (required for new version)</label>
            <input value={commitMsg} onChange={e => setCommitMsg(e.target.value)}
              className="input-dark" placeholder="Improved instruction clarity" />
          </div>

          <button onClick={handleSaveNewVersion} disabled={!commitMsg.trim()}
            className="btn-primary disabled:opacity-50">
            Save as New Version (v{(activeVersion?.version || 0) + 1})
          </button>
        </div>
      )}

      {/* ============ VERSIONS ============ */}
      {tab === "versions" && (
        <div className="card p-0 overflow-hidden">
          <table className="table-dark">
            <thead>
              <tr>
                <th>Version</th>
                <th>Commit Message</th>
                <th>Author</th>
                <th>Created</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {versions.map((v: any) => (
                <tr key={v.id}>
                  <td className="font-mono text-indigo-600">v{v.version}</td>
                  <td className="text-gray-700">{v.commit_message || "—"}</td>
                  <td className="text-gray-500">{v.created_by || "—"}</td>
                  <td className="text-xs text-gray-500">{v.created_at ? new Date(v.created_at).toLocaleString() : "—"}</td>
                  <td>
                    {v.is_active ? <span className="badge badge-success">Active</span> : <span className="text-xs text-gray-400">—</span>}
                  </td>
                  <td>
                    {!v.is_active && (
                      <button onClick={() => handleActivate(v.version)}
                        className="text-xs text-indigo-600 hover:text-indigo-500">Activate</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ============ DIFF ============ */}
      {tab === "diff" && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Version A</label>
              <select value={versionA ?? ""} onChange={e => setVersionA(parseInt(e.target.value))} className="select-dark">
                <option value="">Select...</option>
                {versions.map((v: any) => <option key={v.id} value={v.version}>v{v.version} — {v.commit_message?.substring(0, 40)}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Version B</label>
              <select value={versionB ?? ""} onChange={e => setVersionB(parseInt(e.target.value))} className="select-dark">
                <option value="">Select...</option>
                {versions.map((v: any) => <option key={v.id} value={v.version}>v{v.version} — {v.commit_message?.substring(0, 40)}</option>)}
              </select>
            </div>
          </div>

          {versionA_data && versionB_data && (
            <div className="grid grid-cols-2 gap-3">
              <div className="card border-l-4 border-l-blue-400">
                <h4 className="text-sm font-semibold text-blue-700 mb-2">v{versionA_data.version}</h4>
                <pre className="text-xs font-mono whitespace-pre-wrap text-gray-700 bg-blue-50 p-3 rounded max-h-96 overflow-auto">
                  {versionA_data.template}
                </pre>
              </div>
              <div className="card border-l-4 border-l-green-400">
                <h4 className="text-sm font-semibold text-green-700 mb-2">v{versionB_data.version}</h4>
                <pre className="text-xs font-mono whitespace-pre-wrap text-gray-700 bg-green-50 p-3 rounded max-h-96 overflow-auto">
                  {versionB_data.template}
                </pre>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ============ TEST / RENDER ============ */}
      {tab === "test" && (
        <div className="space-y-4">
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Variables</h3>
            {variables.length === 0 ? (
              <p className="text-xs text-gray-500">No variables in this template.</p>
            ) : (
              <div className="space-y-2">
                {variables.map((v: string) => (
                  <div key={v}>
                    <label className="block text-xs text-gray-600 mb-1">{`{${v}}`}</label>
                    <input value={testVars[v] || ""} onChange={e => setTestVars({ ...testVars, [v]: e.target.value })}
                      className="input-dark" placeholder={`Value for ${v}`} />
                  </div>
                ))}
              </div>
            )}
            <button onClick={handleRender} className="btn-primary mt-3">Render</button>
          </div>

          {renderResult && (
            <div className="card">
              <h3 className="text-sm font-semibold text-gray-700 mb-2">Rendered Output</h3>
              <pre className="text-xs font-mono whitespace-pre-wrap text-green-400 bg-gray-900 p-4 rounded">
                {renderResult}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* ============ USE IN CODE ============ */}
      {tab === "code" && (
        <div className="space-y-4">
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Python SDK Usage</h3>
            <pre className="text-xs font-mono text-green-400 bg-gray-900 p-4 rounded whitespace-pre-wrap">
{`from obtrac_sdk import obtrac_config, get_prompt

obtrac_config(project="${project}")

# Fetch latest active version
prompt = get_prompt("${name}")

# Render with variables
text = prompt.render(${variables.map((v: string) => `${v}="..."`).join(", ")})

# Use in your LLM call
response = llm.invoke(text)`}
            </pre>
          </div>

          <div className="card">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Specific Version</h3>
            <pre className="text-xs font-mono text-green-400 bg-gray-900 p-4 rounded whitespace-pre-wrap">
{`# Pin to specific version
prompt = get_prompt("${name}", version=2)
text = prompt.render(${variables.map((v: string) => `${v}="..."`).join(", ")})`}
            </pre>
          </div>

          <div className="card">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">REST API</h3>
            <pre className="text-xs font-mono text-green-400 bg-gray-900 p-4 rounded whitespace-pre-wrap">
{`# Get latest version
GET ${API}/prompts/${name}/latest?project=${project}

# Get specific version
GET ${API}/prompts/${name}/versions/2?project=${project}

# Render with variables
POST ${API}/prompts/${name}/render?project=${project}
{
  ${variables.map((v: string) => `"${v}": "..."`).join(",\n  ")}
}`}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

export default function PromptDetailPage() {
  return <Suspense fallback={<div className="text-gray-500">Loading...</div>}><PromptDetailContent /></Suspense>;
}
