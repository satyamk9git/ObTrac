"use client";

import { useEffect, useState } from "react";

const API = "/api/v1";

interface Props {
  traceId: string;
  metric: string;
  score: number;
  metricName?: string;
  onClose: () => void;
}

export default function MetricExplainModal({ traceId, metric, score, metricName, onClose }: Props) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [llmLoading, setLlmLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setLlmLoading(true);
    fetch(`${API}/explain/metric`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        trace_id: traceId,
        metric,
        score,
        use_llm: true,
      }),
    })
      .then(r => r.json())
      .then(d => {
        setData(d);
      })
      .catch(() => setData(null))
      .finally(() => {
        setLoading(false);
        setLlmLoading(false);
      });

    // Handle Escape key
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [traceId, metric, score]);

  const severityColor = data?.severity === "good" ? "green" : data?.severity === "warning" ? "yellow" : "red";
  const severityBg = data?.severity === "good" ? "bg-green-50 border-green-200" : data?.severity === "warning" ? "bg-yellow-50 border-yellow-200" : "bg-red-50 border-red-200";
  const severityText = data?.severity === "good" ? "text-green-700" : data?.severity === "warning" ? "text-yellow-700" : "text-red-700";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative w-full max-w-3xl max-h-[85vh] bg-white rounded-xl shadow-2xl overflow-hidden flex flex-col animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold text-gray-900">{metricName || metric}</h2>
            <span className={`text-2xl font-bold ${
              score >= 0.8 ? "text-green-600" : score >= 0.6 ? "text-yellow-600" : "text-red-600"
            }`}>
              {(score * 100).toFixed(1)}%
            </span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-2xl leading-none">×</button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <svg className="animate-spin w-6 h-6 text-indigo-500" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
            </div>
          ) : !data ? (
            <p className="text-red-500">Failed to load explanation</p>
          ) : (
            <div className="space-y-4">
              {/* Verdict */}
              <div className={`rounded-lg border p-3 ${severityBg}`}>
                <p className={`text-sm font-medium ${severityText}`}>{data.verdict}</p>
              </div>

              {/* What it measures */}
              <section>
                <h3 className="text-sm font-semibold text-gray-700 mb-1">What does this metric measure?</h3>
                <p className="text-sm text-gray-600">{data.what_it_measures}</p>
                <p className="text-xs text-gray-500 mt-1">{data.scoring}</p>
              </section>

              {/* Trace-specific LLM analysis */}
              {data.trace_specific_analysis && (
                <section className="bg-indigo-50 border border-indigo-200 rounded-lg p-3">
                  <h3 className="text-sm font-semibold text-indigo-700 mb-2 flex items-center gap-1">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
                    AI Analysis of This Specific Trace
                  </h3>
                  {data.trace_specific_analysis.error ? (
                    <p className="text-xs text-red-600">{data.trace_specific_analysis.error}</p>
                  ) : (
                    <div className="space-y-2 text-xs">
                      {data.trace_specific_analysis.diagnosis && (
                        <div>
                          <p className="font-semibold text-gray-700">Diagnosis</p>
                          <p className="text-gray-600">{data.trace_specific_analysis.diagnosis}</p>
                        </div>
                      )}
                      {data.trace_specific_analysis.evidence && (
                        <div>
                          <p className="font-semibold text-gray-700">Evidence</p>
                          <p className="text-gray-600 italic">"{data.trace_specific_analysis.evidence}"</p>
                        </div>
                      )}
                      {data.trace_specific_analysis.fix && (
                        <div>
                          <p className="font-semibold text-gray-700">Recommended Fix</p>
                          <p className="text-gray-600">{data.trace_specific_analysis.fix}</p>
                        </div>
                      )}
                      {data.trace_specific_analysis.priority && (
                        <span className={`badge ${
                          data.trace_specific_analysis.priority === "high" ? "badge-error" :
                          data.trace_specific_analysis.priority === "medium" ? "badge-warning" : "badge-info"
                        }`}>
                          Priority: {data.trace_specific_analysis.priority}
                        </span>
                      )}
                    </div>
                  )}
                </section>
              )}

              {/* Common causes */}
              {data.common_causes?.length > 0 && (
                <section>
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">Why this metric is low (common causes)</h3>
                  <ul className="space-y-1 text-sm text-gray-600">
                    {data.common_causes.map((c: string, i: number) => (
                      <li key={i} className="flex gap-2">
                        <span className="text-red-400 shrink-0">•</span>
                        <span>{c}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Improvement techniques */}
              {data.improvement_techniques?.length > 0 && (
                <section>
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">How to improve</h3>
                  <ul className="space-y-1 text-sm text-gray-600">
                    {data.improvement_techniques.map((c: string, i: number) => (
                      <li key={i} className="flex gap-2">
                        <span className="text-green-500 shrink-0">✓</span>
                        <span>{c}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-gray-200 bg-gray-50 flex justify-end">
          <button onClick={onClose} className="btn-secondary text-sm">Close</button>
        </div>
      </div>
    </div>
  );
}
