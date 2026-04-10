"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";

const API = "http://localhost:8100/api/v1";

function ResourcesContent() {
  const searchParams = useSearchParams();
  const project = searchParams.get("project") || "default";

  const [tab, setTab] = useState("upload");
  const [datasets, setDatasets] = useState<any[]>([]);
  const [records, setRecords] = useState<any[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string>("");

  // Upload state
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<any>(null);

  // AI generator state
  const [genFile, setGenFile] = useState<File | null>(null);
  const [genDatasetName, setGenDatasetName] = useState("");
  const [genNumQuestions, setGenNumQuestions] = useState(10);
  const [genLLMs, setGenLLMs] = useState<any[]>([]);
  const [genLLMId, setGenLLMId] = useState("");
  const [generating, setGenerating] = useState(false);
  const [genResult, setGenResult] = useState<any>(null);
  const [genTimer, setGenTimer] = useState(0);

  const fetchDatasets = () => {
    fetch(`${API}/resources/ground-truth/datasets?project=${encodeURIComponent(project)}`)
      .then(r => r.json())
      .then(d => setDatasets(d.datasets || []))
      .catch(() => setDatasets([]));
  };

  const fetchRecords = (dataset: string) => {
    const params = new URLSearchParams({ project });
    if (dataset) params.set("dataset_name", dataset);
    fetch(`${API}/resources/ground-truth?${params}`)
      .then(r => r.json())
      .then(d => setRecords(d.records || []))
      .catch(() => setRecords([]));
  };

  useEffect(() => {
    fetchDatasets();
    // Fetch LLMs for generator
    fetch(`${API}/llm-configs`)
      .then(r => r.json())
      .then(d => {
        setGenLLMs(d.configs || []);
        const autoEval = d.configs?.find((c: any) => c.use_for_auto_eval);
        if (autoEval) setGenLLMId(autoEval.id);
      })
      .catch(() => {});
  }, [project]);

  useEffect(() => {
    if (selectedDataset) fetchRecords(selectedDataset);
  }, [selectedDataset]);

  // Timer for generator
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (generating) {
      setGenTimer(0);
      interval = setInterval(() => setGenTimer(t => t + 1), 1000);
    }
    return () => clearInterval(interval);
  }, [generating]);

  const handleUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setUploading(true);
    setUploadResult(null);
    const formData = new FormData(e.currentTarget);
    formData.set("project", project);
    try {
      const res = await fetch(`${API}/resources/ground-truth/upload`, { method: "POST", body: formData });
      const data = await res.json();
      setUploadResult(data);
      fetchDatasets();
    } catch (err) {
      setUploadResult({ status: "error", error: String(err) });
    } finally {
      setUploading(false);
    }
  };

  const handleGenerate = async (saveToDb: boolean) => {
    if (!genFile) {
      alert("Please select a file");
      return;
    }
    setGenerating(true);
    setGenResult(null);
    try {
      const formData = new FormData();
      formData.append("file", genFile);
      formData.append("project", project);
      formData.append("dataset_name", genDatasetName);
      formData.append("num_questions", String(genNumQuestions));
      formData.append("llm_config_id", genLLMId || "");
      formData.append("save", String(saveToDb));

      const res = await fetch(`${API}/resources/ground-truth/generate`, { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) {
        setGenResult({ error: data.detail || "Generation failed" });
      } else {
        setGenResult(data);
        if (saveToDb) fetchDatasets();
      }
    } catch (e) {
      setGenResult({ error: String(e) });
    } finally {
      setGenerating(false);
    }
  };

  const downloadAsCSV = (records: any[], filename: string) => {
    const header = "question,ground_truth,context";
    const rows = records.map(r => {
      const esc = (s: string) => `"${(s || "").replace(/"/g, '""')}"`;
      return `${esc(r.question)},${esc(r.ground_truth)},${esc(r.context || "")}`;
    });
    const blob = new Blob([header + "\n" + rows.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadAsJSON = (records: any[], filename: string) => {
    const blob = new Blob([JSON.stringify(records, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleDeleteDataset = async (name: string) => {
    if (!confirm(`Delete dataset '${name}'?`)) return;
    await fetch(`${API}/resources/ground-truth/dataset/${encodeURIComponent(name)}?project=${encodeURIComponent(project)}`, { method: "DELETE" });
    fetchDatasets();
    setRecords([]);
    setSelectedDataset("");
  };

  const TABS = [
    { id: "upload", label: "Upload" },
    { id: "generate", label: "AI Generator" },
    { id: "datasets", label: `Datasets (${datasets.length})` },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Resources</h1>
          <p className="text-sm text-gray-500">Ground truth datasets in {project}</p>
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

      {/* ============ UPLOAD ============ */}
      {tab === "upload" && (
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Upload Ground Truth File</h2>
          <p className="text-sm text-gray-500 mb-4">
            Upload a CSV or JSON file with columns: <code className="bg-gray-100 px-1 rounded">question</code>,{" "}
            <code className="bg-gray-100 px-1 rounded">ground_truth</code>,{" "}
            <code className="bg-gray-100 px-1 rounded">context</code> (optional)
          </p>

          <form onSubmit={handleUpload} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-600 mb-1">File (CSV/JSON)</label>
                <input type="file" name="file" accept=".csv,.json" required className="text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-600 mb-1">Dataset Name</label>
                <input type="text" name="dataset_name" placeholder="e.g., qa-v1" className="input-dark" />
              </div>
            </div>
            <button type="submit" disabled={uploading} className="btn-primary disabled:opacity-50">
              {uploading ? "Uploading..." : "Upload"}
            </button>
          </form>

          {uploadResult && (
            <div className={`mt-4 p-3 rounded-lg text-sm ${
              uploadResult.status === "uploaded" ? "bg-green-50 text-green-800 border border-green-200" : "bg-red-50 text-red-800 border border-red-200"
            }`}>
              {uploadResult.status === "uploaded"
                ? `Uploaded ${uploadResult.records_created} records to "${uploadResult.dataset_name}"`
                : `Error: ${uploadResult.error || "Upload failed"}`}
            </div>
          )}
        </div>
      )}

      {/* ============ AI GENERATOR ============ */}
      {tab === "generate" && (
        <div className="space-y-4">
          <div className="card">
            <h2 className="text-lg font-semibold text-gray-900 mb-2">AI Ground Truth Generator</h2>
            <p className="text-sm text-gray-500 mb-4">
              Upload any document (PDF/TXT) and let AI generate question-answer pairs to use as a golden dataset for evaluation.
            </p>

            <div className="space-y-3">
              <div>
                <label className="block text-xs text-gray-600 mb-1">Step 1: Upload Document (PDF/TXT)</label>
                <input type="file" accept=".pdf,.txt" onChange={e => setGenFile(e.target.files?.[0] || null)}
                  className="text-sm" />
                {genFile && <p className="text-[10px] text-gray-400 mt-1">Selected: {genFile.name} ({Math.round(genFile.size / 1024)} KB)</p>}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Step 2: Number of Q&A Pairs (10-1000)</label>
                  <div className="flex items-center gap-3">
                    <input type="range" min={10} max={1000} step={10} value={genNumQuestions}
                      onChange={e => setGenNumQuestions(parseInt(e.target.value))}
                      className="flex-1" />
                    <input type="number" min={10} max={1000} value={genNumQuestions}
                      onChange={e => setGenNumQuestions(parseInt(e.target.value) || 10)}
                      className="input-dark w-20 text-center" />
                  </div>
                  <p className="text-[10px] text-gray-400 mt-0.5">More questions = longer generation time</p>
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Step 3: Choose LLM</label>
                  <select value={genLLMId} onChange={e => setGenLLMId(e.target.value)} className="select-dark">
                    <option value="">Auto-select (auto-eval LLM)</option>
                    {genLLMs.map(c => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({c.provider}/{c.model_id}) {c.use_for_auto_eval ? "★" : ""}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs text-gray-600 mb-1">Dataset Name (when saving)</label>
                <input value={genDatasetName} onChange={e => setGenDatasetName(e.target.value)}
                  className="input-dark" placeholder="e.g., resume-golden-v1" />
              </div>

              <button onClick={() => handleGenerate(false)} disabled={generating || !genFile}
                className={`px-6 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  generating ? "bg-yellow-500 text-white animate-pulse" : "bg-indigo-600 text-white hover:bg-indigo-500"
                } disabled:opacity-50`}>
                {generating ? `AI is generating ${genNumQuestions} Q&A pairs... ${genTimer}s` : `Generate ${genNumQuestions} Q&A Pairs`}
              </button>
            </div>
          </div>

          {/* Generation result */}
          {genResult && genResult.error && (
            <div className="card border-l-4 border-l-red-400 text-sm text-red-700">
              <p className="font-semibold mb-1">Generation failed</p>
              <p className="text-xs">{genResult.error}</p>
            </div>
          )}

          {genResult && genResult.records && (
            <div className="card">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h3 className="text-sm font-semibold text-gray-700">
                    Generated {genResult.num_generated} Q&A pairs
                  </h3>
                  <p className="text-xs text-gray-500">Using {genResult.llm_used}</p>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => downloadAsCSV(genResult.records, `${genDatasetName || "golden-dataset"}.csv`)}
                    className="btn-secondary text-xs">Download CSV</button>
                  <button onClick={() => downloadAsJSON(genResult.records, `${genDatasetName || "golden-dataset"}.json`)}
                    className="btn-secondary text-xs">Download JSON</button>
                  <button onClick={() => handleGenerate(true)} className="btn-primary text-xs">
                    Save to Database
                  </button>
                </div>
              </div>

              <div className="max-h-96 overflow-auto">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left text-gray-500 w-8">#</th>
                      <th className="px-3 py-2 text-left text-gray-500">Question</th>
                      <th className="px-3 py-2 text-left text-gray-500">Ground Truth</th>
                      <th className="px-3 py-2 text-left text-gray-500">Context</th>
                    </tr>
                  </thead>
                  <tbody>
                    {genResult.records.map((r: any, i: number) => (
                      <tr key={i} className="border-t border-gray-100 hover:bg-gray-50">
                        <td className="px-3 py-2 text-gray-400">{i + 1}</td>
                        <td className="px-3 py-2 text-gray-800">{r.question}</td>
                        <td className="px-3 py-2 text-gray-700">{r.ground_truth}</td>
                        <td className="px-3 py-2 text-gray-500 text-[10px] max-w-xs truncate" title={r.context}>{r.context}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ============ DATASETS ============ */}
      {tab === "datasets" && (
        <div>
          {datasets.length === 0 ? (
            <div className="card text-center py-16">
              <h3 className="text-lg font-semibold text-gray-700 mb-2">No datasets yet</h3>
              <p className="text-sm text-gray-500">Upload a file or generate one with AI to get started.</p>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Datasets</h3>
                {datasets.map(ds => (
                  <button key={ds.name} onClick={() => setSelectedDataset(ds.name)}
                    className={`w-full text-left card p-3 transition-colors ${
                      selectedDataset === ds.name ? "border-indigo-400 bg-indigo-50" : ""
                    }`}>
                    <div className="flex justify-between items-center">
                      <div>
                        <p className="text-sm font-medium text-gray-900">{ds.name}</p>
                        <p className="text-[10px] text-gray-500">{ds.count} records</p>
                      </div>
                      <button onClick={(e) => { e.stopPropagation(); handleDeleteDataset(ds.name); }}
                        className="text-[10px] text-red-500 hover:text-red-600">Delete</button>
                    </div>
                  </button>
                ))}
              </div>

              <div className="col-span-2">
                {!selectedDataset ? (
                  <div className="card text-center py-16 text-gray-400">
                    Select a dataset to see records
                  </div>
                ) : (
                  <div className="card p-0 overflow-hidden">
                    <div className="px-4 py-3 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
                      <h3 className="text-sm font-semibold text-gray-700">{records.length} records in {selectedDataset}</h3>
                      <div className="flex gap-2">
                        <button onClick={() => downloadAsCSV(records, `${selectedDataset}.csv`)} className="text-xs btn-secondary">CSV</button>
                        <button onClick={() => downloadAsJSON(records, `${selectedDataset}.json`)} className="text-xs btn-secondary">JSON</button>
                      </div>
                    </div>
                    <div className="max-h-[600px] overflow-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-3 py-2 text-left text-gray-500">Question</th>
                            <th className="px-3 py-2 text-left text-gray-500">Ground Truth</th>
                            <th className="px-3 py-2 text-left text-gray-500">Context</th>
                          </tr>
                        </thead>
                        <tbody>
                          {records.map(r => (
                            <tr key={r.id} className="border-t border-gray-100 hover:bg-gray-50">
                              <td className="px-3 py-2 text-gray-700">{r.question}</td>
                              <td className="px-3 py-2 text-gray-700">{r.ground_truth}</td>
                              <td className="px-3 py-2 text-gray-500 text-[10px] max-w-xs truncate" title={r.context}>{r.context || "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ResourcesPage() {
  return <Suspense fallback={<div className="text-gray-500">Loading...</div>}><ResourcesContent /></Suspense>;
}
