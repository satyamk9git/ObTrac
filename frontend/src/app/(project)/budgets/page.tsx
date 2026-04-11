"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

const API = "http://localhost:8100/api/v1";

type Channel = {
  id: string;
  name: string;
  channel_type: string;
  is_active: boolean;
};

type Budget = {
  id: string;
  name: string;
  project: string;
  period: string;
  amount_usd: number;
  alert_thresholds: number[];
  alert_channel_ids: string[];
  alert_channels: Channel[];
  is_active: boolean;
  spent_usd: number;
  remaining_usd: number;
  used_pct: number;
  status: string;
  period_start: string;
  last_fired_threshold: number | null;
  last_fired_at: string | null;
};

function BudgetsContent() {
  const searchParams = useSearchParams();
  const project = searchParams.get("project") || "default";
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Form state
  const [name, setName] = useState("Monthly Budget");
  const [period, setPeriod] = useState("monthly");
  const [amount, setAmount] = useState("100");
  const [thresholds, setThresholds] = useState("50, 80, 100");
  const [selectedChannelIds, setSelectedChannelIds] = useState<string[]>([]);

  const fetchAll = () => {
    setLoading(true);
    Promise.all([
      fetch(`${API}/budgets?project=${encodeURIComponent(project)}`).then((r) => r.json()),
      fetch(`${API}/alerts/channels`).then((r) => r.json()),
    ])
      .then(([b, c]) => {
        setBudgets(b.budgets || []);
        setChannels(c.channels || []);
      })
      .catch(() => {
        setBudgets([]);
        setChannels([]);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchAll(); }, [project]);

  const resetForm = () => {
    setName("Monthly Budget");
    setPeriod("monthly");
    setAmount("100");
    setThresholds("50, 80, 100");
    setSelectedChannelIds([]);
    setEditingId(null);
  };

  const handleStartEdit = (b: Budget) => {
    setEditingId(b.id);
    setName(b.name);
    setPeriod(b.period);
    setAmount(String(b.amount_usd));
    setThresholds((b.alert_thresholds || []).join(", "));
    setSelectedChannelIds(b.alert_channel_ids || []);
    setShowForm(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const thresholdList = thresholds
      .split(",")
      .map((t) => parseInt(t.trim()))
      .filter((n) => !isNaN(n));

    const body = {
      project,
      name,
      period,
      amount_usd: parseFloat(amount),
      alert_thresholds: thresholdList,
      alert_channel_ids: selectedChannelIds,
    };

    const url = editingId ? `${API}/budgets/${editingId}` : `${API}/budgets`;
    const method = editingId ? "PUT" : "POST";
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      setShowForm(false);
      resetForm();
      fetchAll();
    } else {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || "Failed to save budget");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this budget?")) return;
    await fetch(`${API}/budgets/${id}`, { method: "DELETE" });
    fetchAll();
  };

  const handleToggle = async (b: Budget) => {
    await fetch(`${API}/budgets/${b.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !b.is_active }),
    });
    fetchAll();
  };

  const toggleChannel = (id: string) => {
    setSelectedChannelIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Cost Budgets</h1>
          <p className="text-sm text-gray-500">{budgets.length} budgets in {project}</p>
        </div>
        <button
          onClick={() => {
            if (showForm) {
              setShowForm(false);
              resetForm();
            } else {
              resetForm();
              setShowForm(true);
            }
          }}
          className="btn-primary"
        >
          {showForm ? "Cancel" : "+ New Budget"}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="card mb-6 space-y-3">
          <h2 className="text-base font-semibold text-gray-900">
            {editingId ? "Edit Budget" : "Create Budget"}
          </h2>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} required className="input-dark" />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Period</label>
              <select value={period} onChange={(e) => setPeriod(e.target.value)} className="select-dark">
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Amount (USD)</label>
              <input
                type="number"
                step="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
                className="input-dark"
                placeholder="100"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Alert thresholds (% comma separated)</label>
              <input
                value={thresholds}
                onChange={(e) => setThresholds(e.target.value)}
                className="input-dark"
                placeholder="50, 80, 100"
              />
              <p className="text-[10px] text-gray-400 mt-0.5">Alerts fire when budget reaches these percentages</p>
            </div>
          </div>

          {/* Channel mapping */}
          <div>
            <label className="block text-xs text-gray-600 mb-1">Notify channels</label>
            {channels.length === 0 ? (
              <div className="text-xs bg-yellow-50 border border-yellow-200 rounded px-3 py-2 text-yellow-800">
                No alert channels yet.{" "}
                <Link href={`/alerts?project=${encodeURIComponent(project)}`} className="underline font-semibold">
                  Create one in Alerts
                </Link>{" "}
                first, then come back here to map it.
              </div>
            ) : (
              <div className="border border-gray-200 rounded-lg p-2 max-h-40 overflow-y-auto">
                {channels.map((c) => (
                  <label key={c.id} className="flex items-center gap-2 px-2 py-1.5 hover:bg-gray-50 rounded cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedChannelIds.includes(c.id)}
                      onChange={() => toggleChannel(c.id)}
                    />
                    <span className="text-xs font-semibold text-gray-700">{c.name}</span>
                    <span className="text-[10px] text-gray-500 uppercase">{c.channel_type}</span>
                    {!c.is_active && <span className="text-[10px] text-gray-400">(inactive)</span>}
                  </label>
                ))}
              </div>
            )}
            <p className="text-[10px] text-gray-400 mt-1">
              {selectedChannelIds.length === 0
                ? "Without any channels, this budget will track spend silently."
                : `When a threshold is crossed, alerts will fire to ${selectedChannelIds.length} channel${selectedChannelIds.length !== 1 ? "s" : ""}.`}
            </p>
          </div>

          <div className="flex gap-2">
            <button type="submit" className="btn-primary">
              {editingId ? "Save Changes" : "Create Budget"}
            </button>
            {editingId && (
              <button type="button" onClick={() => { setShowForm(false); resetForm(); }} className="btn-secondary">
                Cancel
              </button>
            )}
          </div>
        </form>
      )}

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="animate-spin w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full" />
        </div>
      ) : budgets.length === 0 ? (
        <div className="card text-center py-16">
          <h3 className="text-lg font-semibold text-gray-700 mb-2">No budgets yet</h3>
          <p className="text-sm text-gray-500">
            Create a budget to track spending and get alerts when limits are reached.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {budgets.map((b) => {
            const statusColor = b.status === "exceeded" ? "red" : b.status === "warning" ? "yellow" : "green";
            const barColor = statusColor === "red" ? "bg-red-500" : statusColor === "yellow" ? "bg-yellow-500" : "bg-green-500";

            // Period-aware label so the "spent" number isn't confused with lifetime cost
            const spentLabel =
              b.period === "daily" ? "Spent today" :
              b.period === "weekly" ? "Spent this week" :
              b.period === "monthly" ? "Spent this month" :
              "Spent this period";
            const resetLabel =
              b.period === "daily" ? "resets at midnight" :
              b.period === "weekly" ? "resets Monday" :
              b.period === "monthly" ? "resets on the 1st" :
              "";

            return (
              <div key={b.id} className="card">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-base font-semibold text-gray-900">{b.name}</h3>
                    <p className="text-xs text-gray-500">
                      {b.period} budget · {resetLabel} · period started {new Date(b.period_start).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleToggle(b)}
                      className={`text-xs px-2 py-1 rounded ${b.is_active ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"}`}
                    >
                      {b.is_active ? "Active" : "Paused"}
                    </button>
                    <button onClick={() => handleStartEdit(b)} className="text-xs text-indigo-600 hover:text-indigo-700">
                      Edit
                    </button>
                    <button onClick={() => handleDelete(b.id)} className="text-xs text-red-500 hover:text-red-600">
                      Delete
                    </button>
                  </div>
                </div>

                <div className="mb-2">
                  <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{spentLabel}</p>
                  <div className="flex items-center justify-between">
                    <span
                      className="text-2xl font-bold text-gray-900"
                      title={`Sum of total_cost_usd for traces in ${b.project} since ${new Date(b.period_start).toLocaleString()}`}
                    >
                      ${b.spent_usd.toFixed(4)}
                    </span>
                    <span className="text-sm text-gray-500">of ${b.amount_usd.toFixed(2)} budget</span>
                  </div>
                </div>

                <div className="w-full bg-gray-100 rounded-full h-3 mb-2">
                  <div
                    className={`h-3 rounded-full ${barColor} transition-all`}
                    style={{ width: `${Math.min(b.used_pct, 100)}%` }}
                  />
                </div>

                <div className="flex items-center justify-between text-xs">
                  <span className={`font-semibold ${statusColor === "red" ? "text-red-600" : statusColor === "yellow" ? "text-yellow-600" : "text-green-600"}`}>
                    {b.used_pct.toFixed(1)}% used
                  </span>
                  <span className="text-gray-500">${b.remaining_usd.toFixed(4)} remaining</span>
                </div>

                {/* Threshold pills + last fired indicator */}
                <div className="flex flex-wrap gap-2 mt-3">
                  {(b.alert_thresholds || []).map((t: number) => {
                    const crossed = b.used_pct >= t;
                    const fired = b.last_fired_threshold !== null && t <= b.last_fired_threshold;
                    return (
                      <span
                        key={t}
                        className={`text-[10px] px-2 py-0.5 rounded ${
                          fired
                            ? "bg-red-100 text-red-700 font-semibold"
                            : crossed
                              ? "bg-yellow-100 text-yellow-700"
                              : "bg-gray-100 text-gray-500"
                        }`}
                        title={fired ? "Already notified this period" : crossed ? "Crossed but not yet fired" : "Not crossed"}
                      >
                        {t}% {fired ? "🔔" : crossed ? "•" : ""}
                      </span>
                    );
                  })}
                  {b.last_fired_at && (
                    <span className="text-[10px] text-gray-500 italic ml-1">
                      Last fired: {new Date(b.last_fired_at).toLocaleString()}
                    </span>
                  )}
                </div>

                {/* Notify channels */}
                <div className="mt-3 border-t border-gray-100 pt-3">
                  {(b.alert_channels || []).length > 0 ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">📢 Notifies:</span>
                      {b.alert_channels.map((c) => (
                        <span
                          key={c.id}
                          className={`text-[11px] px-2 py-0.5 rounded border ${
                            c.is_active
                              ? "bg-indigo-50 border-indigo-200 text-indigo-700"
                              : "bg-gray-50 border-gray-200 text-gray-400"
                          }`}
                          title={c.is_active ? "" : "Channel is inactive"}
                        >
                          {c.channel_type === "slack" ? "💬" : "🔗"} {c.name}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-[11px] text-yellow-700 bg-yellow-50 border border-yellow-200 rounded px-2 py-1.5">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      No alert channels configured. This budget tracks spend silently — nobody will be notified.
                      <button onClick={() => handleStartEdit(b)} className="underline font-semibold">
                        Add channels
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function BudgetsPage() {
  return <Suspense fallback={<div className="text-gray-500">Loading...</div>}><BudgetsContent /></Suspense>;
}
