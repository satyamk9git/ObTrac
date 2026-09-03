"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";

const API = "/api/v1";

function AlertsContent() {
  const searchParams = useSearchParams();
  // Alerts is now a GLOBAL feature — no longer scoped to a project.
  // The query param is still respected so existing bookmarks keep working,
  // but defaults to "all" so the page works without a project context.
  const project = searchParams.get("project") || "all";

  const [channels, setChannels] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [triggers, setTriggers] = useState<any[]>([]);
  const [tab, setTab] = useState("channels");
  const [showForm, setShowForm] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [channelBudgets, setChannelBudgets] = useState<Record<string, any[]>>({});
  // Real list of projects from the backend — used by the "Listens to project" dropdown
  const [allProjects, setAllProjects] = useState<string[]>([]);

  // Form state
  const [name, setName] = useState("");
  const [channelType, setChannelType] = useState("slack");
  const [url, setUrl] = useState("");
  const [chProject, setChProject] = useState("all");
  const [selectedTriggers, setSelectedTriggers] = useState<string[]>([]);

  const fetchAll = () => {
    Promise.all([
      fetch(`${API}/alerts/channels`).then(r => r.json()),
      fetch(`${API}/alerts/history?project=${encodeURIComponent(project)}`).then(r => r.json()),
      fetch(`${API}/alerts/triggers`).then(r => r.json()),
      fetch(`${API}/traces/projects`).then(r => r.json()),
    ]).then(async ([c, h, t, p]) => {
      const chans = c.channels || [];
      setChannels(chans);
      setHistory(h.history || []);
      setTriggers(t.triggers || []);
      setAllProjects((p.projects || []).map((x: any) => x.name).sort());

      // Fetch budgets for each channel in parallel — used for the
      // "Subscribed by N budgets" badge.
      const budgetMap: Record<string, any[]> = {};
      await Promise.all(
        chans.map(async (ch: any) => {
          try {
            const r = await fetch(`${API}/alerts/channels/${ch.id}/budgets`);
            if (r.ok) {
              const d = await r.json();
              budgetMap[ch.id] = d.budgets || [];
            }
          } catch {}
        })
      );
      setChannelBudgets(budgetMap);
    }).catch(() => {});
  };

  useEffect(() => { fetchAll(); }, [project]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const res = await fetch(`${API}/alerts/channels`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        channel_type: channelType,
        config: { url },
        project: chProject,
        triggers: selectedTriggers,
      }),
    });
    if (res.ok) {
      setShowForm(false);
      setName(""); setUrl(""); setSelectedTriggers([]);
      fetchAll();
    }
  };

  const handleTest = async (id: string) => {
    setTestResult({ id, loading: true });
    const res = await fetch(`${API}/alerts/channels/${id}/test`, { method: "POST" });
    const data = await res.json();
    setTestResult({ id, ...data });
    setTimeout(() => fetchAll(), 1000);
  };

  const handleDelete = async (id: string) => {
    const subscribedBudgets = channelBudgets[id] || [];
    let prompt = "Delete this channel?";
    if (subscribedBudgets.length > 0) {
      const budgetNames = subscribedBudgets.map((b) => `• ${b.name} (${b.project})`).join("\n");
      prompt = `This channel is used by ${subscribedBudgets.length} budget${subscribedBudgets.length !== 1 ? "s" : ""}:\n\n${budgetNames}\n\nDeleting will unmap it from those budgets. Continue?`;
    }
    if (!confirm(prompt)) return;
    await fetch(`${API}/alerts/channels/${id}`, { method: "DELETE" });
    fetchAll();
  };

  const toggleTrigger = (id: string) => {
    setSelectedTriggers(prev => prev.includes(id) ? prev.filter(t => t !== id) : [...prev, id]);
  };

  const TABS = [
    { id: "channels", label: `Channels (${channels.length})` },
    { id: "history", label: `History (${history.length})` },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Alerts</h1>
          <p className="text-sm text-gray-500">
            Globally-shared webhook and Slack channels. Map them to specific budgets in the Budgets page.
          </p>
        </div>
        {tab === "channels" && (
          <button onClick={() => setShowForm(!showForm)} className="btn-primary">
            {showForm ? "Cancel" : "+ New Channel"}
          </button>
        )}
      </div>

      <div className="flex gap-1 mb-6 border-b border-gray-200">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t.id ? "border-indigo-600 text-indigo-600" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ============ CHANNELS ============ */}
      {tab === "channels" && (
        <>
          {showForm && (
            <form onSubmit={handleCreate} className="card mb-6 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">
                    Channel Name <span className="text-gray-400 font-normal">— use the same Slack channel name the webhook URL was created for</span>
                  </label>
                  <input value={name} onChange={e => setName(e.target.value)} required
                    className="input-dark" placeholder="#all-obtrac" />
                  <p className="text-[10px] text-gray-400 mt-1">
                    This is just a display label so you can identify which channel each URL points to. It does NOT change where messages are delivered.
                  </p>
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Type</label>
                  <select value={channelType} onChange={e => setChannelType(e.target.value)} className="select-dark">
                    <option value="slack">Slack</option>
                    <option value="webhook">Generic Webhook</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-600 mb-1">
                  {channelType === "slack" ? "Slack Incoming Webhook URL" : "Webhook URL"}
                </label>
                <input value={url} onChange={e => setUrl(e.target.value)} required
                  className="input-dark" placeholder={channelType === "slack" ? "https://hooks.slack.com/services/..." : "https://your-webhook.com/alerts"} />
              </div>
              <div>
                <label className="block text-xs text-gray-600 mb-1">Listens to project</label>
                <select
                  value={chProject}
                  onChange={(e) => setChProject(e.target.value)}
                  className="select-dark"
                >
                  <option value="all">All projects</option>
                  {allProjects.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
                <p className="text-[10px] text-gray-400 mt-1">
                  Filters non-budget events (errors, metric drops, failed traces). Budgets are mapped explicitly via the Budgets page → no need to filter them here.
                </p>
              </div>
              <div>
                <label className="block text-xs text-gray-600 mb-2">Trigger Events (non-budget)</label>
                <div className="grid grid-cols-2 gap-2">
                  {triggers
                    .filter((t: any) => !t.id.startsWith("budget_"))
                    .map((t: any) => (
                      <label key={t.id} className={`flex items-center gap-2 p-2 rounded cursor-pointer transition-colors ${
                        selectedTriggers.includes(t.id) ? "bg-indigo-50 border border-indigo-300" : "hover:bg-gray-50 border border-transparent"
                      }`}>
                        <input type="checkbox" checked={selectedTriggers.includes(t.id)}
                          onChange={() => toggleTrigger(t.id)} className="w-4 h-4" />
                        <span className="text-xs font-mono text-indigo-600">{t.id}</span>
                        <span className="text-xs text-gray-600">{t.label}</span>
                      </label>
                    ))}
                </div>
                <p className="text-[10px] text-gray-400 mt-2">
                  💡 Budget alerts (50%, 80%, 100%) are now configured per-budget on the Budgets page — no need to set them here.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button type="submit" className="btn-primary">Create Channel</button>
                <p className="text-[11px] text-gray-500">
                  💡 After creating, click <strong>Send Test</strong> on the channel card to verify the webhook URL actually delivers a message.
                </p>
              </div>
            </form>
          )}

          {channels.length === 0 ? (
            <div className="card text-center py-16">
              <h3 className="text-lg font-semibold text-gray-700 mb-2">No alert channels yet</h3>
              <p className="text-sm text-gray-500 max-w-md mx-auto">
                Add a Slack or webhook channel to get notified when budgets are exceeded, metrics drop, or errors spike.
              </p>
              <p className="text-xs text-gray-400 mt-3">
                Get a Slack webhook URL: <a href="https://api.slack.com/messaging/webhooks" target="_blank" className="text-indigo-600 underline">api.slack.com</a>
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {channels.map(c => {
                const subBudgets = channelBudgets[c.id] || [];
                return (
                <div key={c.id} className="card">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <span className={`badge ${c.channel_type === "slack" ? "badge-purple" : "badge-info"}`}>
                        {c.channel_type}
                      </span>
                      <h3 className="text-sm font-semibold text-gray-900">{c.name}</h3>
                      <span className="text-xs text-gray-500">project: {c.project}</span>
                      {c.is_active ? <span className="badge badge-success">Active</span> : <span className="badge badge-warning">Paused</span>}
                      {subBudgets.length > 0 && (
                        <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 bg-indigo-100 text-indigo-700 rounded">
                          📢 {subBudgets.length} budget{subBudgets.length !== 1 ? "s" : ""}
                        </span>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleTest(c.id)}
                        className="text-xs px-3 py-1.5 rounded border border-purple-300 text-purple-700 hover:bg-purple-50 font-medium flex items-center gap-1"
                        title="Send a test alert through this channel to verify the URL works"
                      >
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Send Test
                      </button>
                      <button onClick={() => handleDelete(c.id)} className="text-xs text-red-500 hover:text-red-600">Delete</button>
                    </div>
                  </div>
                  <p className="text-[10px] font-mono text-gray-500 truncate mb-2">{c.config?.url}</p>
                  <div className="flex gap-1 flex-wrap">
                    {(c.triggers || []).map((t: string) => (
                      <span key={t} className="text-[10px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">{t}</span>
                    ))}
                  </div>

                  {/* Subscribed budgets list */}
                  {subBudgets.length > 0 && (
                    <div className="mt-3 border-t border-gray-100 pt-2">
                      <p className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Subscribed by:</p>
                      <div className="flex flex-wrap gap-1.5">
                        {subBudgets.map((b: any) => (
                          <span key={b.id} className="text-[11px] bg-indigo-50 border border-indigo-200 text-indigo-700 px-2 py-0.5 rounded">
                            {b.name} <span className="text-[9px] text-indigo-500">({b.project})</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {testResult?.id === c.id && (
                    <div className={`mt-2 p-2 rounded text-xs ${
                      testResult.delivered ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"
                    }`}>
                      {testResult.loading ? "Sending test..." :
                       testResult.delivered ? `✓ Delivered (status ${testResult.status})` :
                       `✗ Failed: ${testResult.error || "unknown error"}`}
                    </div>
                  )}
                </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* ============ HISTORY ============ */}
      {tab === "history" && (
        <div className="card p-0 overflow-hidden">
          <table className="table-dark">
            <thead>
              <tr>
                <th>Event</th>
                <th>Severity</th>
                <th>Message</th>
                <th>Delivered</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {history.length === 0 ? (
                <tr><td colSpan={5} className="text-center py-8 text-gray-400">No alert history yet</td></tr>
              ) : history.map(h => (
                <tr key={h.id}>
                  <td><span className="font-mono text-xs text-indigo-600">{h.event_type}</span></td>
                  <td>
                    <span className={`badge ${
                      h.severity === "critical" ? "badge-error" :
                      h.severity === "warning" ? "badge-warning" : "badge-info"
                    }`}>{h.severity}</span>
                  </td>
                  <td className="text-xs text-gray-700 max-w-md truncate">{h.message}</td>
                  <td>
                    {h.delivered ? <span className="text-green-600 text-xs">✓ ({h.response_status})</span> :
                                   <span className="text-red-500 text-xs">✗ {h.error?.substring(0, 30)}</span>}
                  </td>
                  <td className="text-[10px] text-gray-500">{h.created_at ? new Date(h.created_at).toLocaleString() : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function AlertsPage() {
  return <Suspense fallback={<div className="text-gray-500">Loading...</div>}><AlertsContent /></Suspense>;
}
