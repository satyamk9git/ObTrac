"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";

const API = "/api/v1";
const METRIC_COLORS: Record<string, string> = {
  faithfulness: "#6366f1",
  answer_relevancy: "#8b5cf6",
  context_precision: "#06b6d4",
  context_recall: "#10b981",
  answer_correctness: "#f59e0b",
  answer_similarity: "#ec4899",
};

function getScoreColor(v: number) {
  if (v >= 0.8) return "text-green-600";
  if (v >= 0.6) return "text-yellow-600";
  return "text-red-600";
}
function getScoreBg(v: number) {
  if (v >= 0.8) return "bg-green-50 text-green-700";
  if (v >= 0.6) return "bg-yellow-50 text-yellow-700";
  return "bg-red-50 text-red-700";
}

function MetricsContent() {
  const searchParams = useSearchParams();
  const project = searchParams.get("project") || "test-rag-app";
  const p = encodeURIComponent(project);

  const [summary, setSummary] = useState<any>(null);
  const [perQuery, setPerQuery] = useState<any>(null);
  const [worst, setWorst] = useState<any>(null);
  const [correlation, setCorrelation] = useState<any>(null);
  const [byModel, setByModel] = useState<any>(null);
  const [gtCoverage, setGtCoverage] = useState<any>(null);
  const [info, setInfo] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [worstMetric, setWorstMetric] = useState("faithfulness");
  const [tab, setTab] = useState("overview");

  // AI Insights (Overview tab)
  const [aiInsights, setAiInsights] = useState<any>(null);
  const [aiLoading, setAiLoading] = useState(false);

  const fetchAiInsights = async (refresh = false) => {
    setAiLoading(true);
    try {
      const r = await fetch(`${API}/explain/project-metrics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project, refresh }),
      });
      const data = await r.json();
      setAiInsights(data);
    } catch (e: any) {
      setAiInsights({ status: "error", message: e.message || "Network error" });
    } finally {
      setAiLoading(false);
    }
  };

  // AI Correlation Analysis (Correlation tab)
  const [corrInsights, setCorrInsights] = useState<any>(null);
  const [corrLoading, setCorrLoading] = useState(false);

  const fetchCorrInsights = async (refresh = false) => {
    setCorrLoading(true);
    try {
      const r = await fetch(`${API}/explain/correlation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project, refresh }),
      });
      const data = await r.json();
      setCorrInsights(data);
    } catch (e: any) {
      setCorrInsights({ status: "error", message: e.message || "Network error" });
    } finally {
      setCorrLoading(false);
    }
  };

  useEffect(() => {
    Promise.all([
      fetch(`${API}/metrics/summary?project=${p}`).then(r => r.json()),
      fetch(`${API}/metrics/per-query?project=${p}&limit=50`).then(r => r.json()),
      fetch(`${API}/metrics/worst?project=${p}&metric=${worstMetric}`).then(r => r.json()),
      fetch(`${API}/metrics/correlation?project=${p}`).then(r => r.json()),
      fetch(`${API}/metrics/by-model?project=${p}`).then(r => r.json()),
      fetch(`${API}/metrics/ground-truth-coverage?project=${p}`).then(r => r.json()),
      fetch(`${API}/evaluation/metrics-info`).then(r => r.json()),
    ])
      .then(([s, pq, w, c, m, gt, mi]) => {
        setSummary(s); setPerQuery(pq); setWorst(w); setCorrelation(c);
        setByModel(m); setGtCoverage(gt); setInfo(mi?.metrics || {});
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [project]);

  useEffect(() => {
    fetch(`${API}/metrics/worst?project=${p}&metric=${worstMetric}`)
      .then(r => r.json()).then(setWorst).catch(() => {});
  }, [worstMetric]);

  if (loading) return <div className="flex justify-center py-20"><div className="animate-spin w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full" /></div>;

  const metricNames = perQuery?.metric_names || Object.keys(summary?.avg_metrics || {});
  const hasMetrics = metricNames.length > 0;

  // Trend chart data — reverse so oldest is left
  const trendData = [...(summary?.metrics_over_time || [])].reverse().map((d: any, i: number) => ({
    idx: i + 1,
    time: d.timestamp ? new Date(d.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "",
    ...Object.fromEntries(metricNames.map((m: string) => [m, d.metrics?.[m] != null ? +(d.metrics[m] * 100).toFixed(1) : null])),
    latency: d.latency_ms || 0,
  }));

  const TABS = [
    { id: "overview", label: "Overview" },
    { id: "per-query", label: "Per-Query Breakdown" },
    { id: "worst", label: "Worst / Best Traces" },
    { id: "correlation", label: "Correlation" },
    { id: "model", label: "By Model" },
  ];

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">RAGAS Metrics</h1>
          <p className="text-sm text-gray-500">{summary?.total_traces || 0} evaluated traces in {project}</p>
        </div>
        <div className="flex gap-2">
          <a href={`${API}/metrics/export?project=${p}&format=csv`} className="btn-secondary text-xs" download>Export CSV</a>
          <a href={`${API}/metrics/export?project=${p}&format=json`} className="btn-secondary text-xs" target="_blank">Export JSON</a>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-gray-200 overflow-x-auto">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              tab === t.id ? "border-indigo-600 text-indigo-600" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ============ OVERVIEW ============ */}
      {tab === "overview" && (
        <div className="space-y-6">
          {/* Avg Metric Cards */}
          {hasMetrics ? (
            <div className="grid grid-cols-3 gap-4">
              {Object.entries(summary?.avg_metrics || {}).map(([name, value]) => {
                const v = value as number;
                const mi = info[name];
                return (
                  <div key={name} className="card">
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <h3 className="text-sm font-medium text-gray-700">{mi?.name || name}</h3>
                        <p className="text-[10px] text-gray-400">{mi?.category || ""}</p>
                      </div>
                      <span className={`text-2xl font-bold ${getScoreColor(v)}`}>{(v * 100).toFixed(1)}%</span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-2">
                      <div className={`h-2 rounded-full ${v >= 0.8 ? "bg-green-500" : v >= 0.6 ? "bg-yellow-500" : "bg-red-500"}`}
                        style={{ width: `${Math.min(v * 100, 100)}%` }} />
                    </div>
                    <p className="text-[10px] text-gray-400 mt-1">{mi?.description || ""}</p>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="card text-center py-10">
              <p className="text-gray-500">No metric data yet. Run RAGAS evaluation on your traces.</p>
            </div>
          )}

          {/* ============ AI INSIGHTS ============ */}
          {hasMetrics && (
            <div className={`card border-2 ${
              aiInsights?.insights?.health === "critical" ? "border-red-200 bg-red-50/30" :
              aiInsights?.insights?.health === "warning" ? "border-yellow-200 bg-yellow-50/30" :
              aiInsights?.insights?.health === "good" ? "border-green-200 bg-green-50/30" :
              "border-purple-200 bg-purple-50/30"
            }`}>
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-9 h-9 bg-gradient-to-br from-purple-500 to-indigo-600 rounded-lg flex items-center justify-center shrink-0">
                    <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="text-base font-semibold text-gray-900 flex items-center gap-2">
                      AI Insights
                      <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded">AI POWERED</span>
                    </h3>
                    <p className="text-[11px] text-gray-500">
                      Analyzes patterns across all traces and recommends the highest-leverage fix.
                      {aiInsights?.from_cache && ` Cached ${Math.floor(aiInsights.cache_age_seconds / 60)}m ago.`}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => fetchAiInsights(!!aiInsights)}
                  disabled={aiLoading}
                  className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-all ${
                    aiLoading
                      ? "bg-gray-200 text-gray-500 cursor-wait"
                      : aiInsights
                        ? "bg-white border border-purple-300 text-purple-700 hover:bg-purple-50"
                        : "bg-purple-600 text-white hover:bg-purple-700"
                  }`}
                >
                  {aiLoading ? "Analyzing..." : aiInsights ? "Re-analyze" : "Generate Analysis"}
                </button>
              </div>

              {/* Empty state */}
              {!aiInsights && !aiLoading && (
                <p className="text-sm text-gray-600 mt-2">
                  Click <strong>Generate Analysis</strong> to have your auto-eval LLM diagnose patterns across the {summary?.total_traces || 0} evaluated traces, identify root causes, and recommend the single highest-leverage fix.
                </p>
              )}

              {/* Loading */}
              {aiLoading && (
                <div className="flex items-center gap-3 text-sm text-purple-700">
                  <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Analyzing {summary?.total_traces || 0} traces with the auto-eval LLM...
                </div>
              )}

              {/* Errors */}
              {aiInsights?.status === "no_llm" && (
                <div className="text-sm text-yellow-800 bg-yellow-50 border border-yellow-200 rounded px-3 py-2 mt-2">
                  {aiInsights.message} — <Link href="/llm-config" className="underline">Open LLM Config</Link>
                </div>
              )}
              {aiInsights?.status === "no_data" && (
                <div className="text-sm text-gray-700 bg-gray-50 border border-gray-200 rounded px-3 py-2 mt-2">
                  {aiInsights.message}
                </div>
              )}
              {aiInsights?.status === "error" && (
                <div className="text-sm text-red-800 bg-red-50 border border-red-200 rounded px-3 py-2 mt-2">
                  {aiInsights.message}
                </div>
              )}

              {/* Result */}
              {aiInsights?.status === "ok" && aiInsights?.insights && (
                <div className="space-y-4 mt-3">
                  {/* Headline */}
                  {aiInsights.insights.headline && (
                    <div className={`rounded-lg px-4 py-3 border ${
                      aiInsights.insights.health === "critical" ? "bg-red-100 border-red-200 text-red-900" :
                      aiInsights.insights.health === "warning" ? "bg-yellow-100 border-yellow-200 text-yellow-900" :
                      "bg-green-100 border-green-200 text-green-900"
                    }`}>
                      <p className="text-sm font-semibold">{aiInsights.insights.headline}</p>
                    </div>
                  )}

                  {/* Top Issues */}
                  {Array.isArray(aiInsights.insights.top_issues) && aiInsights.insights.top_issues.length > 0 && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-700 uppercase tracking-wider mb-2">Top Issues</h4>
                      <div className="space-y-2">
                        {aiInsights.insights.top_issues.map((issue: any, i: number) => (
                          <div key={i} className="bg-white border border-gray-200 rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs font-mono text-indigo-700">{issue.metric}</span>
                              <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                                issue.severity === "high" ? "bg-red-100 text-red-700" :
                                issue.severity === "medium" ? "bg-yellow-100 text-yellow-700" :
                                "bg-gray-100 text-gray-600"
                              }`}>
                                {issue.severity}
                              </span>
                            </div>
                            <p className="text-sm text-gray-700">{issue.pattern}</p>
                            {issue.root_cause && (
                              <p className="text-xs text-gray-600 mt-1">
                                <strong>Root cause:</strong> {issue.root_cause}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Highest-Leverage Fix */}
                  {aiInsights.insights.highest_leverage_fix && (
                    <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                        <h4 className="text-xs font-bold text-indigo-900 uppercase tracking-wider">Highest-Leverage Fix</h4>
                      </div>
                      <p className="text-sm font-semibold text-gray-900">{aiInsights.insights.highest_leverage_fix.title}</p>
                      <p className="text-sm text-gray-700 mt-1">{aiInsights.insights.highest_leverage_fix.description}</p>
                      {aiInsights.insights.highest_leverage_fix.expected_impact && (
                        <p className="text-xs text-indigo-700 mt-2">
                          <strong>Expected impact:</strong> {aiInsights.insights.highest_leverage_fix.expected_impact}
                        </p>
                      )}
                      {aiInsights.insights.highest_leverage_fix.code_or_config_example && (
                        <pre className="mt-2 bg-gray-900 text-green-300 text-[11px] font-mono p-3 rounded overflow-x-auto whitespace-pre-wrap">
                          {aiInsights.insights.highest_leverage_fix.code_or_config_example}
                        </pre>
                      )}
                    </div>
                  )}

                  {/* What's Working */}
                  {aiInsights.insights.whats_working && (
                    <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                      <h4 className="text-xs font-bold text-green-900 uppercase tracking-wider mb-1">What's Working</h4>
                      <p className="text-sm text-green-800">{aiInsights.insights.whats_working}</p>
                    </div>
                  )}

                  {/* Next Steps */}
                  {Array.isArray(aiInsights.insights.next_steps) && aiInsights.insights.next_steps.length > 0 && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-700 uppercase tracking-wider mb-2">Next Steps</h4>
                      <ol className="space-y-1">
                        {aiInsights.insights.next_steps.map((step: string, i: number) => (
                          <li key={i} className="text-sm text-gray-700 flex gap-2">
                            <span className="font-bold text-purple-600">{i + 1}.</span>
                            <span>{step}</span>
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {/* Footer */}
                  <p className="text-[10px] text-gray-400 mt-2">
                    Analyzed by {aiInsights.analyzed_by} • {aiInsights.evaluated_traces} traces • {aiInsights.generated_at}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Stats Row */}
          <div className="grid grid-cols-4 gap-4">
            <div className="card">
              <p className="text-xs text-gray-500">Avg Latency</p>
              <p className="text-xl font-bold text-gray-900">{(summary?.performance_stats?.avg_latency_ms || 0).toFixed(0)}ms</p>
            </div>
            <div className="card">
              <p className="text-xs text-gray-500">Total Cost</p>
              <p className="text-xl font-bold text-gray-900">${(summary?.cost_stats?.total_cost_usd || 0).toFixed(4)}</p>
            </div>
            <div className="card">
              <p className="text-xs text-gray-500">Total Tokens</p>
              <p className="text-xl font-bold text-gray-900">{(summary?.cost_stats?.total_tokens || 0).toLocaleString()}</p>
            </div>
            <div className="card">
              <p className="text-xs text-gray-500">Ground Truth Coverage</p>
              <p className={`text-xl font-bold ${(gtCoverage?.coverage_pct || 0) > 50 ? "text-green-600" : "text-yellow-600"}`}>
                {gtCoverage?.coverage_pct || 0}%
              </p>
              <p className="text-[10px] text-gray-400">{gtCoverage?.traces_with_ground_truth || 0}/{gtCoverage?.total_traces || 0} traces</p>
            </div>
          </div>

          {/* Metric Trend Chart */}
          {trendData.length > 1 && (
            <div className="card">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">Metric Trends Over Time</h3>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="time" tick={{ fontSize: 10 }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} tickFormatter={(v: number) => `${v}%`} />
                  <Tooltip formatter={(v: number) => `${v}%`} />
                  <Legend />
                  {metricNames.map((m: string) => (
                    <Line key={m} type="monotone" dataKey={m} stroke={METRIC_COLORS[m] || "#888"}
                      strokeWidth={2} dot={{ r: 3 }} name={info[m]?.name || m} connectNulls />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Latency Trend */}
          {trendData.length > 1 && (
            <div className="card">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">Latency Per Trace</h3>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="time" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={(v: number) => `${v}ms`} />
                  <Tooltip formatter={(v: number) => `${v.toFixed(0)}ms`} />
                  <Bar dataKey="latency" fill="#6366f1" radius={[4, 4, 0, 0]} name="Latency" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* ============ PER-QUERY ============ */}
      {tab === "per-query" && (
        <div className="card p-0 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-700">All Traces with Metric Scores</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="table-dark">
              <thead>
                <tr>
                  <th>Query</th>
                  {metricNames.map((m: string) => {
                    const fullName = info[m]?.name || m.replace(/_/g, " ");
                    const words = fullName.trim().split(/\s+/);
                    // Multi-word names (e.g. "Answer Relevancy" / "Answer Correctness")
                    // share a first word — use the last word so columns stay distinct.
                    const shortLabel = words[words.length - 1];
                    return (
                      <th key={m} className="text-center" title={fullName}>{shortLabel}</th>
                    );
                  })}
                  <th className="text-center">Avg</th>
                  <th>Latency</th>
                  <th>GT</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {(perQuery?.rows || []).length === 0 ? (
                  <tr><td colSpan={metricNames.length + 5} className="text-center py-8 text-gray-400">No data</td></tr>
                ) : (perQuery?.rows || []).map((r: any) => (
                  <tr key={r.trace_id}>
                    <td className="max-w-[220px]">
                      <Link href={`/traces/${r.trace_id}?project=${p}`} className="text-indigo-600 hover:text-indigo-500 text-xs">
                        {(r.query || r.name || "—").substring(0, 55)}{(r.query || "").length > 55 ? "..." : ""}
                      </Link>
                    </td>
                    {metricNames.map((m: string) => {
                      const v = r.metrics?.[m];
                      return (
                        <td key={m} className="text-center">
                          {v != null ? (
                            <span className={`text-[11px] px-2 py-0.5 rounded ${getScoreBg(v)}`}>{(v * 100).toFixed(0)}%</span>
                          ) : <span className="text-gray-300">—</span>}
                        </td>
                      );
                    })}
                    <td className="text-center">
                      {r.avg_score != null ? (
                        <span className={`text-xs font-bold ${getScoreColor(r.avg_score)}`}>{(r.avg_score * 100).toFixed(0)}%</span>
                      ) : "—"}
                    </td>
                    <td className="text-gray-500 text-xs">{(r.latency_ms || 0).toFixed(0)}ms</td>
                    <td>{r.has_ground_truth ? <span className="text-green-600 text-[10px]">Yes</span> : <span className="text-gray-300 text-[10px]">No</span>}</td>
                    <td className="text-gray-400 text-[10px]">{r.created_at ? new Date(r.created_at).toLocaleString() : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ============ WORST/BEST TRACES ============ */}
      {tab === "worst" && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <select value={worstMetric} onChange={e => setWorstMetric(e.target.value)} className="select-dark w-52">
              {metricNames.map((m: string) => <option key={m} value={m}>{info[m]?.name || m}</option>)}
            </select>
          </div>

          <h3 className="text-sm font-semibold text-red-600">Bottom Performers</h3>
          {(worst?.worst || []).length === 0 ? (
            <p className="text-sm text-gray-400">No traces with this metric.</p>
          ) : (worst?.worst || []).map((t: any, i: number) => (
            <div key={t.trace_id} className="card border-l-4 border-l-red-400 flex items-start gap-4">
              <div className="text-xl font-bold text-red-200 w-8 text-center shrink-0">#{i + 1}</div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <Link href={`/traces/${t.trace_id}?project=${p}`} className="text-xs font-mono text-indigo-600 hover:text-indigo-500">{t.trace_id.substring(0, 12)}</Link>
                  <span className={`text-sm font-bold ${getScoreColor(t.score)}`}>{(t.score * 100).toFixed(1)}%</span>
                </div>
                <p className="text-sm text-gray-700 truncate">{t.query || "—"}</p>
                {t.suggestions?.[0] && <p className="text-xs text-orange-600 mt-1 truncate">{t.suggestions[0]}</p>}
              </div>
              <div className="flex gap-1 flex-wrap shrink-0">
                {Object.entries(t.all_metrics || {}).map(([k, v]) => {
                  const fullName = info[k]?.name || k.replace(/_/g, " ");
                  const words = fullName.trim().split(/\s+/);
                  const shortLabel = words[words.length - 1];
                  return (
                    <span key={k} title={fullName} className={`text-[10px] px-1.5 py-0.5 rounded ${getScoreBg(v as number)}`}>
                      {shortLabel}: {((v as number) * 100).toFixed(0)}%
                    </span>
                  );
                })}
              </div>
            </div>
          ))}

          {(worst?.best || []).length > 0 && (
            <>
              <h3 className="text-sm font-semibold text-green-600 mt-6">Top Performers</h3>
              {worst.best.slice(0, 5).map((t: any, i: number) => (
                <div key={t.trace_id} className="card border-l-4 border-l-green-400 flex items-center gap-4">
                  <div className="text-lg font-bold text-green-200 w-8 text-center">#{i + 1}</div>
                  <Link href={`/traces/${t.trace_id}?project=${p}`} className="text-xs font-mono text-indigo-600">{t.trace_id.substring(0, 12)}</Link>
                  <span className={`text-sm font-bold ${getScoreColor(t.score)}`}>{(t.score * 100).toFixed(1)}%</span>
                  <p className="text-sm text-gray-600 truncate flex-1">{t.query || "—"}</p>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {/* ============ CORRELATION ============ */}
      {tab === "correlation" && (
        <div className="card">
          <div className="mb-4">
            <h3 className="text-sm font-semibold text-gray-700">Metric Correlation Matrix</h3>
            <p className="text-xs text-gray-500 mt-1">
              Shows how metrics move together across {correlation?.sample_size || 0} traces.
              <strong className="text-green-700"> Green = move together</strong> ·
              <strong className="text-gray-500"> Gray = independent</strong> ·
              <strong className="text-red-700"> Red = move opposite</strong>
            </p>
          </div>
          {(correlation?.metric_names?.length || 0) < 2 ? (
            <p className="text-sm text-gray-500">Need at least 2 metrics with 3+ traces to compute correlation.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr>
                    <th className="px-3 py-3 sticky left-0 bg-white" />
                    {correlation.metric_names.map((m: string) => {
                      const label = info[m]?.name || m.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase());
                      return (
                        <th
                          key={m}
                          className="px-2 py-3 text-center text-[11px] text-gray-700 font-semibold border-b border-gray-200 align-bottom"
                          style={{ minWidth: 90 }}
                          title={m}
                        >
                          <div className="leading-tight">{label}</div>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {correlation.metric_names.map((m1: string) => {
                    const label = info[m1]?.name || m1.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase());
                    return (
                      <tr key={m1} className="border-t border-gray-100">
                        <td
                          className="px-3 py-2.5 font-semibold text-[11px] text-gray-700 sticky left-0 bg-white border-r border-gray-200 whitespace-nowrap"
                          title={m1}
                        >
                          {label}
                        </td>
                        {correlation.metric_names.map((m2: string) => {
                          const v = correlation.matrix?.[m1]?.[m2];
                          const isDiagonal = m1 === m2;
                          const bg = isDiagonal
                            ? "bg-indigo-50"
                            : v == null
                              ? "bg-gray-50"
                              : v >= 0.7
                                ? "bg-green-100"
                                : v >= 0.3
                                  ? "bg-green-50"
                                  : v >= -0.3
                                    ? "bg-gray-50"
                                    : v >= -0.7
                                      ? "bg-red-50"
                                      : "bg-red-100";
                          const tooltip = v == null
                            ? "No data"
                            : isDiagonal
                              ? "Self correlation (always 1.00)"
                              : v >= 0.7
                                ? `Strong positive — ${label} and ${info[m2]?.name || m2} usually move together`
                                : v >= 0.3
                                  ? `Weak positive — slight tendency to move together`
                                  : v >= -0.3
                                    ? `No relationship — these metrics move independently`
                                    : v >= -0.7
                                      ? `Weak negative — slight tendency to move opposite`
                                      : `Strong negative — usually move in opposite directions`;
                          return (
                            <td
                              key={m2}
                              className={`px-2 py-2.5 text-center font-mono text-[11px] border border-gray-100 ${bg}`}
                              title={tooltip}
                            >
                              {v != null ? (
                                isDiagonal ? (
                                  <span className="text-indigo-400">1.00</span>
                                ) : (
                                  <span className={
                                    v >= 0.7 ? "text-green-800 font-semibold" :
                                    v <= -0.7 ? "text-red-800 font-semibold" :
                                    "text-gray-700"
                                  }>
                                    {v.toFixed(2)}
                                  </span>
                                )
                              ) : "—"}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="mt-4 text-[11px] text-gray-600 bg-gray-50 border border-gray-200 rounded-lg p-3 space-y-1">
                <p><strong>How to read this:</strong></p>
                <p>• <strong>+1.00</strong> = perfect positive correlation (move together exactly)</p>
                <p>• <strong>+0.70 to +0.99</strong> = strong positive (highlighted green)</p>
                <p>• <strong>-0.30 to +0.30</strong> = no real relationship</p>
                <p>• <strong>-0.70 or lower</strong> = strong negative (highlighted red) — these metrics fight each other; investigate why</p>
                <p className="pt-1"><strong>Tip:</strong> hover over any cell to see what the number means in plain English.</p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ============ AI CORRELATION ANALYSIS ============ */}
      {tab === "correlation" && (correlation?.metric_names?.length || 0) >= 2 && (
        <div className={`card mt-4 border-2 ${
          corrInsights?.status === "ok" ? "border-purple-200 bg-purple-50/30" : "border-purple-200"
        }`}>
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 bg-gradient-to-br from-purple-500 to-indigo-600 rounded-lg flex items-center justify-center shrink-0">
                <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
              </div>
              <div>
                <h3 className="text-base font-semibold text-gray-900 flex items-center gap-2">
                  Analyze Metrics
                  <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded">AI POWERED</span>
                </h3>
                <p className="text-[11px] text-gray-500">
                  Explains the correlation matrix in plain English — what's expected, what's concerning, and what to investigate.
                  {corrInsights?.from_cache && ` Cached ${Math.floor(corrInsights.cache_age_seconds / 60)}m ago.`}
                </p>
              </div>
            </div>
            <button
              onClick={() => fetchCorrInsights(!!corrInsights)}
              disabled={corrLoading}
              className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-all ${
                corrLoading
                  ? "bg-gray-200 text-gray-500 cursor-wait"
                  : corrInsights
                    ? "bg-white border border-purple-300 text-purple-700 hover:bg-purple-50"
                    : "bg-purple-600 text-white hover:bg-purple-700"
              }`}
            >
              {corrLoading ? "Analyzing..." : corrInsights ? "Re-analyze" : "Analyze Metrics"}
            </button>
          </div>

          {/* Empty state */}
          {!corrInsights && !corrLoading && (
            <p className="text-sm text-gray-600">
              Click <strong>Analyze Metrics</strong> to have your auto-eval LLM interpret the correlation matrix and tell you which patterns are normal and which need investigation.
            </p>
          )}

          {/* Loading */}
          {corrLoading && (
            <div className="flex items-center gap-3 text-sm text-purple-700">
              <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Interpreting the correlation matrix...
            </div>
          )}

          {/* Error states */}
          {corrInsights?.status === "no_llm" && (
            <div className="text-sm text-yellow-800 bg-yellow-50 border border-yellow-200 rounded px-3 py-2">
              {corrInsights.message} — <Link href="/llm-config" className="underline">Open LLM Config</Link>
            </div>
          )}
          {corrInsights?.status === "insufficient_data" && (
            <div className="text-sm text-gray-700 bg-gray-50 border border-gray-200 rounded px-3 py-2">
              {corrInsights.message}
            </div>
          )}
          {corrInsights?.status === "error" && (
            <div className="text-sm text-red-800 bg-red-50 border border-red-200 rounded px-3 py-2">
              {corrInsights.message}
            </div>
          )}

          {/* Result */}
          {corrInsights?.status === "ok" && corrInsights?.insights && (
            <div className="space-y-4 mt-3">
              {/* Summary headline */}
              {corrInsights.insights.summary && (
                <div className="bg-white border border-purple-200 rounded-lg px-4 py-3">
                  <p className="text-sm font-semibold text-gray-900">{corrInsights.insights.summary}</p>
                </div>
              )}

              {/* Concerning patterns */}
              {Array.isArray(corrInsights.insights.concerning_patterns) && corrInsights.insights.concerning_patterns.length > 0 && (
                <div>
                  <h4 className="text-xs font-bold text-red-700 uppercase tracking-wider mb-2 flex items-center gap-1">
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    Concerning Patterns — Investigate These
                  </h4>
                  <div className="space-y-2">
                    {corrInsights.insights.concerning_patterns.map((p: any, i: number) => (
                      <div key={i} className="bg-red-50 border border-red-200 rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-mono text-red-800">{p.pair}</span>
                          {p.correlation != null && (
                            <span className="text-[10px] font-bold px-1.5 py-0.5 bg-red-200 text-red-900 rounded">
                              r = {Number(p.correlation).toFixed(2)}
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-gray-800">{p.interpretation}</p>
                        {p.likely_cause && (
                          <p className="text-xs text-gray-700 mt-1.5">
                            <strong>Likely cause:</strong> {p.likely_cause}
                          </p>
                        )}
                        {p.investigation_step && (
                          <p className="text-xs text-indigo-700 mt-1">
                            <strong>What to check:</strong> {p.investigation_step}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Expected patterns */}
              {Array.isArray(corrInsights.insights.expected_patterns) && corrInsights.insights.expected_patterns.length > 0 && (
                <div>
                  <h4 className="text-xs font-bold text-green-700 uppercase tracking-wider mb-2 flex items-center gap-1">
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    Expected Patterns — Working as Designed
                  </h4>
                  <div className="space-y-2">
                    {corrInsights.insights.expected_patterns.map((p: any, i: number) => (
                      <div key={i} className="bg-green-50 border border-green-200 rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-mono text-green-800">{p.pair}</span>
                          {p.correlation != null && (
                            <span className="text-[10px] font-bold px-1.5 py-0.5 bg-green-200 text-green-900 rounded">
                              r = +{Number(p.correlation).toFixed(2)}
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-gray-800">{p.interpretation}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Key insight */}
              {corrInsights.insights.key_insight && (
                <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-1">
                    <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    <h4 className="text-xs font-bold text-indigo-900 uppercase tracking-wider">Key Insight</h4>
                  </div>
                  <p className="text-sm text-gray-800">{corrInsights.insights.key_insight}</p>
                </div>
              )}

              {/* No action needed */}
              {corrInsights.insights.no_action_needed_if && (
                <div className="text-xs text-gray-500 italic border-l-2 border-gray-200 pl-3">
                  <strong>What's normal:</strong> {corrInsights.insights.no_action_needed_if}
                </div>
              )}

              {/* Footer */}
              <p className="text-[10px] text-gray-400">
                Analyzed by {corrInsights.analyzed_by} • {corrInsights.evaluated_traces} traces • {corrInsights.notable_pair_count} notable pair{corrInsights.notable_pair_count !== 1 ? "s" : ""} • {corrInsights.generated_at}
              </p>
            </div>
          )}
        </div>
      )}

      {/* ============ BY MODEL ============ */}
      {tab === "model" && (
        <div>
          {(byModel?.models || []).length === 0 ? (
            <div className="card text-center py-10"><p className="text-gray-500">No model data. Model info is captured from generation spans.</p></div>
          ) : (
            <div className="card p-0 overflow-hidden">
              <table className="table-dark">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Traces</th>
                    {metricNames.map((m: string) => {
                      const fullName = info[m]?.name || m.replace(/_/g, " ");
                      const words = fullName.trim().split(/\s+/);
                      const shortLabel = words[words.length - 1];
                      return <th key={m} className="text-center" title={fullName}>{shortLabel}</th>;
                    })}
                    <th>Avg Latency</th>
                    <th>Cost</th>
                    <th>Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {byModel.models.map((m: any) => (
                    <tr key={m.model}>
                      <td className="font-medium text-gray-900">{m.model}</td>
                      <td className="text-gray-600">{m.traces}</td>
                      {metricNames.map((metric: string) => {
                        const v = m.avg_metrics?.[metric];
                        return (
                          <td key={metric} className="text-center">
                            {v != null ? <span className={`text-[11px] px-2 py-0.5 rounded ${getScoreBg(v)}`}>{(v * 100).toFixed(0)}%</span> : <span className="text-gray-300">—</span>}
                          </td>
                        );
                      })}
                      <td className="text-gray-600">{m.avg_latency_ms.toFixed(0)}ms</td>
                      <td className="text-green-600">${m.total_cost_usd.toFixed(4)}</td>
                      <td className="text-gray-600">{m.total_tokens.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function MetricsPage() {
  return <Suspense fallback={<div className="text-gray-500">Loading...</div>}><MetricsContent /></Suspense>;
}
