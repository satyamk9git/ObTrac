"use client";

import { useEffect, useMemo, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import ColumnHeader, { SortDir } from "@/components/ColumnHeader";

const API = "/api/v1";

function TracesContent() {
  const searchParams = useSearchParams();
  const project = searchParams.get("project") || "all";
  const [traces, setTraces] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  // Filters — empty array means "show all"
  const [traceIdFilter, setTraceIdFilter] = useState<(string | number)[]>([]);
  const [pipelineFilter, setPipelineFilter] = useState<(string | number)[]>([]);
  const [userFilter, setUserFilter] = useState<(string | number)[]>([]);
  const [statusFilter, setStatusFilter] = useState<(string | number)[]>([]);
  const [spansFilter, setSpansFilter] = useState<(string | number)[]>([]);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  // Sort
  const [latencySort, setLatencySort] = useState<SortDir>(null);
  const [timeSort, setTimeSort] = useState<SortDir>("desc"); // newest first by default

  const fetchTraces = () => {
    setLoading(true);
    const params = new URLSearchParams({ project, limit: "200" });
    fetch(`${API}/traces?${params}`)
      .then((r) => r.json())
      .then((d) => {
        setTraces(d.traces || []);
        setTotal(d.total || 0);
      })
      .catch(() => setTraces([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchTraces(); }, [project]);

  // Distinct value lists for the filter dropdowns
  const distinct = useMemo(() => {
    const ids = new Set<string>();
    const pipelines = new Set<string>();
    const users = new Set<string>();
    const statuses = new Set<string>();
    const spans = new Set<number>();
    for (const t of traces) {
      if (t.trace_id) ids.add(t.trace_id.substring(0, 12));
      if (t.name) pipelines.add(t.name);
      if (t.user) users.add(t.user);
      if (t.status) statuses.add(t.status);
      if (typeof t.num_spans === "number") spans.add(t.num_spans);
    }
    return {
      ids: Array.from(ids).sort(),
      pipelines: Array.from(pipelines).sort(),
      users: Array.from(users).sort(),
      statuses: Array.from(statuses).sort(),
      spans: Array.from(spans).sort((a, b) => a - b),
    };
  }, [traces]);

  // Apply filters + sort client-side. ColumnHeader uses two sentinels:
  //   []                  → "show all" (no filter)
  //   ["__NONE__"]        → "show nothing" (everything is unchecked)
  //   [v1, v2, ...]       → specific subset
  const NONE = "__NONE__";
  const isNoneFilter = (f: (string | number)[]) => f.length === 1 && f[0] === NONE;

  const visible = useMemo(() => {
    let list = traces.slice();

    if (isNoneFilter(traceIdFilter)) return [];
    if (traceIdFilter.length > 0) {
      list = list.filter((t) => traceIdFilter.includes(t.trace_id?.substring(0, 12)));
    }
    if (isNoneFilter(pipelineFilter)) return [];
    if (pipelineFilter.length > 0) {
      list = list.filter((t) => pipelineFilter.includes(t.name));
    }
    if (isNoneFilter(userFilter)) return [];
    if (userFilter.length > 0) {
      list = list.filter((t) => userFilter.includes(t.user));
    }
    if (isNoneFilter(statusFilter)) return [];
    if (statusFilter.length > 0) {
      list = list.filter((t) => statusFilter.includes(t.status));
    }
    if (isNoneFilter(spansFilter)) return [];
    if (spansFilter.length > 0) {
      list = list.filter((t) => spansFilter.includes(t.num_spans));
    }
    if (dateFrom) {
      const fromTs = new Date(dateFrom).getTime();
      list = list.filter((t) => t.created_at && new Date(t.created_at).getTime() >= fromTs);
    }
    if (dateTo) {
      // Make end-of-day inclusive
      const toTs = new Date(dateTo).getTime() + 24 * 60 * 60 * 1000 - 1;
      list = list.filter((t) => t.created_at && new Date(t.created_at).getTime() <= toTs);
    }

    if (latencySort) {
      list.sort((a, b) => {
        const av = a.total_latency_ms || 0;
        const bv = b.total_latency_ms || 0;
        return latencySort === "asc" ? av - bv : bv - av;
      });
    } else if (timeSort) {
      list.sort((a, b) => {
        const av = a.created_at ? new Date(a.created_at).getTime() : 0;
        const bv = b.created_at ? new Date(b.created_at).getTime() : 0;
        return timeSort === "asc" ? av - bv : bv - av;
      });
    }

    return list;
  }, [traces, traceIdFilter, pipelineFilter, userFilter, statusFilter, spansFilter, dateFrom, dateTo, latencySort, timeSort]);

  const activeFilters: { label: string; clear: () => void }[] = [];
  if (traceIdFilter.length) activeFilters.push({ label: `Trace ID: ${traceIdFilter.length}`, clear: () => setTraceIdFilter([]) });
  if (pipelineFilter.length) activeFilters.push({ label: `Pipeline: ${pipelineFilter.length}`, clear: () => setPipelineFilter([]) });
  if (userFilter.length) activeFilters.push({ label: `User: ${userFilter.length}`, clear: () => setUserFilter([]) });
  if (statusFilter.length) activeFilters.push({ label: `Status: ${statusFilter.join(", ")}`, clear: () => setStatusFilter([]) });
  if (spansFilter.length) activeFilters.push({ label: `Spans: ${spansFilter.join(", ")}`, clear: () => setSpansFilter([]) });
  if (dateFrom || dateTo) activeFilters.push({
    label: `Date: ${dateFrom || "…"} → ${dateTo || "…"}`,
    clear: () => { setDateFrom(""); setDateTo(""); },
  });

  const clearAll = () => {
    setTraceIdFilter([]);
    setPipelineFilter([]);
    setUserFilter([]);
    setStatusFilter([]);
    setSpansFilter([]);
    setDateFrom("");
    setDateTo("");
    setLatencySort(null);
    setTimeSort("desc");
  };

  // When latency sort is set, clear time sort (and vice versa) — only one column can be the active sort
  const setLatencySortExclusive = (d: SortDir) => {
    setLatencySort(d);
    if (d) setTimeSort(null);
  };
  const setTimeSortExclusive = (d: SortDir) => {
    setTimeSort(d);
    if (d) setLatencySort(null);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Traces</h1>
          <p className="text-sm text-gray-500">
            Showing {visible.length} of {total} traces {project !== "all" ? `in ${project}` : "across all projects"}
          </p>
        </div>
        <button onClick={fetchTraces} className="btn-primary">Refresh</button>
      </div>

      {/* Active filter chips */}
      {(activeFilters.length > 0 || latencySort || timeSort !== "desc") && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-xs text-gray-500 font-semibold">Active:</span>
          {activeFilters.map((f, i) => (
            <button
              key={i}
              onClick={f.clear}
              className="flex items-center gap-1 text-[11px] bg-indigo-50 border border-indigo-200 text-indigo-700 px-2 py-1 rounded hover:bg-indigo-100"
            >
              {f.label}
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          ))}
          {latencySort && (
            <button
              onClick={() => setLatencySort(null)}
              className="flex items-center gap-1 text-[11px] bg-purple-50 border border-purple-200 text-purple-700 px-2 py-1 rounded hover:bg-purple-100"
            >
              Sort: Latency {latencySort === "asc" ? "↑" : "↓"}
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
          {timeSort !== "desc" && (
            <button
              onClick={() => setTimeSort("desc")}
              className="flex items-center gap-1 text-[11px] bg-purple-50 border border-purple-200 text-purple-700 px-2 py-1 rounded hover:bg-purple-100"
            >
              Sort: Time {timeSort === "asc" ? "↑" : timeSort === "desc" ? "↓" : "—"}
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
          <button
            onClick={clearAll}
            className="text-[11px] text-gray-500 hover:text-gray-700 underline ml-1"
          >
            Clear all
          </button>
        </div>
      )}

      <div className="card p-0 overflow-hidden">
        <table className="table-dark">
          <thead>
            <tr>
              <th>
                <ColumnHeader
                  label="Trace ID"
                  values={distinct.ids}
                  selected={traceIdFilter}
                  onFilterChange={setTraceIdFilter}
                />
              </th>
              {project === "all" && <th>Project</th>}
              <th>
                <ColumnHeader
                  label="Pipeline"
                  values={distinct.pipelines}
                  selected={pipelineFilter}
                  onFilterChange={setPipelineFilter}
                />
              </th>
              <th>
                <ColumnHeader
                  label="User"
                  values={distinct.users}
                  selected={userFilter}
                  onFilterChange={setUserFilter}
                />
              </th>
              <th>Query</th>
              <th>
                <ColumnHeader
                  label="Status"
                  values={distinct.statuses}
                  selected={statusFilter}
                  onFilterChange={setStatusFilter}
                />
              </th>
              <th>
                <ColumnHeader
                  label="Spans"
                  values={distinct.spans}
                  selected={spansFilter}
                  onFilterChange={setSpansFilter}
                />
              </th>
              <th>
                <ColumnHeader
                  label="Latency"
                  sortable
                  sortDir={latencySort}
                  onSortChange={setLatencySortExclusive}
                />
              </th>
              <th>Metrics</th>
              <th>
                <ColumnHeader
                  label="Time"
                  sortable
                  sortDir={timeSort}
                  onSortChange={setTimeSortExclusive}
                  dateRange
                  dateFrom={dateFrom}
                  dateTo={dateTo}
                  onDateRangeChange={(from, to) => { setDateFrom(from); setDateTo(to); }}
                />
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={10} className="text-center py-10 text-gray-500">Loading...</td></tr>
            ) : visible.length === 0 ? (
              <tr><td colSpan={10} className="text-center py-10 text-gray-500">
                {traces.length === 0 ? "No traces found." : "No traces match the active filters."}
              </td></tr>
            ) : visible.map((t) => (
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
