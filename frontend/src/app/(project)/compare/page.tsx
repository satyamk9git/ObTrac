"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

const API = "http://localhost:8100/api/v1";

function CompareContent() {
  const searchParams = useSearchParams();
  const project = searchParams.get("project") || "all";
  const [traces, setTraces] = useState<any[]>([]);
  const [traceA, setTraceA] = useState("");
  const [traceB, setTraceB] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch(`${API}/traces?project=${encodeURIComponent(project)}&limit=50`)
      .then(r => r.json())
      .then(d => setTraces(d.traces || []))
      .catch(() => {});
  }, [project]);

  const compare = async () => {
    if (!traceA || !traceB) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/compare?trace_a=${traceA}&trace_b=${traceB}`);
      setResult(await res.json());
    } catch { setResult(null); }
    finally { setLoading(false); }
  };

  const getWinnerBg = (winner: string) =>
    winner === "a" ? "bg-blue-50" : winner === "b" ? "bg-green-50" : "";

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Trace Comparison</h1>

      {/* Selector */}
      <div className="card mb-6">
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Trace A</label>
            <select value={traceA} onChange={e => setTraceA(e.target.value)} className="select-dark">
              <option value="">Select trace...</option>
              {traces.map(t => (
                <option key={t.trace_id} value={t.trace_id}>
                  {t.trace_id.substring(0, 8)} — {(t.query || t.name || "—").substring(0, 50)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Trace B</label>
            <select value={traceB} onChange={e => setTraceB(e.target.value)} className="select-dark">
              <option value="">Select trace...</option>
              {traces.map(t => (
                <option key={t.trace_id} value={t.trace_id}>
                  {t.trace_id.substring(0, 8)} — {(t.query || t.name || "—").substring(0, 50)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <button onClick={compare} disabled={!traceA || !traceB || traceA === traceB || loading}
          className="btn-primary disabled:opacity-50">
          {loading ? "Comparing..." : "Compare Traces"}
        </button>
      </div>

      {/* Results */}
      {result && (
        <div className="space-y-6 animate-fade-in">
          {/* Header */}
          <div className="grid grid-cols-2 gap-4">
            <div className="card border-l-4 border-l-blue-400">
              <p className="text-xs text-blue-600 font-semibold mb-1">TRACE A</p>
              <p className="text-xs font-mono text-gray-500">{result.trace_a.trace_id.substring(0, 16)}</p>
              <p className="text-sm text-gray-700 mt-1">{result.trace_a.name}</p>
              {result.trace_a.user && <span className="badge badge-purple text-[10px]">{result.trace_a.user}</span>}
            </div>
            <div className="card border-l-4 border-l-green-400">
              <p className="text-xs text-green-600 font-semibold mb-1">TRACE B</p>
              <p className="text-xs font-mono text-gray-500">{result.trace_b.trace_id.substring(0, 16)}</p>
              <p className="text-sm text-gray-700 mt-1">{result.trace_b.name}</p>
              {result.trace_b.user && <span className="badge badge-purple text-[10px]">{result.trace_b.user}</span>}
            </div>
          </div>

          {/* Query & Answer Comparison */}
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Query & Answer</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-gray-500 mb-1">Query</p>
                <p className="text-sm text-gray-800 bg-blue-50 p-2 rounded">{result.trace_a.query || "—"}</p>
                <p className="text-xs text-gray-500 mt-2 mb-1">Answer</p>
                <p className="text-sm text-gray-700 bg-blue-50 p-2 rounded max-h-40 overflow-auto whitespace-pre-wrap">{result.trace_a.answer || "—"}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-1">Query</p>
                <p className="text-sm text-gray-800 bg-green-50 p-2 rounded">{result.trace_b.query || "—"}</p>
                <p className="text-xs text-gray-500 mt-2 mb-1">Answer</p>
                <p className="text-sm text-gray-700 bg-green-50 p-2 rounded max-h-40 overflow-auto whitespace-pre-wrap">{result.trace_b.answer || "—"}</p>
              </div>
            </div>
            <div className="flex gap-2 mt-2">
              {result.diffs.same_query && <span className="badge badge-success">Same Query</span>}
              {result.diffs.same_answer && <span className="badge badge-success">Same Answer</span>}
              {!result.diffs.same_answer && <span className="badge badge-warning">Different Answers</span>}
            </div>
          </div>

          {/* Metrics Comparison */}
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Metrics</h3>
            <table className="table-dark">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th className="text-center text-blue-600">Trace A</th>
                  <th className="text-center text-green-600">Trace B</th>
                  <th className="text-center">Delta</th>
                  <th className="text-center">Winner</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(result.diffs.metrics).map(([metric, d]: [string, any]) => (
                  <tr key={metric}>
                    <td className="font-medium text-gray-700 capitalize">{metric.replace(/_/g, " ")}</td>
                    <td className={`text-center font-mono ${d.winner === "a" ? "font-bold text-blue-600" : "text-gray-600"}`}>
                      {d.a != null ? `${(d.a * 100).toFixed(1)}%` : "—"}
                    </td>
                    <td className={`text-center font-mono ${d.winner === "b" ? "font-bold text-green-600" : "text-gray-600"}`}>
                      {d.b != null ? `${(d.b * 100).toFixed(1)}%` : "—"}
                    </td>
                    <td className="text-center">
                      {d.delta != null ? (
                        <span className={d.delta > 0 ? "text-green-600" : d.delta < 0 ? "text-red-600" : "text-gray-400"}>
                          {d.delta > 0 ? "+" : ""}{(d.delta * 100).toFixed(1)}%
                        </span>
                      ) : "—"}
                    </td>
                    <td className="text-center">
                      {d.winner === "a" ? <span className="badge bg-blue-50 text-blue-600">A</span> :
                       d.winner === "b" ? <span className="badge bg-green-50 text-green-600">B</span> :
                       <span className="badge bg-gray-50 text-gray-400">Tie</span>}
                    </td>
                  </tr>
                ))}
                {/* Performance rows */}
                <tr className="border-t-2 border-gray-200">
                  <td className="font-medium text-gray-700">Latency</td>
                  <td className={`text-center font-mono ${result.diffs.latency.winner === "a" ? "font-bold text-blue-600" : "text-gray-600"}`}>
                    {result.diffs.latency.a.toFixed(0)}ms
                  </td>
                  <td className={`text-center font-mono ${result.diffs.latency.winner === "b" ? "font-bold text-green-600" : "text-gray-600"}`}>
                    {result.diffs.latency.b.toFixed(0)}ms
                  </td>
                  <td className="text-center">
                    <span className={result.diffs.latency.delta < 0 ? "text-green-600" : "text-red-600"}>
                      {result.diffs.latency.delta > 0 ? "+" : ""}{result.diffs.latency.delta.toFixed(0)}ms
                    </span>
                  </td>
                  <td className="text-center">
                    <span className={`badge ${result.diffs.latency.winner === "a" ? "bg-blue-50 text-blue-600" : "bg-green-50 text-green-600"}`}>
                      {result.diffs.latency.winner.toUpperCase()} (faster)
                    </span>
                  </td>
                </tr>
                <tr>
                  <td className="font-medium text-gray-700">Cost</td>
                  <td className="text-center font-mono text-gray-600">${result.diffs.cost.a.toFixed(5)}</td>
                  <td className="text-center font-mono text-gray-600">${result.diffs.cost.b.toFixed(5)}</td>
                  <td className="text-center">
                    <span className={result.diffs.cost.delta < 0 ? "text-green-600" : "text-red-600"}>
                      {result.diffs.cost.delta > 0 ? "+" : ""}${result.diffs.cost.delta.toFixed(5)}
                    </span>
                  </td>
                  <td className="text-center">
                    <span className={`badge ${result.diffs.cost.winner === "a" ? "bg-blue-50 text-blue-600" : "bg-green-50 text-green-600"}`}>
                      {result.diffs.cost.winner.toUpperCase()} (cheaper)
                    </span>
                  </td>
                </tr>
                <tr>
                  <td className="font-medium text-gray-700">Spans</td>
                  <td className="text-center text-gray-600">{result.diffs.spans.a}</td>
                  <td className="text-center text-gray-600">{result.diffs.spans.b}</td>
                  <td colSpan={2} />
                </tr>
              </tbody>
            </table>
          </div>

          {/* Span Comparison */}
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Spans</h3>
            <div className="grid grid-cols-2 gap-4">
              {[{ label: "A", data: result.trace_a, color: "blue" }, { label: "B", data: result.trace_b, color: "green" }].map(({ label, data, color }) => (
                <div key={label}>
                  <p className={`text-xs font-semibold text-${color}-600 mb-2`}>Trace {label}</p>
                  <div className="space-y-1">
                    {data.spans.map((s: any, i: number) => (
                      <div key={i} className={`flex items-center gap-2 text-xs p-1.5 rounded bg-${color}-50`}>
                        <span className="badge badge-info text-[9px]">{s.span_type}</span>
                        <span className="text-gray-700 font-medium">{s.name}</span>
                        <span className="text-gray-400 ml-auto">{(s.latency_ms || 0).toFixed(0)}ms</span>
                        {s.model && <span className="text-gray-400 text-[10px]">{s.model}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ComparePage() {
  return <Suspense fallback={<div className="text-gray-500">Loading...</div>}><CompareContent /></Suspense>;
}
