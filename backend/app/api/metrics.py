"""
Metrics API - Aggregated RAGAS metrics, trends, comparisons, and analytics.
"""

import math
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
import csv
import io
import json

from app.db.database import get_db
from app.db.models import TraceRecord, GroundTruthRecord

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _safe_float(v):
    """Return float or None if NaN/Inf."""
    if v is None:
        return None
    f = float(v)
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 4)


def _get_filtered_traces(db, project, date_from=None, date_to=None, limit=200):
    """Get traces with optional date filter."""
    q = db.query(TraceRecord).filter(TraceRecord.project == project)
    if date_from:
        q = q.filter(TraceRecord.created_at >= datetime.fromisoformat(date_from))
    if date_to:
        q = q.filter(TraceRecord.created_at <= datetime.fromisoformat(date_to))
    return q.order_by(TraceRecord.created_at.desc()).limit(limit).all()


# ========================================
# SUMMARY
# ========================================

@router.get("/summary")
def get_metrics_summary(
    project: str = Query("default"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
):
    """Get aggregated metrics summary with optional date filter."""
    traces = _get_filtered_traces(db, project, date_from, date_to, limit)

    if not traces:
        return {"project": project, "total_traces": 0, "avg_metrics": {}, "metrics_over_time": []}

    # Aggregate metrics
    metric_totals: dict[str, list[float]] = {}
    for trace in traces:
        if trace.metrics:
            for key, value in trace.metrics.items():
                v = _safe_float(value)
                if v is not None:
                    metric_totals.setdefault(key, []).append(v)

    avg_metrics = {
        key: round(sum(values) / len(values), 4)
        for key, values in metric_totals.items()
        if values
    }

    # Metrics over time (for charts)
    metrics_over_time = [
        {
            "trace_id": t.trace_id,
            "timestamp": t.created_at.isoformat() if t.created_at else None,
            "metrics": {k: _safe_float(v) for k, v in (t.metrics or {}).items()},
            "latency_ms": t.total_latency_ms or 0,
            "cost_usd": t.total_cost_usd or 0,
        }
        for t in traces
    ]

    total_cost = sum(t.total_cost_usd or 0 for t in traces)
    avg_latency = sum(t.total_latency_ms or 0 for t in traces) / len(traces)
    total_tokens = sum(sum((t.total_tokens or {}).values()) for t in traces)

    return {
        "project": project,
        "total_traces": len(traces),
        "avg_metrics": avg_metrics,
        "metrics_over_time": metrics_over_time,
        "cost_stats": {
            "total_cost_usd": round(total_cost, 6),
            "avg_cost_per_trace": round(total_cost / len(traces), 6),
            "total_tokens": total_tokens,
        },
        "performance_stats": {
            "avg_latency_ms": round(avg_latency, 2),
            "min_latency_ms": min(t.total_latency_ms or 0 for t in traces),
            "max_latency_ms": max(t.total_latency_ms or 0 for t in traces),
        },
    }


# ========================================
# PER-QUERY BREAKDOWN
# ========================================

@router.get("/per-query")
def get_per_query_metrics(
    project: str = Query("default"),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    """Per-query metric breakdown — every trace with all its scores."""
    traces = _get_filtered_traces(db, project, date_from, date_to, limit)

    # Collect all metric names
    all_metric_names = set()
    for t in traces:
        if t.metrics:
            all_metric_names.update(t.metrics.keys())

    rows = []
    for t in traces:
        metrics = {}
        for m in all_metric_names:
            metrics[m] = _safe_float((t.metrics or {}).get(m))

        # Compute avg score across all metrics for this trace
        valid_scores = [v for v in metrics.values() if v is not None]
        avg_score = round(sum(valid_scores) / len(valid_scores), 4) if valid_scores else None

        rows.append({
            "trace_id": t.trace_id,
            "query": t.query or "",
            "answer": (t.answer or "")[:200],
            "name": t.name or "",
            "status": t.status,
            "metrics": metrics,
            "avg_score": avg_score,
            "latency_ms": t.total_latency_ms or 0,
            "cost_usd": t.total_cost_usd or 0,
            "num_spans": len(t.spans),
            "has_ground_truth": bool(t.ground_truth),
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    # Sort
    if sort_by == "avg_score":
        rows.sort(key=lambda x: x["avg_score"] or 0, reverse=(sort_order == "desc"))
    elif sort_by == "latency_ms":
        rows.sort(key=lambda x: x["latency_ms"], reverse=(sort_order == "desc"))

    return {
        "project": project,
        "total": len(rows),
        "metric_names": sorted(all_metric_names),
        "rows": rows,
    }


# ========================================
# WORST PERFORMING TRACES
# ========================================

@router.get("/worst")
def get_worst_traces(
    project: str = Query("default"),
    metric: str = Query("faithfulness"),
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db),
):
    """Get traces with the lowest scores for a specific metric."""
    traces = (
        db.query(TraceRecord)
        .filter(TraceRecord.project == project)
        .filter(TraceRecord.metrics != None)
        .all()
    )

    scored = []
    for t in traces:
        if t.metrics and metric in t.metrics:
            score = _safe_float(t.metrics[metric])
            if score is not None:
                scored.append({
                    "trace_id": t.trace_id,
                    "query": (t.query or "")[:150],
                    "answer": (t.answer or "")[:150],
                    "score": score,
                    "all_metrics": {k: _safe_float(v) for k, v in t.metrics.items()},
                    "suggestions": t.suggestions or [],
                    "latency_ms": t.total_latency_ms or 0,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                })

    scored.sort(key=lambda x: x["score"])
    return {
        "metric": metric,
        "total": len(scored),
        "worst": scored[:limit],
        "best": scored[-limit:][::-1] if scored else [],
    }


# ========================================
# METRIC COMPARISON (BEFORE/AFTER)
# ========================================

@router.get("/compare")
def compare_metrics(
    project: str = Query("default"),
    period_a_from: str = Query(...),
    period_a_to: str = Query(...),
    period_b_from: str = Query(...),
    period_b_to: str = Query(...),
    db: Session = Depends(get_db),
):
    """Compare metrics between two time periods (A/B)."""
    traces_a = _get_filtered_traces(db, project, period_a_from, period_a_to)
    traces_b = _get_filtered_traces(db, project, period_b_from, period_b_to)

    def aggregate(traces):
        totals: dict[str, list[float]] = {}
        for t in traces:
            if t.metrics:
                for k, v in t.metrics.items():
                    val = _safe_float(v)
                    if val is not None:
                        totals.setdefault(k, []).append(val)
        return {
            k: round(sum(v) / len(v), 4)
            for k, v in totals.items() if v
        }

    avg_a = aggregate(traces_a)
    avg_b = aggregate(traces_b)

    all_metrics = sorted(set(list(avg_a.keys()) + list(avg_b.keys())))

    comparison = []
    for m in all_metrics:
        a_val = avg_a.get(m)
        b_val = avg_b.get(m)
        delta = None
        if a_val is not None and b_val is not None:
            delta = round(b_val - a_val, 4)

        comparison.append({
            "metric": m,
            "period_a": a_val,
            "period_b": b_val,
            "delta": delta,
            "improved": delta > 0 if delta is not None else None,
        })

    return {
        "period_a": {"from": period_a_from, "to": period_a_to, "traces": len(traces_a)},
        "period_b": {"from": period_b_from, "to": period_b_to, "traces": len(traces_b)},
        "comparison": comparison,
    }


# ========================================
# METRIC CORRELATION
# ========================================

@router.get("/correlation")
def get_metric_correlation(
    project: str = Query("default"),
    db: Session = Depends(get_db),
):
    """Compute correlation between metrics (which metrics move together)."""
    traces = (
        db.query(TraceRecord)
        .filter(TraceRecord.project == project)
        .filter(TraceRecord.metrics != None)
        .all()
    )

    # Collect all metric names and values
    all_metrics = set()
    for t in traces:
        if t.metrics:
            all_metrics.update(t.metrics.keys())

    metric_names = sorted(all_metrics)

    # Build value arrays
    values: dict[str, list[float]] = {m: [] for m in metric_names}
    valid_traces = []
    for t in traces:
        if t.metrics and len(t.metrics) >= 2:
            valid_traces.append(t)
            for m in metric_names:
                v = _safe_float((t.metrics or {}).get(m))
                values[m].append(v if v is not None else 0)

    # Compute Pearson correlation
    def pearson(x, y):
        n = len(x)
        if n < 3:
            return None
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
        std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
        if std_x == 0 or std_y == 0:
            return None
        return round(cov / (std_x * std_y), 4)

    matrix = {}
    for m1 in metric_names:
        matrix[m1] = {}
        for m2 in metric_names:
            if m1 == m2:
                matrix[m1][m2] = 1.0
            else:
                matrix[m1][m2] = pearson(values[m1], values[m2])

    return {
        "metric_names": metric_names,
        "matrix": matrix,
        "sample_size": len(valid_traces),
    }


# ========================================
# MODEL COMPARISON
# ========================================

@router.get("/by-model")
def get_metrics_by_model(
    project: str = Query("default"),
    db: Session = Depends(get_db),
):
    """Compare metrics grouped by model (from span data)."""
    traces = (
        db.query(TraceRecord)
        .filter(TraceRecord.project == project)
        .all()
    )

    model_data: dict[str, dict] = {}
    for t in traces:
        # Find model from generation spans
        model_name = None
        for s in t.spans:
            if s.span_type == "generation" and s.model:
                model_name = s.model
                break

        if not model_name:
            model_name = "unknown"

        if model_name not in model_data:
            model_data[model_name] = {
                "traces": 0,
                "metric_totals": {},
                "total_latency": 0,
                "total_cost": 0,
                "total_tokens": 0,
            }

        md = model_data[model_name]
        md["traces"] += 1
        md["total_latency"] += t.total_latency_ms or 0
        md["total_cost"] += t.total_cost_usd or 0

        tokens = t.total_tokens or {}
        md["total_tokens"] += sum(tokens.values())

        if t.metrics:
            for k, v in t.metrics.items():
                val = _safe_float(v)
                if val is not None:
                    md["metric_totals"].setdefault(k, []).append(val)

    result = []
    for model, data in model_data.items():
        avg_metrics = {
            k: round(sum(v) / len(v), 4)
            for k, v in data["metric_totals"].items() if v
        }
        result.append({
            "model": model,
            "traces": data["traces"],
            "avg_metrics": avg_metrics,
            "avg_latency_ms": round(data["total_latency"] / max(data["traces"], 1), 1),
            "total_cost_usd": round(data["total_cost"], 6),
            "total_tokens": data["total_tokens"],
        })

    return {"models": result}


# ========================================
# GROUND TRUTH COVERAGE
# ========================================

@router.get("/ground-truth-coverage")
def get_ground_truth_coverage(
    project: str = Query("default"),
    db: Session = Depends(get_db),
):
    """Show what % of traces have ground truth."""
    total = db.query(func.count(TraceRecord.trace_id)).filter(
        TraceRecord.project == project
    ).scalar() or 0

    with_gt = db.query(func.count(TraceRecord.trace_id)).filter(
        TraceRecord.project == project,
        TraceRecord.ground_truth != None,
        TraceRecord.ground_truth != "",
    ).scalar() or 0

    # Count ground truth records in resources
    gt_records = db.query(func.count(GroundTruthRecord.id)).filter(
        GroundTruthRecord.project == project
    ).scalar() or 0

    return {
        "total_traces": total,
        "traces_with_ground_truth": with_gt,
        "coverage_pct": round(with_gt / max(total, 1) * 100, 1),
        "ground_truth_records_in_resources": gt_records,
    }


# ========================================
# DISTRIBUTION
# ========================================

@router.get("/distribution")
def get_metric_distribution(
    project: str = Query("default"),
    metric_name: str = Query("faithfulness"),
    db: Session = Depends(get_db),
):
    """Get distribution of a specific metric across traces."""
    traces = (
        db.query(TraceRecord)
        .filter(TraceRecord.project == project)
        .filter(TraceRecord.metrics != None)
        .all()
    )

    values = []
    for trace in traces:
        if trace.metrics and metric_name in trace.metrics:
            v = _safe_float(trace.metrics[metric_name])
            if v is not None:
                values.append({
                    "trace_id": trace.trace_id,
                    "value": v,
                    "query": trace.query[:100] if trace.query else "",
                    "timestamp": trace.created_at.isoformat() if trace.created_at else None,
                })

    buckets = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
    for v in values:
        score = v["value"]
        if score < 0.2: buckets["0.0-0.2"] += 1
        elif score < 0.4: buckets["0.2-0.4"] += 1
        elif score < 0.6: buckets["0.4-0.6"] += 1
        elif score < 0.8: buckets["0.6-0.8"] += 1
        else: buckets["0.8-1.0"] += 1

    return {
        "metric_name": metric_name,
        "total": len(values),
        "avg": round(sum(v["value"] for v in values) / len(values), 4) if values else 0,
        "distribution": buckets,
        "values": values,
    }


# ========================================
# EXPORT
# ========================================

@router.get("/export")
def export_metrics(
    project: str = Query("default"),
    format: str = Query("csv"),
    db: Session = Depends(get_db),
):
    """Export all metrics as CSV or JSON."""
    traces = (
        db.query(TraceRecord)
        .filter(TraceRecord.project == project)
        .order_by(TraceRecord.created_at.desc())
        .limit(500)
        .all()
    )

    all_metrics = set()
    for t in traces:
        if t.metrics:
            all_metrics.update(t.metrics.keys())
    metric_names = sorted(all_metrics)

    rows = []
    for t in traces:
        row = {
            "trace_id": t.trace_id,
            "query": t.query or "",
            "answer": (t.answer or "")[:500],
            "status": t.status,
            "latency_ms": t.total_latency_ms or 0,
            "cost_usd": t.total_cost_usd or 0,
            "created_at": t.created_at.isoformat() if t.created_at else "",
        }
        for m in metric_names:
            row[m] = _safe_float((t.metrics or {}).get(m))
        rows.append(row)

    if format == "json":
        return {"rows": rows, "metric_names": metric_names}

    # CSV
    output = io.StringIO()
    fieldnames = ["trace_id", "query", "answer", "status", "latency_ms", "cost_usd", "created_at"] + metric_names
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=obtrac_metrics_{project}.csv"},
    )
