"""
SQL Editor API - Execute genuinely read-only SQL queries against the ObTrac
database.

Read-only is enforced at the database driver/server level, not by
pattern-matching the query text — a keyword blocklist can always be
bypassed by rephrasing (CTEs, PRAGMA tricks, ATTACH DATABASE to write
elsewhere, etc.). On SQLite the file itself is opened with SQLite's own
`mode=ro` URI flag; on Postgres the connection is opened with
`postgresql_readonly=True`, which Postgres enforces server-side
(`SET TRANSACTION READ ONLY`) — either way, a write attempt fails at the
database itself regardless of how the SQL is phrased.
"""

import os
from fastapi import APIRouter
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from pydantic import BaseModel

from app.db.database import DATABASE_DIR, DATABASE_URL, IS_SQLITE

router = APIRouter(prefix="/sql", tags=["sql-editor"])

_DB_PATH = os.path.join(DATABASE_DIR, "obtrac.db")
_readonly_engine: Engine | None = None


def _get_readonly_engine() -> Engine:
    """
    Lazily create the read-only engine on first use (not at module import
    time) — the database file may not exist yet when this router is
    imported at app startup, and SQLite's mode=ro cannot open a
    not-yet-created file.
    """
    global _readonly_engine
    if _readonly_engine is None:
        if IS_SQLITE:
            readonly_url = f"sqlite:///file:{_DB_PATH}?mode=ro&uri=true"
            _readonly_engine = create_engine(readonly_url, connect_args={"check_same_thread": False})
        else:
            # Postgres (or any other SQLAlchemy dialect): enforce read-only
            # at the server via the transaction characteristic, not just in
            # this process. Any write raises a server-side error.
            _readonly_engine = create_engine(DATABASE_URL, execution_options={"postgresql_readonly": True})
    return _readonly_engine


class SQLQuery(BaseModel):
    query: str
    limit: int = 100


@router.get("/schema")
def get_schema():
    """Get all table names and their columns."""
    engine = _get_readonly_engine()
    with engine.connect() as conn:
        tables_raw = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")).fetchall()
        tables = []
        for (tname,) in tables_raw:
            if tname.startswith("sqlite_") or tname.startswith("_"):
                continue
            cols_raw = conn.execute(text(f"PRAGMA table_info('{tname}')")).fetchall()
            columns = [{"name": c[1], "type": c[2], "nullable": not c[3], "pk": bool(c[5])} for c in cols_raw]
            count = conn.execute(text(f"SELECT COUNT(*) FROM '{tname}'")).scalar()
            tables.append({"name": tname, "columns": columns, "row_count": count})
    return {"tables": tables}


@router.post("/execute")
def execute_sql(req: SQLQuery):
    """Execute a read-only SQL query. Any write attempt fails at the SQLite
    driver level (the connection itself is opened read-only), not via
    keyword filtering."""
    query = req.query.strip()

    if not query:
        return {"error": "Empty query", "rows": [], "columns": []}

    first_word = query.split()[0].lower() if query.split() else ""
    query_lower = query.lower()

    # Add LIMIT only for SELECT queries — a friendliness nicety, not a
    # security control (the real guarantee is the read-only connection).
    if first_word == "select" and "limit" not in query_lower:
        query = f"{query} LIMIT {req.limit}"

    engine = _get_readonly_engine()
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query))
            if result.returns_rows:
                columns = list(result.keys())
                rows = [dict(zip(columns, row)) for row in result.fetchall()]
                return {"columns": columns, "rows": rows, "row_count": len(rows), "query": req.query}
            return {
                "columns": [],
                "rows": [],
                "row_count": 0,
                "query": req.query,
                "message": "Statement executed (no rows returned).",
            }
    except Exception as e:
        msg = str(e)
        lowered = msg.lower()
        if any(s in lowered for s in ("readonly database", "attempt to write", "read-only transaction", "read only transaction")):
            return {
                "error": "Write operations are not allowed — the SQL Editor connects to the database read-only. "
                         "Use the SQL Editor's own value only for querying data.",
                "rows": [], "columns": [],
            }
        return {"error": msg, "rows": [], "columns": []}


@router.get("/examples")
def get_example_queries():
    """Get example SQL queries."""
    return {
        "examples": [
            {
                "name": "All traces",
                "query": "SELECT trace_id, project, name, query, status, total_latency_ms, total_cost_usd, created_at FROM traces ORDER BY created_at DESC LIMIT 20",
            },
            {
                "name": "Traces by user",
                "query": "SELECT trace_id, user, query, status, total_latency_ms FROM traces WHERE user != '' ORDER BY created_at DESC",
            },
            {
                "name": "Avg latency by project",
                "query": "SELECT project, COUNT(*) as traces, ROUND(AVG(total_latency_ms), 0) as avg_latency_ms, ROUND(SUM(total_cost_usd), 6) as total_cost FROM traces GROUP BY project",
            },
            {
                "name": "Slowest traces",
                "query": "SELECT trace_id, query, total_latency_ms, total_cost_usd FROM traces ORDER BY total_latency_ms DESC LIMIT 10",
            },
            {
                "name": "Spans by type",
                "query": "SELECT span_type, COUNT(*) as count, ROUND(AVG(latency_ms), 0) as avg_latency FROM spans GROUP BY span_type ORDER BY count DESC",
            },
            {
                "name": "Generation spans with models",
                "query": "SELECT name, model, COUNT(*) as calls, ROUND(AVG(latency_ms), 0) as avg_latency FROM spans WHERE span_type='generation' GROUP BY name, model",
            },
            {
                "name": "LLM configs",
                "query": "SELECT name, provider, model_id, role, is_active, cost_per_1k_prompt, cost_per_1k_completion FROM llm_configs",
            },
            {
                "name": "Ground truth datasets",
                "query": "SELECT dataset_name, COUNT(*) as records FROM ground_truths GROUP BY dataset_name",
            },
            {
                "name": "Traces with metrics",
                "query": "SELECT trace_id, query, metrics, suggestions FROM traces WHERE metrics IS NOT NULL AND metrics != '{}' ORDER BY created_at DESC LIMIT 10",
            },
            {
                "name": "Error traces",
                "query": "SELECT trace_id, query, created_at FROM traces WHERE status='error' ORDER BY created_at DESC",
            },
        ]
    }
