"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

const API = "http://localhost:8100/api/v1";

function TracesContent() {
  const searchParams = useSearchParams();
  const project = searchParams.get("project") || "all";
  const [traces, setTraces] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");

  const fetchTraces = () => {
    setLoading(true);
    const params = new URLSearchParams({ project, limit: "50" });
    if (statusFilter) params.set("status", statusFilter);
    fetch(`${API}/traces?${params}`)
      .then((r) => r.json())
      .then((d) => { setTraces(d.traces || []); setTotal(d.total || 0); })
      .catch(() => setTraces([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchTraces(); }, [project, statusFilter]);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Traces</h1>
          <p className="text-sm text-gray-500">{total} traces {project !== "all" ? `in ${project}` : "across all projects"}</p>
        </div>
        <div className="flex gap-2">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="select-dark w-32">
            <option value="">All Status</option>
            <option value="success">Success</option>
            <option value="error">Error</option>
          </select>
          <button onClick={fetchTraces} className="btn-primary">Refresh</button>
        </div>
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="table-dark">
          <thead>
            <tr>
              <th>Trace ID</th>
              {project === "all" && <th>Project</th>}
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
            {loading ? (
              <tr><td colSpan={9} className="text-center py-10 text-gray-500">Loading...</td></tr>
            ) : traces.length === 0 ? (
              <tr><td colSpan={9} className="text-center py-10 text-gray-500">No traces found.</td></tr>
            ) : traces.map((t) => (
              <tr key={t.trace_id}>
                <td>
                  <Link href={`/traces/${t.trace_id}?project=${encodeURIComponent(t.project)}`} className="font-mono text-xs text-indigo-400 hover:text-indigo-300">
                    {t.trace_id.substring(0, 12)}
                  </Link>
                </td>
                {project === "all" && (
                  <td>
                    <span className={`badge ${t.project.includes("agent") ? "badge-purple" : "badge-info"}`}>
                      {t.project}
                    </span>
                  </td>
                )}
                <td className="text-gray-400">{t.name || "—"}</td>
                <td>{t.user ? <span className="badge badge-purple">{t.user}</span> : <span className="text-gray-300 text-xs">—</span>}</td>
                <td className="text-gray-700 truncate max-w-[200px]">{t.query || "—"}</td>
                <td><span className={`badge ${t.status === "success" ? "badge-success" : "badge-error"}`}>{t.status}</span></td>
                <td className="text-gray-400">{t.num_spans}</td>
                <td className="text-gray-400">{(t.total_latency_ms || 0).toFixed(0)}ms</td>
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
                  ) : t.eval_status === "failed" ? (
                    <span className="text-[10px] text-red-400">Eval failed</span>
                  ) : (
                    <span className="text-[10px] text-gray-300">—</span>
                  )}
                </td>
                <td className="text-xs text-gray-500">{t.created_at ? new Date(t.created_at).toLocaleString() : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function TracesPage() {
  return <Suspense fallback={<div className="text-gray-500">Loading...</div>}><TracesContent /></Suspense>;
}
