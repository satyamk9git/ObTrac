"use client";

import { useEffect, useState } from "react";

const API = "/api/v1";

const PROVIDERS = [
  { value: "azure_openai", label: "Azure OpenAI" },
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic (Claude)" },
  { value: "gemini", label: "Google Gemini" },
  { value: "vertex_ai", label: "Google Vertex AI" },
  { value: "bedrock", label: "AWS Bedrock" },
  { value: "ollama", label: "Ollama (Local)" },
  { value: "groq", label: "Groq" },
  { value: "together", label: "Together AI" },
  { value: "huggingface", label: "Hugging Face" },
  { value: "vllm", label: "vLLM / Custom" },
];

const ROLES = [
  { value: "generator", label: "Generator" },
  { value: "judge", label: "Judge" },
  { value: "master", label: "Master" },
  { value: "embedder", label: "Embedder" },
  { value: "custom", label: "Custom" },
];

const defaultForm = {
  name: "",
  provider: "azure_openai",
  model_id: "",
  role: "generator",
  api_key: "",
  api_base: "",
  api_version: "2024-12-01-preview",
  azure_deployment: "",
  vertex_project: "",
  vertex_location: "",
  aws_region: "",
  temperature: 0.3,
  max_tokens: 2048,
  top_p: 1.0,
  cost_per_1k_prompt: 0,
  cost_per_1k_completion: 0,
  use_for_auto_eval: false,
};

