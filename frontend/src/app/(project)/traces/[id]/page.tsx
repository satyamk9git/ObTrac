"use client";

import { useEffect, useState, Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import SpanTree from "@/components/SpanTree";
import MetricExplainModal from "@/components/MetricExplainModal";
import MultiSelectPicker, { PickerOption } from "@/components/ui/multi-select-picker";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { METRIC_SOURCE_LABELS } from "@/lib/metric-sources";

const LLM_ROLE_LABELS: Record<string, string> = {
  judge: "Judge",
  generator: "Generator",
  master: "Master",
  embedder: "Embedder",
  custom: "Custom",
};

const API = "/api/v1";

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
  const [evalJobId, setEvalJobId] = useState<string | null>(null);
  const [evalStatusMessage, setEvalStatusMessage] = useState("");
  // Annotations
  const [annotations, setAnnotations] = useState<any[]>([]);
  const [annoRating, setAnnoRating] = useState("");
  const [annoLabel, setAnnoLabel] = useState("");
  const [annoNotes, setAnnoNotes] = useState("");
  // Metric explanation modal
  const [explainMetric, setExplainMetric] = useState<{ metric: string; score: number; name?: string } | null>(null);
  // Ground truth datasets
  const [datasets, setDatasets] = useState<any[]>([]);
  const [selectedDataset, setSelectedDataset] = useState("");
  const [matchPreview, setMatchPreview] = useState<any>(null);
  const [matchingPreview, setMatchingPreview] = useState(false);
  const [gtSource, setGtSource] = useState<"manual" | "dataset">("manual");

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
      .then(async (results) => {
        // After main fetch, also load datasets for this trace's project
        const t = results[0];
        if (t?.project) {
          try {
            const dsRes = await fetch(`${API}/resources/ground-truth/datasets?project=${encodeURIComponent(t.project)}`);
            const ds = await dsRes.json();
            setDatasets(ds.datasets || []);
          } catch {}
        }
        return results;
      })
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

  // When dataset selected, semantically match against trace query
  useEffect(() => {
    if (!selectedDataset || !trace?.project || !trace?.query) {
      setMatchPreview(null);
      return;
    }
    setMatchingPreview(true);
    setMatchPreview(null);
    fetch(`${API}/resources/ground-truth/match-semantic?query=${encodeURIComponent(trace.query)}&dataset_name=${encodeURIComponent(selectedDataset)}&project=${encodeURIComponent(trace.project)}`)
      .then(r => r.json())
      .then(d => setMatchPreview(d))
      .catch(() => setMatchPreview(null))
      .finally(() => setMatchingPreview(false));
  }, [selectedDataset, trace?.project, trace?.query]);

  // Timer effect
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (evalRunning) {
      setEvalTimer(0);
      interval = setInterval(() => setEvalTimer((t) => t + 1), 1000);
    }
    return () => clearInterval(interval);
  }, [evalRunning]);

  // Resume in-flight job after page reload — find the most recent
  // queued/running job for THIS trace and start polling it.
  useEffect(() => {
    if (!traceId || evalJobId) return;
    fetch(`${API}/evaluation/jobs?trace_id=${traceId}&status=queued,running&limit=1`)
      .then((r) => r.json())
      .then((d) => {
        if (d.jobs && d.jobs.length > 0) {
          setEvalJobId(d.jobs[0].id);
          setEvalRunning(true);
          setEvalStatusMessage(d.jobs[0].progress_message || "Resuming...");
        }
      })
      .catch(() => {});
  }, [traceId]);

  // Poll the active job until it finishes
  useEffect(() => {
    if (!evalJobId) return;
    let cancelled = false;

    const tick = async () => {
      try {
        const r = await fetch(`${API}/evaluation/jobs/${evalJobId}`);
        if (!r.ok) {
          if (!cancelled) {
            setEvalRunning(false);
            setEvalJobId(null);
          }
          return;
        }
        const job = await r.json();
        if (cancelled) return;

        setEvalStatusMessage(job.progress_message || job.status);

        if (job.status === "completed") {
          setEvalResult(job.result);
          setEvalRunning(false);
          setEvalJobId(null);
          // Refresh trace to pick up new metrics
          const t = await fetch(`${API}/traces/${traceId}`).then((r) => r.json());
          if (!cancelled) setTrace(t);
        } else if (job.status === "failed" || job.status === "cancelled") {
          setEvalResult({ status: "error", error: job.error || job.status });
          setEvalRunning(false);
          setEvalJobId(null);
        }
      } catch {
        // Network blip — keep polling
      }
    };

    tick();
    const interval = setInterval(tick, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [evalJobId, traceId]);

  const runMultiLLMEval = async () => {
    setEvalRunning(true);
    setEvalResult(null);
    setEvalStatusMessage("Queuing evaluation...");
    try {
      const res = await fetch(`${API}/evaluation/run-multi-llm-async`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trace_id: traceId,
          metrics: selectedMetrics,
          judge_llm_config_ids: selectedLLMs,
          ground_truth: gtSource === "manual" ? (groundTruth || null) : null,
          dataset_name: gtSource === "dataset" ? (selectedDataset || null) : null,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setEvalResult({ status: "error", error: err.detail || `HTTP ${res.status}` });
        setEvalRunning(false);
        return;
      }
      const data = await res.json();
      // Hand off to the polling effect
      setEvalJobId(data.job_id);
      setEvalStatusMessage("Queued — you can navigate away, the eval will keep running.");
    } catch (e) {
      setEvalResult({ status: "error", error: String(e) });
      setEvalRunning(false);
    }
  };

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
                    <summary className="cursor-pointer text-sm font-medium text-gray-700 hover:text-primary flex items-center gap-2">
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
          <p className="text-xs text-gray-500 mb-2">Click any metric to see why and how to improve</p>
          <div className="grid grid-cols-3 gap-4">
            {Object.entries(trace.metrics).map(([name, value]) => {
              const mi = info[name];
              const v = value as number;
              const threshold = mi?.threshold || 0.7;
              return (
                <button
                  key={name}
                  onClick={() => setExplainMetric({ metric: name, score: v, name: mi?.name || name })}
                  className="metric-card text-left hover:border-indigo-400 hover:shadow-md transition-all cursor-pointer"
                >
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
                  <p className="text-[10px] text-indigo-500 mt-1">Click to analyze →</p>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Explain Modal */}
      {explainMetric && (
        <MetricExplainModal
          traceId={traceId}
          metric={explainMetric.metric}
          score={explainMetric.score}
          metricName={explainMetric.name}
          onClose={() => setExplainMetric(null)}
        />
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
          EVALUATION SECTION
          ======================================== */}
      <div className="bg-white rounded-lg border p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Run Evaluation
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
            <MultiSelectPicker
              options={llmConfigs.map((cfg): PickerOption => ({
                value: cfg.id,
                label: cfg.name,
                group: cfg.role,
                description: `${cfg.provider}/${cfg.model_id}`,
              }))}
              selected={selectedLLMs}
              onChange={setSelectedLLMs}
              placeholder="Select judge LLM(s)..."
              searchPlaceholder="Search LLM configs..."
              groupLabels={LLM_ROLE_LABELS}
              emptyText="No LLM configs found."
            />
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
          <MultiSelectPicker
            options={Object.entries(info).map(([key, mi]: [string, any]): PickerOption => ({
              value: key,
              label: mi.name,
              group: mi.source || "ragas",
              badge: mi.needs_ground_truth ? "GT" : undefined,
            }))}
            selected={selectedMetrics}
            onChange={setSelectedMetrics}
            placeholder="Select metrics..."
            searchPlaceholder="Search metrics..."
            groupLabels={METRIC_SOURCE_LABELS}
            emptyText="No metrics found."
          />
          <div className="text-xs text-gray-500 mt-1 flex items-center gap-1">
            <Badge variant="outline" className="text-[10px]">GT</Badge>
            = Requires ground truth
          </div>
        </div>

        {/* Step 3: Ground Truth */}
        {selectedMetrics.some((m) => info[m]?.needs_ground_truth) && (
          <div className="mb-5">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Step 3: Ground Truth <span className="text-purple-600">(required for selected metrics)</span>
            </label>

            {/* Toggle: Manual vs Dataset */}
            <Tabs value={gtSource} onValueChange={(v) => setGtSource(v as "manual" | "dataset")} className="mb-3">
              <TabsList>
                <TabsTrigger value="manual">Type Manually</TabsTrigger>
                <TabsTrigger value="dataset">Pick from Dataset ({datasets.length})</TabsTrigger>
              </TabsList>
            </Tabs>

            {gtSource === "manual" ? (
              <textarea
                value={groundTruth}
                onChange={(e) => setGroundTruth(e.target.value)}
                className="w-full text-sm border rounded-lg px-3 py-2 h-24"
                placeholder="Enter the expected correct answer..."
              />
            ) : (
              <div>
                {datasets.length === 0 ? (
                  <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm text-yellow-800">
                    No datasets in this project. Go to <a href={`/resources?project=${encodeURIComponent(trace.project)}`} className="underline font-medium">Resources</a> to upload or generate one.
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Dataset (semantic auto-match)</label>
                      <select
                        value={selectedDataset}
                        onChange={(e) => setSelectedDataset(e.target.value)}
                        className="w-full text-sm border rounded-lg px-3 py-2"
                      >
                        <option value="">-- Select a dataset --</option>
                        {datasets.map((ds: any) => (
                          <option key={ds.name} value={ds.name}>
                            {ds.name} ({ds.count} records)
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Semantic match preview */}
                    {selectedDataset && matchingPreview && (
                      <div className="text-xs text-gray-500 flex items-center gap-2">
                        <svg className="animate-spin w-3 h-3" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                        Finding best match using embeddings...
                      </div>
                    )}

                    {matchPreview && matchPreview.found && (
                      <div className="p-3 bg-green-50 rounded-lg border border-green-200 text-xs space-y-1">
                        <div className="flex items-center justify-between">
                          <p className="font-semibold text-green-800">Auto-matched ({matchPreview.match_type})</p>
                          <span className="text-[10px] bg-green-200 text-green-900 px-2 py-0.5 rounded">
                            similarity: {(matchPreview.score * 100).toFixed(1)}%
                          </span>
                        </div>
                        <p className="text-gray-600"><strong>Q:</strong> {matchPreview.match.question}</p>
                        <p className="text-gray-700"><strong>Ground truth:</strong> {matchPreview.match.ground_truth}</p>
                      </div>
                    )}

                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Run Button */}
        <div className="space-y-2">
          <button
            onClick={runMultiLLMEval}
            disabled={evalRunning || selectedMetrics.length === 0 || selectedLLMs.length === 0}
            className={`px-6 py-2.5 rounded-lg text-sm font-medium transition-all ${
              evalRunning
                ? "bg-yellow-500 text-white animate-pulse cursor-wait"
                : "bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
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
          {evalRunning && (
            <div className="text-xs bg-indigo-50 border border-indigo-200 text-indigo-800 rounded-lg px-3 py-2 flex items-start gap-2">
              <svg className="w-4 h-4 text-indigo-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p className="font-semibold">{evalStatusMessage || "Running in background..."}</p>
                <p className="text-indigo-600 mt-0.5">You can navigate away — the evaluation will keep running and the results will be saved when done.</p>
              </div>
            </div>
          )}
        </div>
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
