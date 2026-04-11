"use client";

import { useEffect, useState } from "react";

const API = "http://localhost:8100/api/v1";

type Embedder = {
  id: string;
  name: string;
  provider: string;
  model_id: string;
  dimensions: number | null;
  api_key: string | null;
  api_base: string | null;
  api_version: string | null;
  azure_deployment: string | null;
  is_default: boolean;
  is_active: boolean;
  created_at: string | null;
};

type ProviderInfo = {
  label: string;
  default_model: string;
  needs_api_key: boolean;
  dimensions_hint: number;
};

const defaultForm = {
  name: "",
  provider: "sentence_transformers",
  model_id: "all-MiniLM-L6-v2",
  dimensions: undefined as number | undefined,
  api_key: "",
  api_base: "",
  api_version: "",
  azure_deployment: "",
  is_default: false,
};

export default function EmbedderConfigPage() {
  const [embedders, setEmbedders] = useState<Embedder[]>([]);
  const [providers, setProviders] = useState<Record<string, ProviderInfo>>({});
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(defaultForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [testResult, setTestResult] = useState<Record<string, any>>({});
  const [testingId, setTestingId] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    Promise.all([
      fetch(`${API}/embedder`).then(r => r.json()),
      fetch(`${API}/embedder/providers`).then(r => r.json()),
    ])
      .then(([list, prov]) => {
        setEmbedders(list.embedders || []);
        setProviders(prov.providers || {});
      })
      .catch(() => {
        setEmbedders([]);
        setProviders({});
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const onProviderChange = (provider: string) => {
    const info = providers[provider];
    setForm({
      ...form,
      provider,
      model_id: info?.default_model || form.model_id,
      dimensions: info?.dimensions_hint,
    });
  };

  const submit = async () => {
    setSaving(true);
    setError("");
    try {
      const res = await fetch(`${API}/embedder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setError(err.detail || `HTTP ${res.status}`);
        return;
      }
      setShowForm(false);
      setForm(defaultForm);
      load();
    } catch (e: any) {
      setError(e.message || "Network error");
    } finally {
      setSaving(false);
    }
  };

  const setDefault = async (id: string) => {
    await fetch(`${API}/embedder/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_default: true }),
    });
    load();
  };

  const remove = async (id: string, name: string) => {
    if (!confirm(`Delete embedder '${name}'?`)) return;
    await fetch(`${API}/embedder/${id}`, { method: "DELETE" });
    load();
  };

  const test = async (id: string) => {
    setTestingId(id);
    setTestResult(prev => ({ ...prev, [id]: null }));
    try {
      const r = await fetch(`${API}/embedder/${id}/test`, { method: "POST" });
      const data = await r.json();
      setTestResult(prev => ({ ...prev, [id]: { ok: r.ok, data } }));
    } catch (e: any) {
      setTestResult(prev => ({ ...prev, [id]: { ok: false, data: { detail: e.message } } }));
    } finally {
      setTestingId(null);
    }
  };

  const providerInfo = providers[form.provider];

  return (
    <div>
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-gray-900">Embedder Config</h1>
            <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 bg-purple-100 text-purple-700 rounded">New</span>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Globally-configured embedding models. Used by semantic ground truth matching and retrieval helpers across all projects.
          </p>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="btn-primary">
          {showForm ? "Cancel" : "+ New Embedder"}
        </button>
      </div>

      {/* Info banner if no embedders */}
      {!loading && embedders.length === 0 && !showForm && (
        <div className="card bg-indigo-50 border-indigo-200 mb-6">
          <div className="flex gap-3">
            <svg className="w-5 h-5 text-indigo-600 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="flex-1">
              <p className="text-sm font-semibold text-indigo-900">No embedders configured — using local fallback</p>
              <p className="text-xs text-indigo-700 mt-1">
                The semantic ground truth matcher is currently using <code>sentence-transformers/all-MiniLM-L6-v2</code> (downloaded automatically on first use). Add a custom embedder if you want to use OpenAI, Azure, Cohere, Vertex, or any other provider.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* New embedder form */}
      {showForm && (
        <div className="card mb-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">Add Embedder</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Name *</label>
              <input
                type="text"
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Local MiniLM"
                className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Provider</label>
              <select
                value={form.provider}
                onChange={e => onProviderChange(e.target.value)}
                className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2"
              >
                {Object.entries(providers).map(([key, info]) => (
                  <option key={key} value={key}>{info.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Model ID</label>
              <input
                type="text"
                value={form.model_id}
                onChange={e => setForm({ ...form, model_id: e.target.value })}
                placeholder={providerInfo?.default_model || "model name"}
                className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 font-mono"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Dimensions (optional)</label>
              <input
                type="number"
                value={form.dimensions || ""}
                onChange={e => setForm({ ...form, dimensions: e.target.value ? parseInt(e.target.value) : undefined })}
                placeholder={String(providerInfo?.dimensions_hint || "")}
                className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2"
              />
            </div>
            {providerInfo?.needs_api_key && (
              <>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">API Key *</label>
                  <input
                    type="password"
                    value={form.api_key}
                    onChange={e => setForm({ ...form, api_key: e.target.value })}
                    placeholder="sk-..."
                    className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">API Base (optional)</label>
                  <input
                    type="text"
                    value={form.api_base}
                    onChange={e => setForm({ ...form, api_base: e.target.value })}
                    placeholder="https://..."
                    className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2"
                  />
                </div>
              </>
            )}
            {form.provider === "azure_openai" && (
              <>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">API Version</label>
                  <input
                    type="text"
                    value={form.api_version}
                    onChange={e => setForm({ ...form, api_version: e.target.value })}
                    placeholder="2024-02-01"
                    className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">Azure Deployment</label>
                  <input
                    type="text"
                    value={form.azure_deployment}
                    onChange={e => setForm({ ...form, azure_deployment: e.target.value })}
                    placeholder="my-embedding-deployment"
                    className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2"
                  />
                </div>
              </>
            )}
            {form.provider === "ollama" && (
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Ollama Base URL</label>
                <input
                  type="text"
                  value={form.api_base}
                  onChange={e => setForm({ ...form, api_base: e.target.value })}
                  placeholder="http://localhost:11434"
                  className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2"
                />
              </div>
            )}
          </div>

          <div className="mt-4 flex items-center gap-2">
            <input
              id="is-default"
              type="checkbox"
              checked={form.is_default}
              onChange={e => setForm({ ...form, is_default: e.target.checked })}
            />
            <label htmlFor="is-default" className="text-xs text-gray-700">
              Set as default embedder (used by semantic GT matching)
            </label>
          </div>

          {error && (
            <div className="mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
              {error}
            </div>
          )}

          <div className="mt-4 flex justify-end gap-2">
            <button onClick={() => { setShowForm(false); setForm(defaultForm); setError(""); }} className="btn-secondary">
              Cancel
            </button>
            <button
              onClick={submit}
              disabled={saving || !form.name.trim()}
              className="btn-primary disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save Embedder"}
            </button>
          </div>
        </div>
      )}

      {/* Embedders list */}
      {loading ? (
        <div className="flex justify-center py-20">
          <div className="animate-spin w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full" />
        </div>
      ) : (
        <div className="space-y-3">
          {embedders.map(e => (
            <div key={e.id} className={`card ${e.is_default ? "border-indigo-300 bg-indigo-50/30" : ""}`}>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="text-base font-semibold text-gray-900">{e.name}</h3>
                    {e.is_default && (
                      <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 bg-indigo-600 text-white rounded">
                        Default
                      </span>
                    )}
                    <span className="text-[10px] text-gray-500 uppercase">{providers[e.provider]?.label || e.provider}</span>
                  </div>
                  <p className="text-xs font-mono text-gray-600">{e.model_id}</p>
                  <div className="flex items-center gap-3 mt-2 text-[11px] text-gray-500">
                    {e.dimensions && <span>{e.dimensions}-dim</span>}
                    {e.api_base && <span>• {e.api_base}</span>}
                    {e.azure_deployment && <span>• deployment: {e.azure_deployment}</span>}
                  </div>
                  {testResult[e.id] && (
                    <div className={`mt-2 text-xs px-2 py-1.5 rounded border ${
                      testResult[e.id].ok
                        ? "bg-green-50 text-green-800 border-green-200"
                        : "bg-red-50 text-red-800 border-red-200"
                    }`}>
                      {testResult[e.id].ok
                        ? `✓ Encoded test sentence — ${testResult[e.id].data.dimensions} dims`
                        : `✗ ${testResult[e.id].data.detail || "Test failed"}`}
                    </div>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => test(e.id)}
                    disabled={testingId === e.id}
                    className="text-xs px-3 py-1.5 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
                  >
                    {testingId === e.id ? "Testing..." : "Test"}
                  </button>
                  {!e.is_default && (
                    <button
                      onClick={() => setDefault(e.id)}
                      className="text-xs px-3 py-1.5 border border-indigo-300 text-indigo-600 rounded hover:bg-indigo-50"
                    >
                      Set Default
                    </button>
                  )}
                  <button
                    onClick={() => remove(e.id, e.name)}
                    className="text-xs px-3 py-1.5 text-red-500 hover:text-red-600"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
