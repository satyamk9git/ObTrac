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

  // Merge state
  const [mergeSelected, setMergeSelected] = useState<number[]>([]);
  const [mergeLLMs, setMergeLLMs] = useState<any[]>([]);
  const [mergeLLMId, setMergeLLMId] = useState("");
  const [mergeDraft, setMergeDraft] = useState<any>(null);
  const [mergeRunning, setMergeRunning] = useState(false);
  const [editedDraftTemplate, setEditedDraftTemplate] = useState("");
  const [regenerateInstructions, setRegenerateInstructions] = useState("");
  const [regenerating, setRegenerating] = useState(false);

  // Lineage / version detail expand
  const [expandedVersion, setExpandedVersion] = useState<number | null>(null);

  // Fetch LLM configs for merge dropdown
  useEffect(() => {
    fetch(`${API}/llm-configs`)
      .then(r => r.json())
      .then(d => {
        setMergeLLMs(d.configs || []);
        const autoEval = d.configs?.find((c: any) => c.use_for_auto_eval);
        if (autoEval) setMergeLLMId(autoEval.id);
      })
      .catch(() => {});
  }, []);

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

  const handleMerge = async () => {
    if (mergeSelected.length < 2) {
      alert("Select at least 2 versions");
      return;
    }
    setMergeRunning(true);
    setMergeDraft(null);
    try {
      const res = await fetch(`${API}/prompts/${name}/merge?project=${encodeURIComponent(project)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          versions: mergeSelected,
          llm_config_id: mergeLLMId || null,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setMergeDraft(data);
        setEditedDraftTemplate(data.merged_template || "");
      } else {
        alert(data.detail || "Merge failed");
      }
    } catch (e) {
      alert(`Error: ${e}`);
    } finally {
      setMergeRunning(false);
    }
  };

  const handleRegenerateDraft = async () => {
    if (!mergeDraft) return;
    setRegenerating(true);
    try {
      const res = await fetch(`${API}/prompts/${name}/merge?project=${encodeURIComponent(project)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          versions: mergeDraft.merged_from,
          llm_config_id: mergeLLMId || mergeDraft.llm_config_id || null,
          extra_instructions: regenerateInstructions.trim() || null,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        // Discard the old draft so we don't leak in-memory entries
        try {
          await fetch(`${API}/prompts/drafts/${mergeDraft.draft_id}`, { method: "DELETE" });
        } catch {}
        setMergeDraft(data);
        setEditedDraftTemplate(data.merged_template || "");
      } else {
        alert(data.detail || "Regeneration failed");
      }
    } catch (e) {
      alert(`Error: ${e}`);
    } finally {
      setRegenerating(false);
    }
  };

  const handleApproveDraft = async () => {
    if (!mergeDraft) return;
    const res = await fetch(`${API}/prompts/drafts/${mergeDraft.draft_id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: editedDraftTemplate,
        commit_message: `Merged from versions ${mergeDraft.merged_from.join(", ")} using ${mergeDraft.merged_by_llm}`,
      }),
    });
    if (res.ok) {
      setMergeDraft(null);
      setMergeSelected([]);
      setEditedDraftTemplate("");
      fetchPrompt();
      setTab("lineage");
    }
  };

  const handleDiscardDraft = async () => {
    if (!mergeDraft) return;
    await fetch(`${API}/prompts/drafts/${mergeDraft.draft_id}`, { method: "DELETE" });
    setMergeDraft(null);
    setEditedDraftTemplate("");
  };

  const handleEditFromVersion = (v: any) => {
    setTemplate(v.template);
    setModel(v.model || "");
    setTemperature(v.temperature?.toString() || "");
    setCommitMsg(`Forked from v${v.version}`);
    setTab("editor");
  };

  const toggleMergeVersion = (v: number) => {
    setMergeSelected(prev =>
      prev.includes(v) ? prev.filter(x => x !== v) : [...prev, v].sort((a, b) => a - b)
    );
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
    { id: "lineage", label: `Lineage (${versions.length})` },
    { id: "merge", label: "Merge with AI" },
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

      {/* ============ LINEAGE ============ */}
      {tab === "lineage" && (
        <div className="space-y-2">
          <p className="text-xs text-gray-500 mb-3">
            Version history (newest first). Click any version to expand and see the template.
          </p>
          {[...versions].sort((a: any, b: any) => b.version - a.version).map((v: any, idx: number) => {
            const isExpanded = expandedVersion === v.version;
            const isLast = idx === versions.length - 1;
            const merged = v.metadata?.merged_from;
            return (
              <div key={v.id} className="relative">
                {/* Connector line */}
                {!isLast && (
                  <div className="absolute left-4 top-12 w-0.5 h-full bg-gray-200" />
                )}

                <div className="flex gap-4">
                  {/* Node circle */}
                  <div className="relative shrink-0">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${
                      v.is_active ? "bg-indigo-600 text-white" : "bg-gray-200 text-gray-600"
                    }`}>
                      v{v.version}
                    </div>
                  </div>

                  {/* Card */}
                  <div className={`flex-1 card cursor-pointer transition-all ${
                    isExpanded ? "border-indigo-300" : ""
                  } ${v.is_active ? "border-l-4 border-l-indigo-500" : ""}`}
                    onClick={() => setExpandedVersion(isExpanded ? null : v.version)}>
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-semibold text-gray-900">v{v.version}</span>
                          {v.is_active && <span className="badge badge-success text-[9px]">ACTIVE</span>}
                          {merged && (
                            <span className="badge badge-purple text-[9px]">
                              Merged from v{merged.join(", v")}
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-gray-600">{v.commit_message || "—"}</p>
                        <p className="text-[10px] text-gray-400 mt-1">
                          {v.created_by || "—"} | {v.created_at ? new Date(v.created_at).toLocaleString() : "—"}
                        </p>
                      </div>
                      <svg className={`w-4 h-4 text-gray-400 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                        fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </div>

                    {isExpanded && (
                      <div className="mt-3 pt-3 border-t border-gray-100 space-y-2">
                        <pre className="text-xs font-mono whitespace-pre-wrap text-green-400 bg-gray-900 p-3 rounded max-h-64 overflow-auto">
                          {v.template}
                        </pre>
                        <div className="flex gap-2">
                          {!v.is_active && (
                            <button onClick={(e) => { e.stopPropagation(); handleActivate(v.version); }}
                              className="text-xs btn-secondary">Activate</button>
                          )}
                          <button onClick={(e) => { e.stopPropagation(); handleEditFromVersion(v); }}
                            className="text-xs btn-primary">Edit & Save as New Version</button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ============ MERGE WITH AI ============ */}
      {tab === "merge" && (
        <div className="space-y-4">
          {!mergeDraft ? (
            <>
              <div className="card">
                <h3 className="text-sm font-semibold text-gray-700 mb-3">Step 1: Select versions to merge (2+)</h3>
                <div className="space-y-2">
                  {versions.map((v: any) => (
                    <label key={v.id} className={`flex items-center gap-3 p-2 rounded cursor-pointer transition-colors ${
                      mergeSelected.includes(v.version) ? "bg-indigo-50 border border-indigo-300" : "hover:bg-gray-50 border border-transparent"
                    }`}>
                      <input type="checkbox" checked={mergeSelected.includes(v.version)}
                        onChange={() => toggleMergeVersion(v.version)} className="w-4 h-4" />
                      <span className="text-sm font-mono text-indigo-600">v{v.version}</span>
                      {v.is_active && <span className="badge badge-success text-[9px]">ACTIVE</span>}
                      <span className="text-xs text-gray-600 truncate">{v.commit_message}</span>
                    </label>
                  ))}
                </div>
                {mergeSelected.length > 0 && mergeSelected.length < 2 && (
                  <p className="text-xs text-yellow-600 mt-2">Select at least 2 versions</p>
                )}
              </div>

              <div className="card">
                <h3 className="text-sm font-semibold text-gray-700 mb-3">Step 2: Choose LLM for merging</h3>
                <select value={mergeLLMId} onChange={e => setMergeLLMId(e.target.value)} className="select-dark">
                  <option value="">Auto-select (use auto-eval LLM)</option>
                  {mergeLLMs.map(c => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.provider}/{c.model_id}) {c.use_for_auto_eval ? "★ auto-eval" : ""}
                    </option>
                  ))}
                </select>
                <p className="text-[10px] text-gray-400 mt-1">
                  The LLM you pick is used to execute the merge. The merge instructions are static and cannot be changed.
                </p>
              </div>

              <button onClick={handleMerge} disabled={mergeRunning || mergeSelected.length < 2}
                className={`px-6 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  mergeRunning ? "bg-yellow-500 text-white animate-pulse" : "bg-indigo-600 text-white hover:bg-indigo-500"
                } disabled:opacity-50`}>
                {mergeRunning ? "AI is merging versions..." : `Merge ${mergeSelected.length} Versions with AI`}
              </button>
            </>
          ) : (
            <>
              {/* Draft preview */}
              <div className="card border-l-4 border-l-purple-400">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold text-purple-700">Draft Merged Version</h3>
                  <span className="text-[10px] text-gray-500">
                    Merged from v{mergeDraft.merged_from.join(", v")} using {mergeDraft.merged_by_llm}
                  </span>
                </div>
                <p className="text-xs text-gray-500 mb-2">
                  Review the merged template below. Edit if needed, then approve to create v{(activeVersion?.version || 0) + 1}.
                </p>

                {mergeDraft.warnings?.length > 0 && (
                  <div className="bg-yellow-50 border border-yellow-200 rounded p-2 mb-2">
                    {mergeDraft.warnings.map((w: string, i: number) => (
                      <p key={i} className="text-xs text-yellow-800">⚠ {w}</p>
                    ))}
                  </div>
                )}

                <textarea value={editedDraftTemplate} onChange={e => setEditedDraftTemplate(e.target.value)}
                  rows={14} className="w-full font-mono text-xs bg-gray-900 text-green-400 rounded-lg p-4 outline-none focus:ring-2 focus:ring-indigo-500" />

                {/* Regenerate with extra guidance */}
                <div className="mt-4 bg-purple-50 border border-purple-200 rounded-lg p-3">
                  <div className="flex items-start gap-2 mb-2">
                    <svg className="w-4 h-4 text-purple-600 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    <div className="flex-1">
                      <p className="text-xs font-semibold text-purple-900">Not happy with the merge? Regenerate with extra guidance.</p>
                      <p className="text-[11px] text-purple-700 mt-0.5">
                        Optionally tell the AI about edge cases, constraints, or specific behaviors you want preserved. Leave blank to just retry with the same instructions.
                      </p>
                    </div>
                  </div>
                  <textarea
                    value={regenerateInstructions}
                    onChange={(e) => setRegenerateInstructions(e.target.value)}
                    rows={3}
                    placeholder="e.g. 'Make sure the prompt handles empty context gracefully', 'Add a constraint to never mention dates', 'Output must be valid JSON'..."
                    className="w-full text-xs border border-purple-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-purple-400 bg-white"
                  />
                  <div className="flex items-center justify-between mt-2">
                    <p className="text-[10px] text-purple-600">
                      Will use {mergeLLMs.find((l) => l.id === (mergeLLMId || mergeDraft.llm_config_id))?.name || mergeDraft.merged_by_llm}
                    </p>
                    <button
                      onClick={handleRegenerateDraft}
                      disabled={regenerating}
                      className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-all ${
                        regenerating
                          ? "bg-gray-200 text-gray-500 cursor-wait"
                          : "bg-purple-600 text-white hover:bg-purple-700"
                      }`}
                    >
                      {regenerating ? "Regenerating..." : (regenerateInstructions.trim() ? "Regenerate with Guidance" : "Regenerate")}
                    </button>
                  </div>
                </div>

                <div className="flex gap-2 mt-3">
                  <button onClick={handleApproveDraft} className="btn-primary">
                    Approve & Create New Version
                  </button>
                  <button onClick={handleDiscardDraft} className="btn-danger">
                    Discard
                  </button>
                </div>
              </div>

              {/* Side-by-side: original versions vs merged */}
              <div className="card">
                <h3 className="text-sm font-semibold text-gray-700 mb-3">Source Versions</h3>
                <div className="grid grid-cols-2 gap-3">
                  {mergeDraft.merged_from.map((vnum: number) => {
                    const v = versions.find((x: any) => x.version === vnum);
                    return v ? (
                      <div key={vnum} className="bg-gray-50 rounded-lg p-3">
                        <p className="text-xs font-semibold text-gray-700 mb-1">v{v.version}</p>
                        <pre className="text-[10px] font-mono whitespace-pre-wrap text-gray-600 max-h-40 overflow-auto">
                          {v.template}
                        </pre>
                      </div>
                    ) : null;
                  })}
                </div>
              </div>
            </>
          )}
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
            <p className="text-xs text-gray-500 mb-3">
              Prompts are <strong>globally accessible</strong> — fetch them by name from any project.
            </p>
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Python SDK Usage</h3>
            <pre className="text-xs font-mono text-green-400 bg-gray-900 p-4 rounded whitespace-pre-wrap">
{`from obtrac_sdk import get_prompt

# Fetch latest active version (works from any project)
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
GET ${API}/prompts/${name}/latest

# Get specific version
GET ${API}/prompts/${name}/versions/2

# Render with variables
POST ${API}/prompts/${name}/render
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
