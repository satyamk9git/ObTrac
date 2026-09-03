"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

const API = "/api/v1";

const DEFAULT_MISSING_EVAL_METRICS = [
  "faithfulness",
  "answer_relevancy",
  "context_precision",
  "context_recall",
  "answer_correctness",
  "answer_similarity",
];

function DashboardContent() {
  const searchParams = useSearchParams();
  const project = searchParams.get("project") || "test-rag-app";
  const [summary, setSummary] = useState<any>(null);
  const [recentTraces, setRecentTraces] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const [bulkJob, setBulkJob] = useState<any>(null);
  const [bulkRunning, setBulkRunning] = useState(false);

  const loadData = () => {
    return Promise.all([
      fetch(`${API}/metrics/summary?project=${encodeURIComponent(project)}`).then((r) => r.json()),
      fetch(`${API}/traces?project=${encodeURIComponent(project)}&limit=10`).then((r) => r.json()),
    ]).then(([s, t]) => {
      setSummary(s);
      setRecentTraces(t.traces || []);
    });
  };

  useEffect(() => {
    loadData()
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  }, [project]);

  const runMissingEvals = async () => {
    setBulkRunning(true);
    setBulkJob({ status: "queued", progress_message: "Queueing..." });
    try {
      const res = await fetch(`${API}/evaluation/run-missing-async`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project, metrics: DEFAULT_MISSING_EVAL_METRICS, limit: 200 }),
      });
      const queued = await res.json();
      const jobId = queued.job_id;

      const poll = async () => {
        const r = await fetch(`${API}/evaluation/jobs/${jobId}`);
        const job = await r.json();
        setBulkJob(job);
        if (job.status === "completed" || job.status === "failed") {
          setBulkRunning(false);
          loadData(); // refresh scores on the page
          return;
        }
        setTimeout(poll, 2000);
      };
      poll();
    } catch (e) {
      setBulkRunning(false);
      setBulkJob({ status: "failed", error: "Network error" });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <svg className="animate-spin w-6 h-6 text-indigo-400" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>
    );
  }

  const hasData = summary && summary.total_traces > 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">{project}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={runMissingEvals}
            disabled={bulkRunning}
            className="btn-secondary text-sm disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-2"
            title="Evaluate only traces that are missing one or more metrics — already-scored traces and metrics are left untouched"
          >
            {bulkRunning && (
              <svg className="animate-spin w-3.5 h-3.5" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            )}
            {bulkRunning ? "Running Missing Evals..." : "Run Missing Evals"}
          </button>
          <Link href={`/traces?project=${encodeURIComponent(project)}`} className="btn-primary">
            View All Traces
          </Link>
        </div>
      </div>

      {bulkJob && (
        <div className={`mb-4 px-4 py-2.5 rounded-lg text-xs border ${
          bulkJob.status === "completed" ? "bg-green-50 border-green-200 text-green-700"
          : bulkJob.status === "failed" ? "bg-red-50 border-red-200 text-red-700"
          : "bg-indigo-50 border-indigo-200 text-indigo-700"
        }`}>
          {bulkJob.status === "completed" && bulkJob.result ? (
            <span>
              Done — checked {bulkJob.result.traces_checked} traces, {bulkJob.result.traces_with_missing_metrics} had gaps,
              {" "}<strong>{bulkJob.result.evaluated} evaluated</strong>
              {bulkJob.result.failed > 0 && `, ${bulkJob.result.failed} failed`}
              {bulkJob.result.skipped_no_applicable_metrics > 0 && `, ${bulkJob.result.skipped_no_applicable_metrics} skipped (no ground truth / context)`}.
            </span>
          ) : bulkJob.status === "failed" ? (
            <span>Bulk eval failed: {bulkJob.error || "unknown error"}</span>
          ) : (
            <span>{bulkJob.progress_message || "Working..."}</span>
          )}
        </div>
      )}

      {!hasData ? (
        <div className="card text-center py-16">
          <h3 className="text-lg font-semibold text-gray-300 mb-2">No data yet</h3>
          <p className="text-sm text-gray-500">Run your RAG pipeline to see metrics here.</p>
        </div>
      ) : (
        <>
          {/* Stats */}
          <div className="grid grid-cols-4 gap-4 mb-6">
            {[
              {
                label: "Total Traces",
                hint: "lifetime",
                value: summary.total_traces,
                color: "text-gray-900",
              },
              {
                label: "Avg Latency",
                hint: "across all traces",
                value: `${(summary.performance_stats?.avg_latency_ms || 0).toFixed(0)}ms`,
                color: "text-blue-600",
              },
              {
                label: "Total Cost",
                hint: "lifetime — see Budgets for windowed spend",
                value: `$${(summary.cost_stats?.total_cost_usd || 0).toFixed(4)}`,
                color: "text-green-600",
              },
              {
                label: "Total Tokens",
                hint: "lifetime",
                value: (summary.cost_stats?.total_tokens || 0).toLocaleString(),
                color: "text-purple-600",
              },
            ].map((stat) => (
              <div key={stat.label} className="card" title={stat.hint}>
                <div className="flex items-baseline justify-between">
                  <p className="text-xs text-gray-500">{stat.label}</p>
                  <p className="text-[9px] text-gray-400 italic">{stat.hint}</p>
                </div>
                <p className={`text-2xl font-bold mt-1 ${stat.color}`}>{stat.value}</p>
              </div>
            ))}
          </div>

          {/* Evaluation Metrics */}
          {Object.keys(summary.avg_metrics || {}).length > 0 && (
            <>
              <h2 className="text-base font-semibold text-gray-900 mb-3">Average Evaluation Metrics</h2>
              <div className="grid grid-cols-3 gap-4 mb-6">
                {Object.entries(summary.avg_metrics).map(([name, value]) => {
                  const v = value as number;
                  const color = v >= 0.8 ? "text-green-600" : v >= 0.6 ? "text-yellow-600" : "text-red-600";
                  const barColor = v >= 0.8 ? "from-green-500 to-emerald-400" : v >= 0.6 ? "from-yellow-500 to-amber-400" : "from-red-500 to-rose-400";
                  return (
                    <div key={name} className="card">
                      <div className="flex justify-between items-center mb-2">
                        <span className="text-sm text-gray-400 capitalize">{name.replace(/_/g, " ")}</span>
                        <span className={`text-xl font-bold ${color}`}>{(v * 100).toFixed(1)}%</span>
                      </div>
                      <div className="w-full bg-gray-100 rounded-full h-1.5">
                        <div className={`h-1.5 rounded-full bg-gradient-to-r ${barColor}`} style={{ width: `${Math.min(v * 100, 100)}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {/* Recent Traces */}
          <h2 className="text-base font-semibold text-gray-900 mb-3">Recent Traces (Last 10)</h2>
          <div className="card p-0 overflow-hidden">
            <table className="table-dark">
              <thead>
                <tr>
                  <th>Trace ID</th>
                  <th>Pipeline</th>
                  <th>User</th>
                  <th>Query</th>
                  <th>Status</th>
                  <th>Spans</th>
                  <th>Latency</th>
                  <th>Metrics</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {recentTraces.length === 0 ? (
                  <tr><td colSpan={8} className="text-center py-6 text-gray-400">No traces yet</td></tr>
                ) : recentTraces.map((t: any) => (
                  <tr key={t.trace_id}>
                    <td>
                      <Link href={`/traces/${t.trace_id}?project=${encodeURIComponent(project)}`} className="font-mono text-xs text-indigo-600 hover:text-indigo-500">
                        {t.trace_id.substring(0, 10)}...
                      </Link>
                    </td>
                    <td className="text-gray-600 text-xs">{t.name || "—"}</td>
                    <td>
                      {t.user ? (
                        <span className="badge badge-purple">{t.user}</span>
                      ) : <span className="text-gray-300 text-xs">—</span>}
                    </td>
                    <td className="text-gray-700 truncate max-w-[200px]">{t.query || "—"}</td>
                    <td>
                      <span className={`badge ${t.status === "success" ? "badge-success" : "badge-error"}`}>
                        {t.status}
                      </span>
                    </td>
                    <td className="text-gray-500">{t.num_spans}</td>
                    <td className="text-gray-500">{(t.total_latency_ms || 0).toFixed(0)}ms</td>
                    <td>
                      {t.eval_status === "pending" || t.eval_status === "running" ? (
                        <span className="flex items-center gap-1 text-xs text-indigo-500">
                          <svg className="animate-spin w-3 h-3" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                          Evaluating...
                        </span>
                      ) : Object.keys(t.metrics || {}).length > 0 ? (
                        <div className="flex gap-1 flex-wrap">
                          {Object.entries(t.metrics).slice(0, 2).map(([k, v]) => (
                            <span key={k} className={`text-[10px] px-1.5 py-0.5 rounded ${(v as number) >= 0.7 ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
                              {k.split("_")[0]}: {((v as number) * 100).toFixed(0)}%
                            </span>
                          ))}
                        </div>
                      ) : t.eval_status === "failed" || t.eval_status === "partial" ? (
                        <span className="text-[10px] text-yellow-500" title="Judge returned an invalid score for one or more metrics — known Azure OpenAI compatibility issue">Eval partial</span>
                      ) : (
                        <span className="text-[10px] text-gray-300">—</span>
                      )}
                    </td>
                    <td className="text-xs text-gray-400">{t.created_at ? new Date(t.created_at).toLocaleString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<div className="text-gray-500">Loading...</div>}>
      <DashboardContent />
    </Suspense>
  );
}
