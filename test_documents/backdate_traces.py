"""
Spreads the generated traces across the last 10 days so Analytics/Metrics
"over time" views show a real trend instead of one timestamp. Each session
gets a distinct day; questions within a session are spaced a few minutes
apart, in original creation order.
"""
import requests
from datetime import datetime, timedelta

BACKEND = "http://localhost:8100"

r = requests.get(f"{BACKEND}/api/v1/traces", params={"project": "langgraph-agent", "limit": 500})
traces = r.json()["traces"]

# Group by "session" — recover session_id via the trace list; the list endpoint
# doesn't return session_id, so pull it per-trace detail. Traces are returned
# newest-first; reverse to get original chronological/creation order.
traces = list(reversed(traces))

detailed = []
for t in traces:
    resp = requests.get(f"{BACKEND}/api/v1/traces/{t['trace_id']}")
    detailed.append(resp.json())

# Group by session via SQL editor (session_id isn't in the /traces list response)
sql_resp = requests.post(f"{BACKEND}/api/v1/sql/execute", json={
    "query": "SELECT trace_id, session_id, created_at FROM traces WHERE project='langgraph-agent' ORDER BY created_at ASC",
})
rows = sql_resp.json()["rows"]

sessions_order = []
by_session = {}
for row in rows:
    sid = row["session_id"] or "unknown"
    if sid not in by_session:
        by_session[sid] = []
        sessions_order.append(sid)
    by_session[sid].append(row["trace_id"])

print(f"{len(sessions_order)} sessions found: {sessions_order}")

now = datetime.utcnow()
updates = 0
for day_offset, sid in enumerate(reversed(sessions_order)):  # oldest session = furthest back
    session_day = now - timedelta(days=(len(sessions_order) - 1 - day_offset), hours=day_offset % 5)
    trace_ids = by_session[sid]
    for i, tid in enumerate(trace_ids):
        ts = session_day + timedelta(minutes=i * 3)
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        upd = requests.post(f"{BACKEND}/api/v1/sql/execute", json={
            "query": (
                f"UPDATE traces SET created_at = '{ts_str}', "
                f"start_time = '{ts_str}', end_time = '{ts_str}' "
                f"WHERE trace_id = '{tid}'"
            ),
        })
        if upd.json().get("error"):
            print(f"  ERROR updating {tid}: {upd.json()['error']}")
        else:
            updates += 1

print(f"\nBackdated {updates} traces across {len(sessions_order)} sessions (spread over ~{len(sessions_order)} days).")
