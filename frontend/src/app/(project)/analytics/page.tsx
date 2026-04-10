"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Area, AreaChart,
} from "recharts";

const API = "http://localhost:8100/api/v1";
const COLORS = ["#6366f1", "#8b5cf6", "#06b6d4", "#10b981", "#f59e0b", "#ef4444"];

function AnalyticsContent() {
  const searchParams = useSearchParams();
  const project = searchParams.get("project") || "all";
  const [tokenData, setTokenData] = useState<any>(null);
  const [costOverTime, setCostOverTime] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/analytics/tokens?project=${encodeURIComponent(project)}`).then((r) => r.json()),
      fetch(`${API}/analytics/cost/over-time?project=${encodeURIComponent(project)}`).then((r) => r.json()),
    ])
      .then(([tokens, cost]) => {
        setTokenData(tokens);
        setCostOverTime(cost);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [project]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <svg className="animate-spin w-6 h-6 text-indigo-500" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>
    );
  }

  if (!tokenData || tokenData.total_traces === 0) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-4">Analytics</h1>
        <div className="card text-center py-16">
          <h3 className="text-lg font-semibold text-gray-700 mb-2">No data yet</h3>
          <p className="text-sm text-gray-500">Run queries in the RAG or Agent app to see token and cost analytics.</p>
        </div>
      </div>
    );
  }

  const totals = tokenData.totals;
  const pieData = [
    { name: "Prompt", value: totals.prompt_tokens },
    { name: "Completion", value: totals.completion_tokens },
  ];

  // Top consumers
  const topTraces = [...(tokenData.per_trace || [])].sort((a, b) => b.total_tokens - a.total_tokens).slice(0, 10);

  // Time series data
  const timeData = (costOverTime?.data_points || []).map((d: any) => ({
    ...d,
    time: d.timestamp ? new Date(d.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "",
  }));

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
          <p className="text-sm text-gray-500">{tokenData.total_traces} traces analyzed</p>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-5 gap-4 mb-8">
        <div className="card">
          <p className="text-xs text-gray-500 mb-1">Total Tokens</p>
          <p className="text-2xl font-bold text-gray-900">{totals.total_tokens.toLocaleString()}</p>
        </div>
        <div className="card">
          <p className="text-xs text-gray-500 mb-1">Prompt Tokens</p>
          <p className="text-2xl font-bold text-indigo-600">{totals.prompt_tokens.toLocaleString()}</p>
          <p className="text-xs text-gray-400">{tokenData.token_split.prompt_pct}%</p>
        </div>
        <div className="card">
          <p className="text-xs text-gray-500 mb-1">Completion Tokens</p>
          <p className="text-2xl font-bold text-purple-600">{totals.completion_tokens.toLocaleString()}</p>
          <p className="text-xs text-gray-400">{tokenData.token_split.completion_pct}%</p>
        </div>
        <div className="card">
          <p className="text-xs text-gray-500 mb-1">Total Cost</p>
          <p className="text-2xl font-bold text-green-600">${totals.total_cost_usd.toFixed(4)}</p>
        </div>
        <div className="card">
          <p className="text-xs text-gray-500 mb-1">Avg Tokens/Trace</p>
          <p className="text-2xl font-bold text-gray-900">{totals.avg_tokens_per_trace.toFixed(0)}</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6 mb-8">
        {/* Token Distribution Pie */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Token Distribution</h3>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                {pieData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i]} />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => v.toLocaleString()} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Cumulative Cost Over Time */}
        <div className="card col-span-2">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Cumulative Cost Over Time</h3>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={timeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="time" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `$${v.toFixed(3)}`} />
              <Tooltip formatter={(v: number) => `$${v.toFixed(6)}`} />
              <Area type="monotone" dataKey="cumulative_cost" stroke="#6366f1" fill="#6366f1" fillOpacity={0.1} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6 mb-8">
        {/* Tokens Per Trace Bar Chart */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Tokens Per Trace (Top 10)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={topTraces} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis type="number" tick={{ fontSize: 10 }} />
              <YAxis dataKey="trace_id" type="category" tick={{ fontSize: 9 }} width={80} tickFormatter={(v) => v.substring(0, 8)} />
              <Tooltip formatter={(v: number) => v.toLocaleString()} />
              <Bar dataKey="prompt_tokens" stackId="a" fill="#6366f1" name="Prompt" />
              <Bar dataKey="completion_tokens" stackId="a" fill="#8b5cf6" name="Completion" />
              <Legend />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Latency vs Tokens Scatter */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Latency Over Time</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={timeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="time" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${v}ms`} />
              <Tooltip formatter={(v: number) => `${v.toFixed(0)}ms`} />
              <Line type="monotone" dataKey="latency_ms" stroke="#f59e0b" dot={{ r: 3 }} name="Latency" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Per-Trace Token Table */}
      <div className="card p-0 overflow-hidden">
        <div className="px-4 py-3 bg-gray-50 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-700">Token Usage Per Trace</h3>
        </div>
        <table className="table-dark">
          <thead>
            <tr>
              <th>Trace</th>
              <th>Query</th>
              <th>Prompt Tokens</th>
              <th>Completion Tokens</th>
              <th>Total Tokens</th>
              <th>Cost</th>
              <th>Latency</th>
              <th>Spans</th>
            </tr>
          </thead>
          <tbody>
            {tokenData.per_trace.map((t: any) => (
              <tr key={t.trace_id}>
                <td>
                  <Link href={`/traces/${t.trace_id}?project=${encodeURIComponent(project)}`} className="font-mono text-xs text-indigo-600 hover:text-indigo-500">
                    {t.trace_id.substring(0, 10)}
                  </Link>
                </td>
                <td className="text-gray-600 truncate max-w-[150px]">{t.query || "—"}</td>
                <td className="text-indigo-600 font-medium">{t.prompt_tokens.toLocaleString()}</td>
                <td className="text-purple-600 font-medium">{t.completion_tokens.toLocaleString()}</td>
                <td className="font-bold text-gray-900">{t.total_tokens.toLocaleString()}</td>
                <td className="text-green-600">${t.cost_usd.toFixed(5)}</td>
                <td className="text-gray-500">{(t.latency_ms || 0).toFixed(0)}ms</td>
                <td className="text-gray-500">{t.num_spans}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  return <Suspense fallback={<div className="text-gray-500">Loading...</div>}><AnalyticsContent /></Suspense>;
}
