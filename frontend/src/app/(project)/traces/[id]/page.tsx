"use client";

import { useEffect, useState, Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import SpanTree from "@/components/SpanTree";

const API = "http://localhost:8100/api/v1";

function TraceDetailContent() {
  const params = useParams();
  const traceId = params.id as string;
  const [trace, setTrace] = useState<any>(null);
  const [metricsInfo, setMetricsInfo] = useState<any>(null);
  const [llmConfigs, setLlmConfigs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Eval state
  const [selectedLLMs, setSelectedLLMs] = useState<string[]>([]);
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([
    "faithfulness",
    "answer_relevancy",
  ]);
  const [groundTruth, setGroundTruth] = useState("");
  const [evalRunning, setEvalRunning] = useState(false);
  const [evalResult, setEvalResult] = useState<any>(null);
  const [evalTimer, setEvalTimer] = useState(0);
  // Annotations
  const [annotations, setAnnotations] = useState<any[]>([]);
  const [annoRating, setAnnoRating] = useState("");
  const [annoLabel, setAnnoLabel] = useState("");
  const [annoNotes, setAnnoNotes] = useState("");

  useEffect(() => {
    if (!traceId) return;
    setLoading(true);

    Promise.all([
      fetch(`${API}/traces/${traceId}`).then((r) => {
        if (!r.ok) throw new Error("Trace not found");
        return r.json();
      }),
      fetch(`${API}/evaluation/metrics-info`).then((r) => r.json()),
      fetch(`${API}/llm-configs`).then((r) => r.json()),
      fetch(`${API}/annotations/trace/${traceId}`).then((r) => r.json()).catch(() => ({ annotations: [] })),
    ])
      .then(([t, info, configs, annos]) => {
        setTrace(t);
        setMetricsInfo(info);
        setLlmConfigs(configs.configs || []);
        setAnnotations(annos.annotations || []);
        if (t?.ground_truth) setGroundTruth(t.ground_truth);
        if (configs.configs?.length > 0) {
          setSelectedLLMs(configs.configs.map((c: any) => c.id));
        }
      })
      .catch((err) => {
        console.error("Trace fetch error:", err);
        setTrace(null);
      })
      .finally(() => setLoading(false));
  }, [traceId]);

  // Timer effect
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (evalRunning) {
      setEvalTimer(0);
      interval = setInterval(() => setEvalTimer((t) => t + 1), 1000);
    }
    return () => clearInterval(interval);
  }, [evalRunning]);

  const runMultiLLMEval = async () => {
    setEvalRunning(true);
    setEvalResult(null);
    try {
      const res = await fetch(`${API}/evaluation/run-multi-llm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trace_id: traceId,
          metrics: selectedMetrics,
          judge_llm_config_ids: selectedLLMs,
          ground_truth: groundTruth || null,
        }),
      });
      const data = await res.json();
      setEvalResult(data);
      // Refresh trace
      const t = await fetch(`${API}/traces/${traceId}`).then((r) => r.json());
      setTrace(t);
    } catch (e) {
      setEvalResult({ status: "error", error: String(e) });
    } finally {
      setEvalRunning(false);
    }
  };

  const toggleMetric = (m: string) =>
    setSelectedMetrics((prev) =>
      prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]
    );

  const toggleLLM = (id: string) =>
    setSelectedLLMs((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );

  if (loading) return <p className="text-gray-500">Loading trace...</p>;
  if (!trace) return (
    <div>
      <p className="text-red-500">Trace not found</p>
      <p className="text-xs text-gray-400 mt-2">Debug: traceId = &quot;{traceId}&quot;, params = {JSON.stringify(params)}</p>
    </div>
  );

  const info = metricsInfo?.metrics || {};

  const getScoreColor = (v: number, threshold = 0.7) =>
    v >= 0.8 ? "text-green-600" : v >= threshold ? "text-yellow-600" : "text-red-600";

  const getScoreBg = (v: number, threshold = 0.7) =>
    v >= 0.8 ? "bg-green-100 text-green-800" : v >= threshold ? "bg-yellow-100 text-yellow-800" : "bg-red-100 text-red-800";

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Trace Detail</h1>
        <span className={`status-${trace.status}`}>{trace.status}</span>
        <span className="text-xs bg-gray-100 px-2 py-1 rounded">{trace.project}</span>
      </div>

      {/* Overview Cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="metric-card">
          <p className="text-xs text-gray-500">Trace ID</p>
          <p className="text-sm font-mono break-all">{trace.trace_id}</p>
        </div>
        <div className="metric-card">
          <p className="text-xs text-gray-500">Latency</p>
          <p className="text-2xl font-bold">{(trace.total_latency_ms || 0).toFixed(0)}ms</p>
        </div>
        <div className="metric-card">
          <p className="text-xs text-gray-500">Cost</p>
          <p className="text-2xl font-bold">${(trace.total_cost_usd || 0).toFixed(5)}</p>
        </div>
        <div className="metric-card">
          <p className="text-xs text-gray-500">Spans</p>
          <p className="text-2xl font-bold">{trace.spans.length}</p>
        </div>
      </div>

      {/* Query & Answer */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="bg-white rounded-lg border p-4">
          <h3 className="text-sm font-semibold text-gray-600 mb-2">Query</h3>
          <p className="text-sm text-gray-800">{trace.query || "N/A"}</p>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <h3 className="text-sm font-semibold text-gray-600 mb-2">Answer</h3>
          <p className="text-sm text-gray-800 whitespace-pre-wrap">{trace.answer || "N/A"}</p>
        </div>
      </div>

      {/* Annotation / Feedback */}
      <div className="card mb-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Feedback & Annotations</h3>
        <div className="flex items-center gap-3 mb-3">
          {/* Thumbs */}
          {[
            { val: "thumbs_up", icon: "👍", label: "Good" },
            { val: "thumbs_down", icon: "👎", label: "Bad" },
            { val: "neutral", icon: "😐", label: "Neutral" },
          ].map(r => (
            <button key={r.val} onClick={() => setAnnoRating(r.val)}
              className={`px-3 py-1.5 rounded-lg border text-sm transition-all ${annoRating === r.val ? "border-indigo-400 bg-indigo-50" : "border-gray-200 hover:bg-gray-50"}`}>
              {r.icon} {r.label}
            </button>
          ))}
          <div className="ml-4 flex gap-1">
            {["correct", "incorrect", "partial", "hallucination", "irrelevant"].map(l => (
              <button key={l} onClick={() => setAnnoLabel(l)}
                className={`text-[10px] px-2 py-1 rounded-full border transition-all ${annoLabel === l ? "border-indigo-400 bg-indigo-50 text-indigo-700" : "border-gray-200 text-gray-500 hover:bg-gray-50"}`}>
                {l}
              </button>
            ))}
          </div>
        </div>
        <div className="flex gap-2">
          <input type="text" value={annoNotes} onChange={e => setAnnoNotes(e.target.value)}
            placeholder="Add notes (optional)..." className="input-dark flex-1" />
          <button
            disabled={!annoRating && !annoLabel}
            onClick={async () => {
              const res = await fetch(`${API}/annotations`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ trace_id: traceId, rating: annoRating, label: annoLabel, notes: annoNotes, annotated_by: "satyam" }),
              });
              if (res.ok) {
                const a = await res.json();
                setAnnotations(prev => [a, ...prev]);
                setAnnoRating(""); setAnnoLabel(""); setAnnoNotes("");
              }
            }}
            className="btn-primary disabled:opacity-50 text-xs">
            Save
          </button>
        </div>
        {/* Existing annotations */}
        {annotations.length > 0 && (
          <div className="mt-3 space-y-2">
            {annotations.map((a: any) => (
              <div key={a.id} className="flex items-center gap-2 text-xs bg-gray-50 rounded-lg px-3 py-2">
                <span>{a.rating === "thumbs_up" ? "👍" : a.rating === "thumbs_down" ? "👎" : "😐"}</span>
                {a.label && <span className="badge badge-info">{a.label}</span>}
                <span className="text-gray-600 flex-1">{a.notes}</span>
                <span className="text-gray-400">{a.annotated_by}</span>
                <span className="text-gray-300">{a.created_at ? new Date(a.created_at).toLocaleString() : ""}</span>
                <button onClick={async () => {
                  await fetch(`${API}/annotations/${a.id}`, { method: "DELETE" });
                  setAnnotations(prev => prev.filter(x => x.id !== a.id));
                }} className="text-red-400 hover:text-red-600">x</button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Prompts — extracted from generation spans */}
      {trace.spans?.filter((s: any) => s.span_type === "generation").length > 0 && (
        <div className="bg-white rounded-lg border p-4 mb-6">
          <h3 className="text-sm font-semibold text-gray-600 mb-3">Prompts Sent to LLM</h3>
          <div className="space-y-3">
            {trace.spans
              .filter((s: any) => s.span_type === "generation")
              .map((span: any, i: number) => {
                // Extract prompt from span inputs
                const inputs = span.inputs || {};
                let prompt = "";
                // Check common patterns for where the prompt lives
                if (inputs.context && inputs.query) {
                  prompt = `[System/Template Prompt]\nContext:\n${inputs.context}\n\nQuestion: ${inputs.query}`;
                } else if (inputs.messages) {
                  try {
                    const msgs = typeof inputs.messages === "string" ? JSON.parse(inputs.messages) : inputs.messages;
                    prompt = Array.isArray(msgs)
                      ? msgs.map((m: any) => `[${m.role}]: ${m.content}`).join("\n\n")
                      : String(inputs.messages);
                  } catch {
                    prompt = String(inputs.messages);
                  }
                } else if (inputs.prompt) {
                  prompt = String(inputs.prompt);
                } else {
                  // Fallback: show all inputs
                  prompt = Object.entries(inputs)
                    .map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`)
                    .join("\n\n");
                }

                return (
                  <details key={span.span_id || i} open={i === 0}>
                    <summary className="cursor-pointer text-sm font-medium text-gray-700 hover:text-primary-600 flex items-center gap-2">
                      <span className="bg-purple-100 text-purple-700 px-2 py-0.5 rounded text-xs">
                        {span.name}
                      </span>
                      <span className="text-xs text-gray-400">
                        {(span.latency_ms || 0).toFixed(0)}ms
                        {span.model && ` | ${span.model}`}
                      </span>
                    </summary>
                    <pre className="mt-2 p-3 bg-gray-900 text-green-400 rounded-lg text-xs overflow-auto max-h-64 whitespace-pre-wrap font-mono">
                      {prompt || "No prompt data captured"}
                    </pre>
                    {/* Show raw output too */}
                    {span.outputs?.result && (
                      <details className="mt-1">
                        <summary className="text-xs text-gray-500 cursor-pointer">
                          LLM Response
                        </summary>
                        <pre className="mt-1 p-2 bg-gray-50 rounded text-xs overflow-auto max-h-32 whitespace-pre-wrap">
                          {typeof span.outputs.result === "string"
                            ? span.outputs.result.substring(0, 1000)
                            : JSON.stringify(span.outputs.result, null, 2).substring(0, 1000)}
                        </pre>
                      </details>
                    )}
                  </details>
                );
              })}
          </div>
        </div>
      )}

      {/* Context */}
      {trace.context && (
        <details className="bg-white rounded-lg border p-4 mb-6">
          <summary className="text-sm font-semibold text-gray-600 cursor-pointer">
            Retrieved Context
          </summary>
          <p className="text-sm text-gray-700 whitespace-pre-wrap max-h-48 overflow-auto mt-2">
            {trace.context}
          </p>
        </details>
      )}

      {/* Existing Metrics */}
      {trace.metrics && Object.keys(trace.metrics).length > 0 && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">Current Metrics</h2>
          <div className="grid grid-cols-3 gap-4">
            {Object.entries(trace.metrics).map(([name, value]) => {
              const mi = info[name];
              const v = value as number;
              const threshold = mi?.threshold || 0.7;
              return (
                <div key={name} className="metric-card">
                  <div className="flex justify-between items-start mb-1">
                    <div>
                      <h3 className="text-sm font-medium text-gray-700">{mi?.name || name}</h3>
                      {mi?.needs_ground_truth && (
                        <span className="text-xs bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">GT</span>
                      )}
                    </div>
                    <span className={`text-2xl font-bold ${getScoreColor(v, threshold)}`}>
                      {(v * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                    <div
                      className={`h-2 rounded-full ${v >= 0.8 ? "bg-green-500" : v >= threshold ? "bg-yellow-500" : "bg-red-500"}`}
                      style={{ width: `${Math.min(v * 100, 100)}%` }}
                    />
                  </div>
                  <p className="text-xs text-gray-500 mt-1">{mi?.description || ""}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Existing Suggestions */}
      {trace.suggestions?.length > 0 && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">Suggestions</h2>
          <div className="space-y-2">
            {trace.suggestions.map((s: string, i: number) => (
              <div key={i} className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
                {s}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ========================================
          RAGAS EVALUATION SECTION
          ======================================== */}
      <div className="bg-white rounded-lg border p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Run RAGAS Evaluation
        </h2>

        {/* Step 1: Select LLMs */}
        <div className="mb-5">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Step 1: Select Judge LLM(s)
          </label>
          {llmConfigs.length === 0 ? (
            <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-800">
              No LLMs configured.{" "}
              <a href="/llm-config" className="underline font-medium">
                Add an LLM first
              </a>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {llmConfigs.map((cfg) => (
                <button
                  key={cfg.id}
                  onClick={() => toggleLLM(cfg.id)}
                  className={`text-xs px-3 py-2 rounded-lg border transition-colors flex items-center gap-2 ${
                    selectedLLMs.includes(cfg.id)
                      ? "bg-primary-100 border-primary-400 text-primary-800"
                      : "bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100"
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full ${
                    cfg.role === "judge" ? "bg-purple-500"
                    : cfg.role === "generator" ? "bg-blue-500"
                    : "bg-gray-400"
                  }`} />
                  <div className="text-left">
                    <span className="font-medium">{cfg.name}</span>
                    <span className="text-gray-400 ml-1">
                      ({cfg.provider}/{cfg.model_id})
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
          <p className="text-xs text-gray-500 mt-1">
            Select multiple LLMs to compare evaluation results across judges.
          </p>
        </div>

        {/* Step 2: Select Metrics */}
        <div className="mb-5">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Step 2: Select Metrics
          </label>
          <div className="flex flex-wrap gap-2">
            {Object.entries(info).map(([key, mi]: [string, any]) => (
              <button
                key={key}
                onClick={() => toggleMetric(key)}
                className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                  selectedMetrics.includes(key)
                    ? "bg-primary-100 border-primary-400 text-primary-800"
                    : "bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100"
                }`}
              >
                {mi.name}
                {mi.needs_ground_truth && <span className="ml-1 text-purple-600">*</span>}
              </button>
            ))}
          </div>
          <p className="text-xs text-gray-500 mt-1">
            <span className="text-purple-600">*</span> = Requires ground truth
          </p>
        </div>

        {/* Step 3: Ground Truth */}
        {selectedMetrics.some((m) => info[m]?.needs_ground_truth) && (
          <div className="mb-5">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Step 3: Ground Truth <span className="text-purple-600">(required for selected metrics)</span>
            </label>
            <textarea
              value={groundTruth}
              onChange={(e) => setGroundTruth(e.target.value)}
              className="w-full text-sm border rounded-lg px-3 py-2 h-24"
              placeholder="Enter the expected correct answer, or it will be matched from Resources..."
            />
          </div>
        )}

        {/* Run Button */}
        <button
          onClick={runMultiLLMEval}
          disabled={evalRunning || selectedMetrics.length === 0 || selectedLLMs.length === 0}
          className={`px-6 py-2.5 rounded-lg text-sm font-medium transition-all ${
            evalRunning
              ? "bg-yellow-500 text-white animate-pulse cursor-wait"
              : "bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
          }`}
        >
          {evalRunning ? (
            <span className="flex items-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Running... {evalTimer}s
            </span>
          ) : (
            `Evaluate with ${selectedLLMs.length} LLM${selectedLLMs.length !== 1 ? "s" : ""} x ${selectedMetrics.length} Metric${selectedMetrics.length !== 1 ? "s" : ""}`
          )}
        </button>
      </div>

      {/* ========================================
          EVALUATION RESULTS
          ======================================== */}
      {evalResult && evalResult.status === "success" && (
        <div className="space-y-6 mb-6">
          {/* Per-LLM Comparison Table */}
          <div className="bg-white rounded-lg border p-6">
            <h2 className="text-lg font-semibold text-gray-800 mb-4">
              LLM Judge Comparison
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-gray-600">LLM Judge</th>
                    <th className="px-4 py-3 text-left text-gray-600">Provider</th>
                    {selectedMetrics.map((m) => (
                      <th key={m} className="px-4 py-3 text-left text-gray-600">
                        {info[m]?.name || m}
                      </th>
                    ))}
                    <th className="px-4 py-3 text-left text-gray-600">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {evalResult.llm_results?.map((r: any, i: number) => (
                    <tr key={i} className="border-t hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium">{r.llm_name}</td>
                      <td className="px-4 py-3">
                        <span className="text-xs bg-gray-100 px-2 py-0.5 rounded">
                          {r.llm_provider}
                        </span>
                      </td>
                      {selectedMetrics.map((m) => (
                        <td key={m} className="px-4 py-3">
                          {r.metrics?.[m] !== undefined ? (
                            <span className={`font-medium ${getScoreColor(r.metrics[m], info[m]?.threshold)}`}>
                              {(r.metrics[m] * 100).toFixed(1)}%
                            </span>
                          ) : (
                            <span className="text-gray-300">—</span>
                          )}
                        </td>
                      ))}
                      <td className="px-4 py-3">
                        <span className={r.status === "success" ? "status-success" : "status-error"}>
                          {r.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Per-Metric Detailed Recommendations */}
          {evalResult.recommendations?.metric_level && (
            <div className="bg-white rounded-lg border p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">
                Per-Metric Analysis & Recommendations
              </h2>
              <div className="space-y-4">
                {Object.entries(evalResult.recommendations.metric_level).map(
                  ([metricKey, data]: [string, any]) => {
                    const mi = info[metricKey];
                    return (
                      <div
                        key={metricKey}
                        className={`rounded-lg border p-4 ${
                          data.status === "good"
                            ? "border-green-200 bg-green-50"
                            : data.status === "warning"
                            ? "border-yellow-200 bg-yellow-50"
                            : data.status === "critical"
                            ? "border-red-200 bg-red-50"
                            : "border-gray-200"
                        }`}
                      >
                        <div className="flex justify-between items-start mb-2">
                          <div>
                            <h3 className="font-semibold text-gray-800">
                              {mi?.name || metricKey}
                            </h3>
                            <p className="text-xs text-gray-500">{mi?.category}</p>
                          </div>
                          <div className="text-right">
                            {data.avg_score !== null && (
                              <span className={`text-xl font-bold ${getScoreColor(data.avg_score, data.threshold)}`}>
                                {(data.avg_score * 100).toFixed(1)}%
                              </span>
                            )}
                            <p className="text-xs text-gray-500">
                              threshold: {((data.threshold || 0.7) * 100).toFixed(0)}%
                            </p>
                          </div>
                        </div>

                        <p className="text-sm mb-2">{data.message}</p>

                        {/* Per-LLM scores for this metric */}
                        {data.scores?.length > 1 && (
                          <div className="flex gap-2 mb-2">
                            {data.scores.map((s: any, i: number) => (
                              <span key={i} className={`text-xs px-2 py-1 rounded ${getScoreBg(s.score, data.threshold)}`}>
                                {s.llm}: {(s.score * 100).toFixed(1)}%
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Recommendations */}
                        {data.recommendations?.length > 0 && (
                          <div className="mt-2">
                            <p className="text-xs font-semibold text-gray-700 mb-1">How to improve:</p>
                            <ul className="text-xs text-gray-600 space-y-1 ml-3 list-disc">
                              {data.recommendations.map((rec: string, i: number) => (
                                <li key={i}>{rec}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    );
                  }
                )}
              </div>
            </div>
          )}

          {/* Trace-Level Recommendations */}
          {evalResult.recommendations?.trace_level?.length > 0 && (
            <div className="bg-white rounded-lg border p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">
                Trace-Level Diagnosis
                {evalResult.recommendations.overall_score !== null && (
                  <span className={`ml-3 text-base ${getScoreColor(evalResult.recommendations.overall_score)}`}>
                    Overall: {(evalResult.recommendations.overall_score * 100).toFixed(1)}%
                  </span>
                )}
              </h2>
              <div className="space-y-3">
                {evalResult.recommendations.trace_level.map((rec: string, i: number) => {
                  const isPriority = rec.startsWith("PRIORITY:");
                  const isDiagnosis = rec.startsWith("DIAGNOSIS:");
                  return (
                    <div
                      key={i}
                      className={`p-3 rounded-lg text-sm ${
                        isPriority
                          ? "bg-red-50 border border-red-200 text-red-800"
                          : isDiagnosis
                          ? "bg-orange-50 border border-orange-200 text-orange-800"
                          : "bg-blue-50 border border-blue-200 text-blue-800"
                      }`}
                    >
                      {isPriority && <span className="font-bold">PRIORITY: </span>}
                      {isDiagnosis && <span className="font-bold">DIAGNOSIS: </span>}
                      {rec.replace(/^(PRIORITY|DIAGNOSIS): /, "")}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Skipped Metrics */}
          {evalResult.skipped?.length > 0 && (
            <div className="bg-gray-50 rounded-lg border p-4">
              <h3 className="text-sm font-semibold text-gray-600 mb-2">Skipped Metrics</h3>
              {evalResult.skipped.map((s: any, i: number) => (
                <p key={i} className="text-xs text-gray-500">
                  {info[s.metric]?.name || s.metric}: {s.reason}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Eval error */}
      {evalResult && evalResult.status === "error" && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
          <p className="text-sm text-red-700">{evalResult.error}</p>
        </div>
      )}

      {/* Span Tree */}
      <h2 className="text-lg font-semibold text-gray-800 mb-3">Span Tree</h2>
      <SpanTree spans={trace.spans} />
    </div>
  );
}

export default function TraceDetailPage() {
  return (
    <Suspense fallback={<div className="text-gray-500">Loading trace...</div>}>
      <TraceDetailContent />
    </Suspense>
  );
}
