"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

const API = "/api/v1";

export default function SearchBar({ project }: { project?: string }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!query || query.length < 2) { setResults([]); return; }
    const timeout = setTimeout(() => {
      setLoading(true);
      const p = project && project !== "all" ? `&project=${project}` : "";
      fetch(`${API}/traces/search?q=${encodeURIComponent(query)}${p}&limit=10`)
        .then((r) => r.json())
        .then((d) => setResults(d.traces || []))
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(timeout);
  }, [query, project]);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-400 hover:border-indigo-300 hover:text-gray-500 transition-all"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        Search traces...
        <kbd className="ml-4 px-1.5 py-0.5 bg-gray-100 rounded text-[10px] font-mono text-gray-400 border border-gray-200">
          Ctrl+K
        </kbd>
      </button>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]">
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={() => setOpen(false)} />
      <div className="relative w-full max-w-xl bg-white border border-gray-200 rounded-xl shadow-2xl animate-fade-in overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100">
          <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search traces by query, answer, ID..."
            className="flex-1 bg-transparent text-sm text-gray-900 placeholder-gray-400 outline-none"
          />
          {loading && (
            <svg className="animate-spin w-4 h-4 text-indigo-500" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-[10px] font-mono text-gray-400 border border-gray-200">
            Esc
          </kbd>
        </div>

        <div className="max-h-80 overflow-y-auto">
          {results.length === 0 && query.length >= 2 && !loading && (
            <p className="px-4 py-6 text-sm text-gray-400 text-center">No results found</p>
          )}
          {results.map((t) => (
            <button
              key={t.trace_id}
              onClick={() => {
                router.push(`/traces/${t.trace_id}${project ? `?project=${project}` : ""}`);
                setOpen(false);
                setQuery("");
              }}
              className="w-full px-4 py-3 text-left hover:bg-gray-50 transition-colors border-b border-gray-50 last:border-0"
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="badge badge-info">{t.project}</span>
                <span className="text-xs font-mono text-gray-400">{t.trace_id.substring(0, 8)}</span>
                <span className={`badge ${t.status === "success" ? "badge-success" : "badge-error"}`}>
                  {t.status}
                </span>
                <span className="text-xs text-gray-400 ml-auto">
                  {t.created_at ? new Date(t.created_at).toLocaleDateString() : ""}
                </span>
              </div>
              <p className="text-sm text-gray-700 truncate">{t.query || t.name || "—"}</p>
              {t.answer && <p className="text-xs text-gray-400 truncate mt-0.5">{t.answer}</p>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