export default function LLMConfigPage() {
  const [configs, setConfigs] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(defaultForm);
  const [testResult, setTestResult] = useState<any>(null);

  const fetchConfigs = () => {
    fetch(`${API}/llm-configs`)
      .then((r) => r.json())
      .then((data) => setConfigs(data.configs || []))
      .catch(() => setConfigs([]));
  };

  useEffect(() => {
    fetchConfigs();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const body = { ...form };
    Object.keys(body).forEach((k) => {
      if ((body as any)[k] === "") (body as any)[k] = null;
    });
    body.name = form.name;
    body.provider = form.provider;
    body.model_id = form.model_id;
    body.role = form.role;

    if (editingId) {
      // Update existing
      const res = await fetch(`${API}/llm-configs/${editingId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setShowForm(false);
        setEditingId(null);
        setForm(defaultForm);
        fetchConfigs();
      }
    } else {
      // Create new
      const res = await fetch(`${API}/llm-configs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setShowForm(false);
        setForm(defaultForm);
        fetchConfigs();
      }
    }
  };

  const handleEdit = (cfg: any) => {
    setEditingId(cfg.id);
    setForm({
      name: cfg.name || "",
      provider: cfg.provider || "azure_openai",
      model_id: cfg.model_id || "",
      role: cfg.role || "generator",
      api_key: "", // Don't prefill — user re-enters if they want to change
      api_base: cfg.api_base || "",
      api_version: cfg.api_version || "2024-12-01-preview",
      azure_deployment: cfg.azure_deployment || "",
      vertex_project: cfg.vertex_project || "",
      vertex_location: cfg.vertex_location || "",
      aws_region: cfg.aws_region || "",
      temperature: cfg.temperature ?? 0.3,
      max_tokens: cfg.max_tokens ?? 2048,
      top_p: cfg.top_p ?? 1.0,
      cost_per_1k_prompt: cfg.cost_per_1k_prompt ?? 0,
      cost_per_1k_completion: cfg.cost_per_1k_completion ?? 0,
      use_for_auto_eval: cfg.use_for_auto_eval ?? false,
    });
    setShowForm(true);
  };

  const handleCancelForm = () => {
    setShowForm(false);
    setEditingId(null);
    setForm(defaultForm);
  };

  const handleDelete = async (id: string) => {
    await fetch(`${API}/llm-configs/${id}`, { method: "DELETE" });
    fetchConfigs();
  };

  const handleTest = async (id: string) => {
    setTestResult({ id, status: "testing..." });
    const res = await fetch(`${API}/llm-configs/${id}/test`, { method: "POST" });
    const data = await res.json();
    setTestResult({ id, ...data });
  };

  const needsField = (field: string) => {
    const providerFields: Record<string, string[]> = {
      openai: ["api_key"],
      azure_openai: ["api_key", "api_base", "api_version", "azure_deployment"],
      anthropic: ["api_key"],
      gemini: ["api_key"],
      vertex_ai: ["vertex_project", "vertex_location"],
      bedrock: ["aws_region"],
      ollama: ["api_base"],
      groq: ["api_key"],
      together: ["api_key"],
      huggingface: ["api_key"],
      vllm: ["api_base"],
    };
    return (providerFields[form.provider] || []).includes(field);
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">LLM Configuration</h1>
        <button
          onClick={() => showForm ? handleCancelForm() : setShowForm(true)}
          className="bg-primary-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-primary-700"
        >
          {showForm ? "Cancel" : "+ Add LLM"}
        </button>
      </div>

      {/* Add/Edit LLM Form */}
      {showForm && editingId && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4 text-sm text-blue-800">
          Editing <strong>{form.name}</strong> — leave API Key blank to keep the existing key unchanged.
        </div>
      )}
      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="bg-white rounded-lg border p-6 mb-6 space-y-4"
        >
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Name
              </label>
              <input
                type="text"
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full text-sm border rounded-lg px-3 py-2"
                placeholder="e.g., my-gpt4o"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Provider
              </label>
              <select
                value={form.provider}
                onChange={(e) => setForm({ ...form, provider: e.target.value })}
                className="w-full text-sm border rounded-lg px-3 py-2"
              >
                {PROVIDERS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {form.provider === "azure_openai" ? "Model Name" : "Model ID"}
              </label>
              <input
                type="text"
                required
                value={form.model_id}
                onChange={(e) => setForm({ ...form, model_id: e.target.value })}
                className="w-full text-sm border rounded-lg px-3 py-2"
                placeholder={
                  form.provider === "azure_openai"
                    ? "e.g., gpt-4o (AZURE_OPENAI_MODEL_NAME)"
                    : "e.g., gpt-4o"
                }
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Role
              </label>
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                className="w-full text-sm border rounded-lg px-3 py-2"
              >
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>

            {needsField("api_key") && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {form.provider === "azure_openai"
                    ? "Subscription Key (API Key)"
                    : "API Key"}
                </label>
                <input
                  type="password"
                  value={form.api_key}
                  onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                  className="w-full text-sm border rounded-lg px-3 py-2"
                  placeholder={
                    form.provider === "azure_openai"
                      ? "AZURE_OPENAI_API_KEY"
                      : ""
                  }
                />
              </div>
            )}

            {needsField("api_base") && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {form.provider === "azure_openai"
                    ? "Endpoint"
                    : form.provider === "ollama"
                    ? "Ollama URL"
                    : "API Base URL"}
                </label>
                <input
                  type="text"
                  value={form.api_base}
                  onChange={(e) =>
                    setForm({ ...form, api_base: e.target.value })
                  }
                  className="w-full text-sm border rounded-lg px-3 py-2"
                  placeholder={
                    form.provider === "azure_openai"
                      ? "https://your-resource.openai.azure.com"
                      : form.provider === "ollama"
                      ? "http://localhost:11434"
                      : "https://..."
                  }
                />
              </div>
            )}
          </div>

          {/* Provider-specific fields */}
          <div className="grid grid-cols-3 gap-4">
            {needsField("api_version") && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  API Version
                </label>
                <input
                  type="text"
                  value={form.api_version}
                  onChange={(e) =>
                    setForm({ ...form, api_version: e.target.value })
                  }
                  className="w-full text-sm border rounded-lg px-3 py-2"
                  placeholder="2024-12-01-preview"
                />
              </div>
            )}
            {needsField("azure_deployment") && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Deployment Name
                </label>
                <input
                  type="text"
                  value={form.azure_deployment}
                  onChange={(e) =>
                    setForm({ ...form, azure_deployment: e.target.value })
                  }
                  className="w-full text-sm border rounded-lg px-3 py-2"
                  placeholder="AZURE_OPENAI_DEPLOYMENT"
                />
              </div>
            )}
            {needsField("vertex_project") && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  GCP Project ID
                </label>
                <input
                  type="text"
                  value={form.vertex_project}
                  onChange={(e) =>
                    setForm({ ...form, vertex_project: e.target.value })
                  }
                  className="w-full text-sm border rounded-lg px-3 py-2"
                />
              </div>
            )}
            {needsField("vertex_location") && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Vertex Location
                </label>
                <input
                  type="text"
                  value={form.vertex_location}
                  onChange={(e) =>
                    setForm({ ...form, vertex_location: e.target.value })
                  }
                  className="w-full text-sm border rounded-lg px-3 py-2"
                  placeholder="us-central1"
                />
              </div>
            )}
            {needsField("aws_region") && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  AWS Region
                </label>
                <input
                  type="text"
                  value={form.aws_region}
                  onChange={(e) =>
                    setForm({ ...form, aws_region: e.target.value })
                  }
                  className="w-full text-sm border rounded-lg px-3 py-2"
                  placeholder="us-east-1"
                />
              </div>
            )}
          </div>

          {/* Advanced params */}
          <details>
            <summary className="text-sm text-gray-600 cursor-pointer">
              Advanced Parameters
            </summary>
            <div className="grid grid-cols-3 gap-4 mt-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">
                  Temperature
                </label>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  value={form.temperature}
                  onChange={(e) =>
                    setForm({ ...form, temperature: parseFloat(e.target.value) })
                  }
                  className="w-full text-sm border rounded-lg px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">
                  Max Tokens
                </label>
                <input
                  type="number"
                  value={form.max_tokens}
                  onChange={(e) =>
                    setForm({ ...form, max_tokens: parseInt(e.target.value) })
                  }
                  className="w-full text-sm border rounded-lg px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">
                  Top P
                </label>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  value={form.top_p}
                  onChange={(e) =>
                    setForm({ ...form, top_p: parseFloat(e.target.value) })
                  }
                  className="w-full text-sm border rounded-lg px-3 py-2"
                />
              </div>
            </div>
          </details>

          {/* Cost Configuration */}
          <details open>
            <summary className="text-sm font-medium text-gray-700 cursor-pointer">
              Cost Configuration (USD per 1K tokens)
            </summary>
            <div className="grid grid-cols-2 gap-4 mt-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">
                  Cost per 1K Prompt Tokens ($)
                </label>
                <input
                  type="number"
                  step="0.0001"
                  min="0"
                  value={(form as any).cost_per_1k_prompt || 0}
                  onChange={(e) =>
                    setForm({ ...form, cost_per_1k_prompt: parseFloat(e.target.value) || 0 } as any)
                  }
                  className="w-full text-sm border rounded-lg px-3 py-2"
                  placeholder="e.g., 0.0025 for GPT-4o"
                />
                <p className="text-xs text-gray-400 mt-0.5">GPT-4o: $0.0025 | GPT-4o-mini: $0.00015</p>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">
                  Cost per 1K Completion Tokens ($)
                </label>
                <input
                  type="number"
                  step="0.0001"
                  min="0"
                  value={(form as any).cost_per_1k_completion || 0}
                  onChange={(e) =>
                    setForm({ ...form, cost_per_1k_completion: parseFloat(e.target.value) || 0 } as any)
                  }
                  className="w-full text-sm border rounded-lg px-3 py-2"
                  placeholder="e.g., 0.01 for GPT-4o"
                />
                <p className="text-xs text-gray-400 mt-0.5">GPT-4o: $0.01 | GPT-4o-mini: $0.0006</p>
              </div>
            </div>
          </details>

          {/* Auto-Eval Toggle */}
          <div className="flex items-center gap-3 p-3 bg-indigo-50 rounded-lg border border-indigo-200">
            <input
              type="checkbox"
              id="auto_eval"
              checked={(form as any).use_for_auto_eval || false}
              onChange={(e) => setForm({ ...form, use_for_auto_eval: e.target.checked } as any)}
              className="w-4 h-4 text-indigo-600 rounded"
            />
            <label htmlFor="auto_eval" className="text-sm text-gray-700">
              <span className="font-medium">Use for Auto-Evaluation</span>
              <p className="text-xs text-gray-500 mt-0.5">
                When enabled, this LLM will be used as the judge for automatic evaluation.
                Only one LLM can have this enabled — enabling here will disable on others.
              </p>
            </label>
          </div>

          <button
            type="submit"
            className="bg-primary-600 text-white px-6 py-2 rounded-lg text-sm hover:bg-primary-700"
          >
            {editingId ? "Update LLM Configuration" : "Save LLM Configuration"}
          </button>
        </form>
      )}

      {/* Configs List */}
      <div className="bg-white rounded-lg border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-gray-600">Name</th>
              <th className="px-4 py-3 text-left text-gray-600">Provider</th>
              <th className="px-4 py-3 text-left text-gray-600">Model</th>
              <th className="px-4 py-3 text-left text-gray-600">Role</th>
              <th className="px-4 py-3 text-left text-gray-600">API Key</th>
              <th className="px-4 py-3 text-left text-gray-600">Active</th>
              <th className="px-4 py-3 text-left text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            {configs.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                  No LLM configurations yet. Click &quot;+ Add LLM&quot; to get started.
                </td>
              </tr>
            ) : (
              configs.map((cfg) => (
                <tr key={cfg.id} className="border-t hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{cfg.name}</td>
                  <td className="px-4 py-3">
                    <span className="bg-gray-100 px-2 py-0.5 rounded text-xs">
                      {cfg.provider}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{cfg.model_id}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium ${
                        cfg.role === "judge"
                          ? "bg-purple-100 text-purple-800"
                          : cfg.role === "generator"
                          ? "bg-blue-100 text-blue-800"
                          : cfg.role === "embedder"
                          ? "bg-green-100 text-green-800"
                          : "bg-gray-100 text-gray-800"
                      }`}
                    >
                      {cfg.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {cfg.api_key_masked || "N/A"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      {cfg.is_active ? (
                        <span className="text-green-600 text-xs">Active</span>
                      ) : (
                        <span className="text-gray-400 text-xs">Inactive</span>
                      )}
                      {cfg.use_for_auto_eval && (
                        <span className="badge badge-info text-[9px]">Auto-Eval</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 flex gap-2">
                    <button
                      onClick={() => handleEdit(cfg)}
                      className="text-xs bg-blue-50 text-blue-600 px-2 py-1 rounded hover:bg-blue-100"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleTest(cfg.id)}
                      className="text-xs bg-gray-100 px-2 py-1 rounded hover:bg-gray-200"
                    >
                      Test
                    </button>
                    <button
                      onClick={() => handleDelete(cfg.id)}
                      className="text-xs text-red-600 hover:text-red-800"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Test Result */}
      {testResult && (
        <div
          className={`mt-4 p-4 rounded-lg border ${
            testResult.status === "success"
              ? "bg-green-50 border-green-200"
              : testResult.status === "testing..."
              ? "bg-yellow-50 border-yellow-200"
              : "bg-red-50 border-red-200"
          }`}
        >
          <p className="text-sm font-medium">
            Connection Test: {testResult.status}
          </p>
          {testResult.response && (
            <p className="text-xs text-gray-600 mt-1">
              Response: {testResult.response}
            </p>
          )}
          {testResult.error && (
            <p className="text-xs text-red-600 mt-1">
              Error: {testResult.error}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
