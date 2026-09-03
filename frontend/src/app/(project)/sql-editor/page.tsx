"use client";

import { useEffect, useState, Suspense, useRef } from "react";
import { useSearchParams } from "next/navigation";

const API = "/api/v1";

function SQLEditorContent() {
  const searchParams = useSearchParams();
  const project = searchParams.get("project") || "";

  const [query, setQuery] = useState("");
  const [result, setResult] = useState<any>(null);
  const [schema, setSchema] = useState<any[]>([]);
  const [examples, setExamples] = useState<any[]>([]);
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const [showSchema, setShowSchema] = useState(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/sql/schema`).then(r => r.json()),
      fetch(`${API}/sql/examples`).then(r => r.json()),
    ]).then(([s, e]) => {
      setSchema(s.tables || []);
      setExamples(e.examples || []);
      // Set default query
      if (e.examples?.length > 0) setQuery(e.examples[0].query);
    }).catch(() => {});
  }, []);

  const runQuery = async () => {
    if (!query.trim()) return;
    setRunning(true);
    setResult(null);
    try {
      const res = await fetch(`${API}/sql/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), limit: 100 }),
      });
      const data = await res.json();
      setResult(data);
      // Add to history
      setHistory(prev => [query.trim(), ...prev.filter(h => h !== query.trim())].slice(0, 20));
    } catch (e) {
      setResult({ error: String(e), rows: [], columns: [] });
    } finally {
      setRunning(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      runQuery();
    }
  };

  return (
    <div className="flex gap-4 h-[calc(100vh-80px)]">
      {/* Left: Schema Panel */}
      {showSchema && (
        <div className="w-64 shrink-0 overflow-y-auto border-r border-gray-200 pr-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-700">Schema</h3>
            <button onClick={() => setShowSchema(false)} className="text-gray-400 hover:text-gray-600 text-xs">Hide</button>
          </div>

          {schema.map(table => (
            <div key={table.name} className="mb-3">
              <button
                onClick={() => {
                  setQuery(`SELECT * FROM ${table.name} LIMIT 10`);
                  textareaRef.current?.focus();
                }}
                className="text-xs font-semibold text-indigo-600 hover:text-indigo-500 flex items-center gap-1"
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7" /></svg>
                {table.name}
                <span className="text-gray-400 font-normal">({table.row_count})</span>
              </button>
              <div className="ml-4 mt-1 space-y-0.5">
                {table.columns.map((col: any) => (
                  <div
                    key={col.name}
                    className="text-[10px] text-gray-500 cursor-pointer hover:text-gray-700 flex items-center gap-1"
                    onClick={() => {
                      // Insert column name at cursor
                      const ta = textareaRef.current;
                      if (ta) {
                        const pos = ta.selectionStart;
                        const before = query.substring(0, pos);
                        const after = query.substring(pos);
                        setQuery(`${before}${col.name}${after}`);
                      }
                    }}
                  >
                    {col.pk && <span className="text-yellow-500">PK</span>}
                    <span className="text-gray-700">{col.name}</span>
                    <span className="text-gray-400">{col.type}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* Example Queries */}
          <div className="mt-6 pt-4 border-t border-gray-200">
            <h3 className="text-sm font-semibold text-gray-700 mb-2">Example Queries</h3>
            <div className="space-y-1">
              {examples.map((ex, i) => (
                <button
                  key={i}
                  onClick={() => { setQuery(ex.query); textareaRef.current?.focus(); }}
                  className="block w-full text-left text-[11px] text-gray-600 hover:text-indigo-600 hover:bg-indigo-50 px-2 py-1 rounded transition-colors"
                >
                  {ex.name}
                </button>
              ))}
            </div>
          </div>

          {/* History */}
          {history.length > 0 && (
            <div className="mt-4 pt-4 border-t border-gray-200">
              <h3 className="text-sm font-semibold text-gray-700 mb-2">History</h3>
              <div className="space-y-1">
                {history.slice(0, 10).map((h, i) => (
                  <button
                    key={i}
                    onClick={() => { setQuery(h); textareaRef.current?.focus(); }}
                    className="block w-full text-left text-[10px] text-gray-500 hover:text-indigo-600 px-2 py-1 rounded truncate"
                  >
                    {h.substring(0, 60)}...
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Right: Editor + Results */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Toolbar */}
        <div className="flex items-center gap-2 mb-3">
          {!showSchema && (
            <button onClick={() => setShowSchema(true)} className="btn-secondary text-xs px-2 py-1">
              Schema
            </button>
          )}
          <h1 className="text-lg font-bold text-gray-900">SQL Editor</h1>
          <span className="text-xs text-gray-400 ml-auto">Read-only (enforced at the database connection) | Ctrl+Enter to run</span>
        </div>

        {/* SQL Editor */}
        <div className="relative mb-3">
          <textarea
            ref={textareaRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={6}
            className="w-full font-mono text-sm bg-gray-900 text-green-400 rounded-xl p-4 border border-gray-700 outline-none resize-y focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 placeholder-gray-600"
            placeholder="SELECT * FROM traces LIMIT 10"
            spellCheck={false}
          />
          <div className="absolute bottom-3 right-3 flex gap-2">
            <button onClick={() => setQuery("")} className="text-xs text-gray-500 hover:text-gray-300 px-2 py-1">
              Clear
            </button>
            <button
              onClick={runQuery}
              disabled={running || !query.trim()}
              className={`px-4 py-1.5 rounded-lg text-xs font-medium transition-all ${
                running
                  ? "bg-yellow-500 text-white animate-pulse"
                  : "bg-indigo-600 text-white hover:bg-indigo-500"
              } disabled:opacity-50`}
            >
              {running ? (
                <span className="flex items-center gap-1">
                  <svg className="animate-spin w-3 h-3" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                  Running...
                </span>
              ) : "Run Query"}
            </button>
          </div>
        </div>

        {/* Results */}
        <div className="flex-1 overflow-auto">
          {result?.error && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-3">
              <p className="text-sm font-medium text-red-700">Error</p>
              <p className="text-xs text-red-600 mt-1 font-mono">{result.error}</p>
            </div>
          )}

          {result?.columns?.length > 0 && (
            <div className="card p-0 overflow-hidden">
              <div className="px-4 py-2 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
                <span className="text-xs text-gray-500">
                  {result.row_count} row{result.row_count !== 1 ? "s" : ""} returned
                </span>
                <button
                  onClick={() => {
                    // Copy as CSV
                    const header = result.columns.join(",");
                    const rows = result.rows.map((r: any) =>
                      result.columns.map((c: string) => {
                        const v = r[c];
                        const s = v === null ? "" : String(v);
                        return s.includes(",") || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s;
                      }).join(",")
                    );
                    navigator.clipboard.writeText([header, ...rows].join("\n"));
                  }}
                  className="text-xs text-indigo-600 hover:text-indigo-500"
                >
                  Copy CSV
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left text-[10px] font-semibold text-gray-400 uppercase w-8">#</th>
                      {result.columns.map((col: string) => (
                        <th key={col} className="px-3 py-2 text-left text-[10px] font-semibold text-gray-500 uppercase whitespace-nowrap">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row: any, i: number) => (
                      <tr key={i} className="border-t border-gray-50 hover:bg-gray-50">
                        <td className="px-3 py-2 text-gray-300 text-[10px]">{i + 1}</td>
                        {result.columns.map((col: string) => {
                          const val = row[col];
                          const display = val === null ? "NULL" : String(val);
                          const isNull = val === null;
                          const isLong = display.length > 100;
                          const isId = col.includes("id") && typeof val === "string" && val.length > 20;
                          return (
                            <td key={col} className="px-3 py-2 max-w-[300px]">
                              <span
                                className={`${
                                  isNull ? "text-gray-300 italic" :
                                  isId ? "font-mono text-indigo-600 text-[10px]" :
                                  typeof val === "number" ? "text-blue-600 font-mono" :
                                  "text-gray-700"
                                } ${isLong ? "block truncate" : ""}`}
                                title={isLong ? display : undefined}
                              >
                                {isLong ? display.substring(0, 100) + "..." : display}
                              </span>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {result && !result.error && result.columns?.length === 0 && (
            <div className="text-center py-10 text-gray-400 text-sm">Query executed. No rows returned.</div>
          )}

          {!result && !running && (
            <div className="text-center py-16 text-gray-400">
              <svg className="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
              </svg>
              <p className="text-sm">Write a SQL query or click an example from the sidebar</p>
              <p className="text-xs mt-1">Tables: traces, spans, llm_configs, ground_truths</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function SQLEditorPage() {
  return <Suspense fallback={<div className="text-gray-500">Loading...</div>}><SQLEditorContent /></Suspense>;
}
