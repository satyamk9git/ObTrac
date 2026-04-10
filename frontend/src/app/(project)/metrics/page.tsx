"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";

const API = "http://localhost:8100/api/v1";
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
                  {metricNames.map((m: string) => (
                    <th key={m} className="text-center">{(info[m]?.name || m).replace(/ /g, "\n").split("\n")[0]}</th>
                  ))}
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
                {Object.entries(t.all_metrics || {}).map(([k, v]) => (
                  <span key={k} className={`text-[10px] px-1.5 py-0.5 rounded ${getScoreBg(v as number)}`}>
                    {(info[k]?.name || k).split(" ")[0]}: {((v as number) * 100).toFixed(0)}%
                  </span>
                ))}
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
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Metric Correlation Matrix ({correlation?.sample_size || 0} samples)</h3>
          {(correlation?.metric_names?.length || 0) < 2 ? (
            <p className="text-sm text-gray-500">Need at least 2 metrics with 3+ traces to compute correlation.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr>
                    <th className="px-3 py-2" />
                    {correlation.metric_names.map((m: string) => (
                      <th key={m} className="px-3 py-2 text-center text-gray-600 font-medium">{(info[m]?.name || m).split(" ")[0]}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {correlation.metric_names.map((m1: string) => (
                    <tr key={m1} className="border-t border-gray-100">
                      <td className="px-3 py-2 font-medium text-gray-700">{(info[m1]?.name || m1).split(" ")[0]}</td>
                      {correlation.metric_names.map((m2: string) => {
                        const v = correlation.matrix?.[m1]?.[m2];
                        const bg = v == null ? "bg-gray-50" : v >= 0.7 ? "bg-green-100" : v >= 0.3 ? "bg-yellow-50" : v >= -0.3 ? "bg-gray-50" : "bg-red-100";
                        return (
                          <td key={m2} className={`px-3 py-2.5 text-center font-mono ${bg}`}>
                            {v != null ? (m1 === m2 ? <span className="text-gray-400">1.00</span> : v.toFixed(2)) : "—"}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-[10px] text-gray-400 mt-3">Green = strong positive | Yellow = weak | Red = negative correlation</p>
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
                    {metricNames.map((m: string) => <th key={m} className="text-center">{(info[m]?.name || m).split(" ")[0]}</th>)}
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
