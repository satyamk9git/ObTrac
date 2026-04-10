"""
Suggestions API - Returns improvement suggestions based on metrics.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import TraceRecord
from obtrac_sdk.evaluator import SuggestionEngine

router = APIRouter(prefix="/suggestions", tags=["suggestions"])

suggestion_engine = SuggestionEngine()


@router.get("")
def get_suggestions(
    project: str = Query("default"),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """Get aggregated suggestions for a project based on recent traces."""
    traces = (
        db.query(TraceRecord)
        .filter(TraceRecord.project == project)
        .filter(TraceRecord.metrics != None)
        .order_by(TraceRecord.created_at.desc())
        .limit(limit)
        .all()
    )

    if not traces:
        return {"project": project, "suggestions": [], "problem_areas": []}

    # Collect all metrics
    metric_aggregates: dict[str, list[float]] = {}
    per_trace_suggestions = []

    for trace in traces:
        if trace.metrics:
            for key, value in trace.metrics.items():
                metric_aggregates.setdefault(key, []).append(value)

            # Generate suggestions for each trace
            suggestions = suggestion_engine.generate_suggestions(trace.metrics)
            if suggestions and "performing well" not in suggestions[0]:
                per_trace_suggestions.append(
                    {
                        "trace_id": trace.trace_id,
                        "query": trace.query[:100] if trace.query else "",
                        "suggestions": suggestions,
                        "metrics": trace.metrics,
                    }
                )

    # Identify problem areas (metrics consistently below threshold)
    problem_areas = []
    for metric_name, values in metric_aggregates.items():
        avg = sum(values) / len(values)
        rule = suggestion_engine.RULES.get(metric_name)
        if rule and avg < rule["threshold"]:
            problem_areas.append(
                {
                    "metric": metric_name,
                    "avg_score": round(avg, 4),
                    "threshold": rule["threshold"],
                    "num_traces_below": sum(
                        1 for v in values if v < rule["threshold"]
                    ),
                    "total_traces": len(values),
                    "suggestion": rule["low_suggestion"],
                }
            )

    # Sort by severity (lowest avg score first)
    problem_areas.sort(key=lambda x: x["avg_score"])

    return {
        "project": project,
        "total_traces_analyzed": len(traces),
        "problem_areas": problem_areas,
        "recent_issues": per_trace_suggestions[:20],
    }


@router.get("/trace/{trace_id}")
def get_trace_suggestions(trace_id: str, db: Session = Depends(get_db)):
    """Get suggestions for a specific trace."""
    trace = db.query(TraceRecord).filter(TraceRecord.trace_id == trace_id).first()
    if not trace:
        return {"trace_id": trace_id, "suggestions": []}

    if trace.suggestions:
        return {"trace_id": trace_id, "suggestions": trace.suggestions}

    if trace.metrics:
        suggestions = suggestion_engine.generate_suggestions(trace.metrics)
        return {"trace_id": trace_id, "suggestions": suggestions, "metrics": trace.metrics}

    return {"trace_id": trace_id, "suggestions": ["No metrics available for this trace."]}
