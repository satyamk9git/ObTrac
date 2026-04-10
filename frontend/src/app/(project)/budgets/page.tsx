"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";

const API = "http://localhost:8100/api/v1";

function BudgetsContent() {
  const searchParams = useSearchParams();
  const project = searchParams.get("project") || "default";
  const [budgets, setBudgets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  // Form state
  const [name, setName] = useState("Monthly Budget");
  const [period, setPeriod] = useState("monthly");
  const [amount, setAmount] = useState("100");
  const [thresholds, setThresholds] = useState("50, 80, 100");

  const fetchBudgets = () => {
    setLoading(true);
    fetch(`${API}/budgets?project=${encodeURIComponent(project)}`)
      .then(r => r.json())
      .then(d => setBudgets(d.budgets || []))
      .catch(() => setBudgets([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchBudgets(); }, [project]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const thresholdList = thresholds.split(",").map(t => parseInt(t.trim())).filter(n => !isNaN(n));
    const res = await fetch(`${API}/budgets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project,
        name,
        period,
        amount_usd: parseFloat(amount),
        alert_thresholds: thresholdList,
      }),
    });
    if (res.ok) {
      setShowForm(false);
      setName("Monthly Budget");
      setAmount("100");
      fetchBudgets();
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this budget?")) return;
    await fetch(`${API}/budgets/${id}`, { method: "DELETE" });
    fetchBudgets();
  };

  const handleToggle = async (b: any) => {
    await fetch(`${API}/budgets/${b.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !b.is_active }),
    });
    fetchBudgets();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Cost Budgets</h1>
          <p className="text-sm text-gray-500">{budgets.length} budgets in {project}</p>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="btn-primary">
          {showForm ? "Cancel" : "+ New Budget"}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="card mb-6 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Name</label>
              <input value={name} onChange={e => setName(e.target.value)} required className="input-dark" />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Period</label>
              <select value={period} onChange={e => setPeriod(e.target.value)} className="select-dark">
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Amount (USD)</label>
              <input type="number" step="0.01" value={amount} onChange={e => setAmount(e.target.value)}
                required className="input-dark" placeholder="100" />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Alert thresholds (% comma separated)</label>
              <input value={thresholds} onChange={e => setThresholds(e.target.value)}
                className="input-dark" placeholder="50, 80, 100" />
              <p className="text-[10px] text-gray-400 mt-0.5">Alerts fire when budget reaches these percentages</p>
            </div>
          </div>
          <button type="submit" className="btn-primary">Create Budget</button>
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
          {budgets.map(b => {
            const statusColor = b.status === "exceeded" ? "red" : b.status === "warning" ? "yellow" : "green";
            const barColor = statusColor === "red" ? "bg-red-500" : statusColor === "yellow" ? "bg-yellow-500" : "bg-green-500";
            return (
              <div key={b.id} className="card">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-base font-semibold text-gray-900">{b.name}</h3>
                    <p className="text-xs text-gray-500">{b.period} budget · resets {new Date(b.period_start).toLocaleDateString()}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button onClick={() => handleToggle(b)}
                      className={`text-xs px-2 py-1 rounded ${b.is_active ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                      {b.is_active ? "Active" : "Paused"}
                    </button>
                    <button onClick={() => handleDelete(b.id)} className="text-xs text-red-500 hover:text-red-600">Delete</button>
                  </div>
                </div>

                <div className="flex items-center justify-between mb-2">
                  <span className="text-2xl font-bold text-gray-900">${b.spent_usd.toFixed(4)}</span>
                  <span className="text-sm text-gray-500">of ${b.amount_usd.toFixed(2)}</span>
                </div>

                <div className="w-full bg-gray-100 rounded-full h-3 mb-2">
                  <div className={`h-3 rounded-full ${barColor} transition-all`}
                    style={{ width: `${Math.min(b.used_pct, 100)}%` }} />
                </div>

                <div className="flex items-center justify-between text-xs">
                  <span className={`font-semibold ${statusColor === "red" ? "text-red-600" : statusColor === "yellow" ? "text-yellow-600" : "text-green-600"}`}>
                    {b.used_pct.toFixed(1)}% used
                  </span>
                  <span className="text-gray-500">${b.remaining_usd.toFixed(4)} remaining</span>
                </div>

                <div className="flex gap-2 mt-3">
                  {(b.alert_thresholds || []).map((t: number) => (
                    <span key={t} className={`text-[10px] px-2 py-0.5 rounded ${
                      b.used_pct >= t ? "bg-red-100 text-red-700" : "bg-gray-100 text-gray-500"
                    }`}>
                      {t}% alert {b.used_pct >= t ? "✓" : ""}
                    </span>
                  ))}
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
