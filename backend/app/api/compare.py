"""
Trace Comparison API — Side-by-side diff of two traces.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import TraceRecord

router = APIRouter(prefix="/compare", tags=["compare"])


@router.get("")
def compare_traces(
    trace_a: str = Query(...),
    trace_b: str = Query(...),
    db: Session = Depends(get_db),
):
    """Compare two traces side-by-side."""
    a = db.query(TraceRecord).filter(TraceRecord.trace_id == trace_a).first()
    b = db.query(TraceRecord).filter(TraceRecord.trace_id == trace_b).first()

    if not a:
        raise HTTPException(404, f"Trace A not found: {trace_a}")
    if not b:
        raise HTTPException(404, f"Trace B not found: {trace_b}")

    def trace_to_dict(t):
        return {
            "trace_id": t.trace_id,
            "project": t.project,
            "name": t.name,
            "user": t.user or "",
            "status": t.status,
            "query": t.query or "",
            "answer": t.answer or "",
            "context": (t.context or "")[:1000],
            "ground_truth": t.ground_truth,
            "total_latency_ms": t.total_latency_ms or 0,
            "total_cost_usd": t.total_cost_usd or 0,
            "total_tokens": t.total_tokens or {},
            "metrics": t.metrics or {},
            "suggestions": t.suggestions or [],
            "num_spans": len(t.spans),
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "spans": [
                {
                    "name": s.name,
                    "span_type": s.span_type,
                    "model": s.model,
                    "latency_ms": s.latency_ms or 0,
                    "tokens": s.tokens or {},
                    "cost_usd": s.cost_usd or 0,
                    "status": s.status,
                }
                for s in t.spans
            ],
        }

    da = trace_to_dict(a)
    db_dict = trace_to_dict(b)

    # Compute diffs
    diffs = {}
    # Metric diffs
    all_metrics = set(list(da["metrics"].keys()) + list(db_dict["metrics"].keys()))
    metric_diffs = {}
    for m in all_metrics:
        va = da["metrics"].get(m)
        vb = db_dict["metrics"].get(m)
        metric_diffs[m] = {
            "a": va,
            "b": vb,
            "delta": round(vb - va, 4) if va is not None and vb is not None else None,
            "winner": "b" if va is not None and vb is not None and vb > va else "a" if va is not None and vb is not None and va > vb else "tie",
        }
    diffs["metrics"] = metric_diffs

    # Performance diffs
    diffs["latency"] = {
        "a": da["total_latency_ms"],
        "b": db_dict["total_latency_ms"],
        "delta": round(db_dict["total_latency_ms"] - da["total_latency_ms"], 1),
        "winner": "a" if da["total_latency_ms"] < db_dict["total_latency_ms"] else "b",
    }
    diffs["cost"] = {
        "a": da["total_cost_usd"],
        "b": db_dict["total_cost_usd"],
        "delta": round(db_dict["total_cost_usd"] - da["total_cost_usd"], 6),
        "winner": "a" if da["total_cost_usd"] < db_dict["total_cost_usd"] else "b",
    }
    diffs["spans"] = {
        "a": da["num_spans"],
        "b": db_dict["num_spans"],
    }
    diffs["same_query"] = da["query"].strip().lower() == db_dict["query"].strip().lower()
    diffs["same_answer"] = da["answer"].strip() == db_dict["answer"].strip()

    return {
        "trace_a": da,
        "trace_b": db_dict,
        "diffs": diffs,
    }
