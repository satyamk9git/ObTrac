"""
Analytics API - Token usage, cost breakdown, and performance analytics.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import get_db
from app.db.models import TraceRecord, SpanRecord, LLMConfigRecord

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _period_start(period: str):
    """Convert a period name to a start datetime. None means lifetime."""
    from datetime import datetime, timedelta
    p = (period or "lifetime").lower()
    now = datetime.utcnow()
    if p == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if p == "weekly":
        days = now.weekday()  # Monday = 0
        return (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    if p == "monthly":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return None  # lifetime — no filter


@router.get("/tokens")
def get_token_analytics(
    project: str = Query("all"),
    limit: int = Query(500, le=2000),
    period: str = Query("lifetime", description="daily | weekly | monthly | lifetime"),
    db: Session = Depends(get_db),
):
    """Token usage analytics at project level."""
    query = db.query(TraceRecord)
    if project != "all":
        query = query.filter(TraceRecord.project == project)

    start = _period_start(period)
    if start is not None:
        query = query.filter(TraceRecord.created_at >= start)

    traces = query.order_by(TraceRecord.created_at.desc()).limit(limit).all()

    total_prompt = 0
    total_completion = 0
    total_cost = 0.0
    per_trace = []

    for t in traces:
        tokens = t.total_tokens or {}
        prompt = tokens.get("prompt", 0) or 0
        compl = tokens.get("completion", 0) or 0
        cost = t.total_cost_usd or 0

        # Also aggregate from spans if trace-level is 0
        if prompt == 0 and compl == 0:
            for s in t.spans:
                stok = s.tokens or {}
                prompt += stok.get("prompt", 0) or 0
                compl += stok.get("completion", 0) or 0
                cost += s.cost_usd or 0

        total_prompt += prompt
        total_completion += compl
        total_cost += cost

        per_trace.append({
            "trace_id": t.trace_id,
            "name": t.name,
            "query": (t.query or "")[:80],
            "prompt_tokens": prompt,
            "completion_tokens": compl,
            "total_tokens": prompt + compl,
            "cost_usd": round(cost, 6),
            "latency_ms": t.total_latency_ms or 0,
            "num_spans": len(t.spans),
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    return {
        "project": project,
        "period": period,
        "period_start": start.isoformat() if start else None,
        "total_traces": len(traces),
        "totals": {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "total_cost_usd": round(total_cost, 6),
            "avg_tokens_per_trace": round((total_prompt + total_completion) / max(len(traces), 1), 1),
            "avg_cost_per_trace": round(total_cost / max(len(traces), 1), 6),
        },
        "token_split": {
            "prompt_pct": round(total_prompt / max(total_prompt + total_completion, 1) * 100, 1),
            "completion_pct": round(total_completion / max(total_prompt + total_completion, 1) * 100, 1),
        },
        "per_trace": per_trace,
    }


@router.get("/tokens/by-span")
def get_token_by_span(
    trace_id: str = Query(...),
    db: Session = Depends(get_db),
):
    """Token breakdown by span within a trace."""
    spans = (
        db.query(SpanRecord)
        .filter(SpanRecord.trace_id == trace_id)
        .all()
    )

    span_data = []
    for s in spans:
        tokens = s.tokens or {}
        prompt = tokens.get("prompt", 0) or 0
        compl = tokens.get("completion", 0) or 0

        span_data.append({
            "span_id": s.span_id,
            "name": s.name,
            "span_type": s.span_type,
            "model": s.model,
            "prompt_tokens": prompt,
            "completion_tokens": compl,
            "total_tokens": prompt + compl,
            "cost_usd": round(s.cost_usd or 0, 6),
            "latency_ms": s.latency_ms or 0,
        })

    # Sort by total tokens desc
    span_data.sort(key=lambda x: x["total_tokens"], reverse=True)

    total_tokens = sum(s["total_tokens"] for s in span_data)
    total_cost = sum(s["cost_usd"] for s in span_data)

    # By span type
    by_type: dict = {}
    for s in span_data:
        t = s["span_type"]
        if t not in by_type:
            by_type[t] = {"tokens": 0, "cost": 0, "count": 0}
        by_type[t]["tokens"] += s["total_tokens"]
        by_type[t]["cost"] += s["cost_usd"]
        by_type[t]["count"] += 1

    return {
        "trace_id": trace_id,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
        "spans": span_data,
        "by_type": {
            k: {**v, "cost": round(v["cost"], 6), "pct": round(v["tokens"] / max(total_tokens, 1) * 100, 1)}
            for k, v in by_type.items()
        },
    }


@router.get("/cost/over-time")
def get_cost_over_time(
    project: str = Query("all"),
    limit: int = Query(500, le=2000),
    period: str = Query("lifetime", description="daily | weekly | monthly | lifetime"),
    db: Session = Depends(get_db),
):
    """Cost and token usage over time for charts."""
    query = db.query(TraceRecord)
    if project != "all":
        query = query.filter(TraceRecord.project == project)

    start = _period_start(period)
    if start is not None:
        query = query.filter(TraceRecord.created_at >= start)

    traces = query.order_by(TraceRecord.created_at.asc()).limit(limit).all()

    data_points = []
    running_cost = 0.0
    running_tokens = 0

    for t in traces:
        tokens = t.total_tokens or {}
        prompt = tokens.get("prompt", 0) or 0
        compl = tokens.get("completion", 0) or 0
        cost = t.total_cost_usd or 0

        # Aggregate from spans if needed
        if prompt == 0 and compl == 0:
            for s in t.spans:
                stok = s.tokens or {}
                prompt += stok.get("prompt", 0) or 0
                compl += stok.get("completion", 0) or 0
                cost += s.cost_usd or 0

        running_cost += cost
        running_tokens += prompt + compl

        data_points.append({
            "timestamp": t.created_at.isoformat() if t.created_at else None,
            "trace_id": t.trace_id,
            "tokens": prompt + compl,
            "cost": round(cost, 6),
            "cumulative_cost": round(running_cost, 6),
            "cumulative_tokens": running_tokens,
            "latency_ms": t.total_latency_ms or 0,
        })

    return {
        "project": project,
        "period": period,
        "period_start": start.isoformat() if start else None,
        "data_points": data_points,
        "total_cost": round(running_cost, 6),
        "total_tokens": running_tokens,
    }
