"""
Sessions API — Group traces by session_id to track conversations.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import get_db
from app.db.models import TraceRecord

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
def list_sessions(
    project: str = Query("all"),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """List all sessions with aggregated stats."""
    query = db.query(
        TraceRecord.session_id,
        TraceRecord.project,
        TraceRecord.user,
        func.count(TraceRecord.trace_id).label("trace_count"),
        func.min(TraceRecord.created_at).label("started_at"),
        func.max(TraceRecord.created_at).label("last_activity"),
        func.sum(TraceRecord.total_latency_ms).label("total_latency"),
        func.sum(TraceRecord.total_cost_usd).label("total_cost"),
    ).filter(
        TraceRecord.session_id != "",
        TraceRecord.session_id != None,
    )

    if project != "all":
        query = query.filter(TraceRecord.project == project)

    sessions = (
        query.group_by(TraceRecord.session_id, TraceRecord.project, TraceRecord.user)
        .order_by(func.max(TraceRecord.created_at).desc())
        .limit(limit)
        .all()
    )

    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "project": s.project,
                "user": s.user or "",
                "trace_count": s.trace_count,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "last_activity": s.last_activity.isoformat() if s.last_activity else None,
                "total_latency_ms": round(s.total_latency or 0, 1),
                "total_cost_usd": round(float(s.total_cost or 0), 6),
            }
            for s in sessions
        ]
    }


@router.get("/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db)):
    """Get all traces in a session, ordered chronologically."""
    traces = (
        db.query(TraceRecord)
        .filter(TraceRecord.session_id == session_id)
        .order_by(TraceRecord.created_at.asc())
        .all()
    )

    if not traces:
        return {"session_id": session_id, "traces": []}

    return {
        "session_id": session_id,
        "project": traces[0].project,
        "user": traces[0].user or "",
        "trace_count": len(traces),
        "started_at": traces[0].created_at.isoformat() if traces[0].created_at else None,
        "last_activity": traces[-1].created_at.isoformat() if traces[-1].created_at else None,
        "traces": [
            {
                "trace_id": t.trace_id,
                "name": t.name,
                "query": t.query or "",
                "answer": (t.answer or "")[:300],
                "status": t.status,
                "total_latency_ms": t.total_latency_ms or 0,
                "total_cost_usd": t.total_cost_usd or 0,
                "metrics": t.metrics or {},
                "num_spans": len(t.spans),
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in traces
        ],
    }
