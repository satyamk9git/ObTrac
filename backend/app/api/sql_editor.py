"""
SQL Editor API - Execute read-only SQL queries against the ObTrac database.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from app.db.database import get_db

router = APIRouter(prefix="/sql", tags=["sql-editor"])


class SQLQuery(BaseModel):
    query: str
    limit: int = 100


BLOCKED_KEYWORDS = {"drop"}


@router.get("/schema")
def get_schema(db: Session = Depends(get_db)):
    """Get all table names and their columns."""
    tables_raw = db.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")).fetchall()
    tables = []
    for (tname,) in tables_raw:
        if tname.startswith("sqlite_") or tname.startswith("_"):
            continue
        cols_raw = db.execute(text(f"PRAGMA table_info('{tname}')")).fetchall()
        columns = [{"name": c[1], "type": c[2], "nullable": not c[3], "pk": bool(c[5])} for c in cols_raw]
        count = db.execute(text(f"SELECT COUNT(*) FROM '{tname}'")).scalar()
        tables.append({"name": tname, "columns": columns, "row_count": count})
    return {"tables": tables}


@router.post("/execute")
def execute_sql(req: SQLQuery, db: Session = Depends(get_db)):
    """Execute a read-only SQL query."""
    query = req.query.strip()

    if not query:
        return {"error": "Empty query", "rows": [], "columns": []}

    # Block write operations
    first_word = query.split()[0].lower() if query.split() else ""
    if first_word in BLOCKED_KEYWORDS:
        return {"error": f"Write operation '{first_word.upper()}' not allowed. Read-only access.", "rows": [], "columns": []}

    # Also check for write keywords anywhere (e.g., subqueries)
    query_lower = query.lower()
    for kw in BLOCKED_KEYWORDS:
        if f" {kw} " in f" {query_lower} ":
            return {"error": f"'{kw.upper()}' not allowed. Read-only access.", "rows": [], "columns": []}

    # Add LIMIT only for SELECT queries
    if first_word == "select" and "limit" not in query_lower:
        query = f"{query} LIMIT {req.limit}"

    try:
        result = db.execute(text(query))

        if result.returns_rows:
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
            return {"columns": columns, "rows": rows, "row_count": len(rows), "query": req.query}
        else:
            # Write operation — commit and return affected rows
            db.commit()
            affected = result.rowcount
            return {
                "columns": ["affected_rows"],
                "rows": [{"affected_rows": affected}],
                "row_count": 1,
                "query": req.query,
                "message": f"{affected} row(s) affected",
            }
    except Exception as e:
        db.rollback()
        return {"error": str(e), "rows": [], "columns": []}


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
