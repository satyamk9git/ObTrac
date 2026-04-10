"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

const API = "http://localhost:8100/api/v1";

function SessionsContent() {
  const searchParams = useSearchParams();
  const project = searchParams.get("project") || "all";
  const [sessions, setSessions] = useState<any[]>([]);
  const [selectedSession, setSelectedSession] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/sessions?project=${encodeURIComponent(project)}`)
      .then(r => r.json())
      .then(d => setSessions(d.sessions || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [project]);

  const loadSession = async (sessionId: string) => {
    const res = await fetch(`${API}/sessions/${sessionId}`);
    setSelectedSession(await res.json());
  };

  if (loading) return <div className="flex justify-center py-20"><div className="animate-spin w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full" /></div>;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Sessions</h1>
          <p className="text-sm text-gray-500">Conversations grouped by session_id</p>
        </div>
      </div>

      {sessions.length === 0 ? (
        <div className="card text-center py-16">
          <h3 className="text-lg font-semibold text-gray-700 mb-2">No sessions yet</h3>
          <p className="text-sm text-gray-500">
            Pass <code className="bg-gray-100 px-1 rounded">session_id</code> in <code className="bg-gray-100 px-1 rounded">obtrac_config()</code> to group traces into sessions.
          </p>
          <pre className="mt-4 text-xs bg-gray-50 p-3 rounded-lg text-left max-w-md mx-auto text-gray-600">
{`config = obtrac_config(
    project="my-app",
    user="satyam",
    session_id="conv_abc123",
)`}
          </pre>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-6">
          {/* Sessions List */}
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-gray-600 mb-2">{sessions.length} Sessions</h3>
            {sessions.map(s => (
              <button
                key={s.session_id}
                onClick={() => loadSession(s.session_id)}
                className={`w-full text-left card p-3 transition-colors ${
                  selectedSession?.session_id === s.session_id ? "border-indigo-400 bg-indigo-50" : ""
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-mono text-indigo-600">{s.session_id.substring(0, 16)}</span>
                  <span className="badge badge-info">{s.trace_count} traces</span>
                </div>
                <div className="flex items-center gap-2 text-[10px] text-gray-500">
                  {s.user && <span className="badge badge-purple">{s.user}</span>}
                  <span>{s.started_at ? new Date(s.started_at).toLocaleString() : ""}</span>
                </div>
                <div className="flex gap-3 mt-1 text-[10px] text-gray-400">
                  <span>{s.total_latency_ms.toFixed(0)}ms total</span>
                  <span>${s.total_cost_usd.toFixed(4)}</span>
                </div>
              </button>
            ))}
          </div>

          {/* Session Detail — Conversation View */}
          <div className="col-span-2">
            {!selectedSession ? (
              <div className="card text-center py-16 text-gray-400">
                <p>Select a session to view the conversation</p>
              </div>
            ) : (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700">
                      Session: <span className="font-mono text-indigo-600">{selectedSession.session_id.substring(0, 20)}</span>
                    </h3>
                    <p className="text-xs text-gray-500">
                      {selectedSession.trace_count} turns | {selectedSession.user} | {selectedSession.started_at ? new Date(selectedSession.started_at).toLocaleString() : ""}
                    </p>
                  </div>
                </div>

                {/* Conversation Timeline */}
                <div className="space-y-3">
                  {selectedSession.traces.map((t: any, i: number) => (
                    <div key={t.trace_id} className="card animate-fade-in">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="w-6 h-6 bg-indigo-100 text-indigo-600 rounded-full flex items-center justify-center text-xs font-bold">
                          {i + 1}
                        </span>
                        <span className={`badge ${t.status === "success" ? "badge-success" : "badge-error"}`}>{t.status}</span>
                        <span className="text-xs text-gray-400">{(t.total_latency_ms || 0).toFixed(0)}ms</span>
                        <span className="text-xs text-gray-400">{t.num_spans} spans</span>
                        {Object.entries(t.metrics || {}).slice(0, 2).map(([k, v]) => (
                          <span key={k} className={`text-[10px] px-1.5 py-0.5 rounded ${(v as number) >= 0.7 ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
                            {k.split("_")[0]}: {((v as number) * 100).toFixed(0)}%
                          </span>
                        ))}
                        <Link href={`/traces/${t.trace_id}?project=${encodeURIComponent(project)}`}
                          className="text-[10px] text-indigo-600 hover:text-indigo-500 ml-auto">
                          View trace
                        </Link>
                      </div>

                      {/* Query */}
                      <div className="bg-gray-50 rounded-lg p-3 mb-2">
                        <p className="text-[10px] text-gray-400 mb-0.5">User</p>
                        <p className="text-sm text-gray-800">{t.query || "—"}</p>
                      </div>

                      {/* Answer */}
                      <div className="bg-indigo-50 rounded-lg p-3">
                        <p className="text-[10px] text-indigo-400 mb-0.5">Assistant</p>
                        <p className="text-sm text-gray-700 whitespace-pre-wrap">{t.answer || "—"}</p>
                      </div>

                      {/* Time */}
                      <p className="text-[10px] text-gray-400 mt-1">
                        {t.created_at ? new Date(t.created_at).toLocaleString() : ""}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function SessionsPage() {
  return <Suspense fallback={<div className="text-gray-500">Loading...</div>}><SessionsContent /></Suspense>;
}
