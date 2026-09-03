"""
Traces API - CRUD operations for traces and spans.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import uuid

from app.db.database import get_db
from app.db.models import TraceRecord, SpanRecord, ProjectRecord
from pydantic import BaseModel

router = APIRouter(prefix="/traces", tags=["traces"])


# --- Pydantic Schemas ---

class SpanCreate(BaseModel):
    span_id: str = ""
    parent_span_id: Optional[str] = None
    name: str = ""
    span_type: str = "custom"
    status: str = "success"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    latency_ms: float = 0.0
    inputs: dict = {}
    outputs: dict = {}
    metadata: dict = {}
    error: Optional[str] = None
    tokens: dict = {}
    cost_usd: float = 0.0
    model: Optional[str] = None


class TraceCreate(BaseModel):
    trace_id: str = ""
    project: str = "default"
    name: str = ""
    user: str = ""
    session_id: str = ""
    eval_status: str = "none"
    eval_metrics: list[str] = []  # If non-empty, run evaluation after storing
    status: str = "success"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    total_latency_ms: float = 0.0
    total_cost_usd: float = 0.0
    total_tokens: dict = {}
    query: str = ""
    context: str = ""
    answer: str = ""
    ground_truth: Optional[str] = None
    retrieved_chunks: list = []
    metrics: dict = {}
    suggestions: list = []
    metadata: dict = {}
    spans: list[SpanCreate] = []


class TraceResponse(BaseModel):
    trace_id: str
    project: str
    name: str
    status: str
    start_time: str
    end_time: Optional[str]
    total_latency_ms: float
    total_cost_usd: float
    total_tokens: dict
    query: str
    context: str
    answer: str
    ground_truth: Optional[str]
    retrieved_chunks: list
    metrics: dict
    suggestions: list
    spans: list[dict]

    class Config:
        from_attributes = True


# --- Endpoints ---

@router.post("", status_code=201)
def create_trace(trace_data: TraceCreate, db: Session = Depends(get_db)):
    """Receive and store a trace from the SDK."""
    trace_id = trace_data.trace_id or str(uuid.uuid4())

    trace_record = TraceRecord(
        trace_id=trace_id,
        project=trace_data.project,
        name=trace_data.name,
        user=trace_data.user,
        session_id=trace_data.session_id,
        eval_status=trace_data.eval_status,
        status=trace_data.status,
        start_time=datetime.fromisoformat(trace_data.start_time) if trace_data.start_time else datetime.utcnow(),
        end_time=datetime.fromisoformat(trace_data.end_time) if trace_data.end_time else None,
        total_latency_ms=trace_data.total_latency_ms,
        total_cost_usd=trace_data.total_cost_usd,
        total_tokens=trace_data.total_tokens,
        query=trace_data.query,
        context=trace_data.context,
        answer=trace_data.answer,
        ground_truth=trace_data.ground_truth,
        retrieved_chunks=trace_data.retrieved_chunks,
        metrics=trace_data.metrics,
        suggestions=trace_data.suggestions,
        metadata_json=trace_data.metadata,
    )

    db.add(trace_record)

    # Add spans
    for span_data in trace_data.spans:
        span_record = SpanRecord(
            span_id=span_data.span_id or str(uuid.uuid4()),
            trace_id=trace_id,
            parent_span_id=span_data.parent_span_id,
            name=span_data.name,
            span_type=span_data.span_type,
            status=span_data.status,
            start_time=datetime.fromisoformat(span_data.start_time) if span_data.start_time else datetime.utcnow(),
            end_time=datetime.fromisoformat(span_data.end_time) if span_data.end_time else None,
            latency_ms=span_data.latency_ms,
            inputs=span_data.inputs,
            outputs=span_data.outputs,
            metadata_json=span_data.metadata,
            error=span_data.error,
            tokens=span_data.tokens,
            cost_usd=span_data.cost_usd,
            model=span_data.model,
        )
        db.add(span_record)

    db.commit()

    # Background: check budget alerts (non-blocking)
    try:
        import threading
        from app.api.alerts import check_budget_alerts
        from app.db.database import SessionLocal

        def _check_budgets():
            try:
                bg_db = SessionLocal()
                check_budget_alerts(trace_data.project, bg_db)
                bg_db.close()
            except Exception:
                pass

        threading.Thread(target=_check_budgets, daemon=True).start()
    except Exception:
        pass

    # Auto-eval: if eval_metrics provided, run evaluation synchronously
    eval_result = None
    if trace_data.eval_metrics and trace_data.eval_status == "pending":
        try:
            # Update status to running
            trace_record.eval_status = "running"
            db.commit()

            from app.api.evaluation import EvalRequest, run_evaluation
            eval_req = EvalRequest(
                trace_id=trace_id,
                metrics=trace_data.eval_metrics,
            )
            eval_result = run_evaluation(eval_req, db)

            # Update status based on result
            if eval_result.get("status") == "success":
                trace_record.eval_status = "completed"
            elif eval_result.get("status") == "partial":
                trace_record.eval_status = "partial"
            else:
                trace_record.eval_status = "failed"
            db.commit()
        except Exception as e:
            trace_record.eval_status = "failed"
            db.commit()
            import logging
            logging.getLogger("obtrac").warning(f"Auto-eval failed: {e}")

    return {
        "trace_id": trace_id,
        "status": "stored",
        "eval_status": trace_record.eval_status,
        "eval_result": eval_result,
    }


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


@router.post("/projects", status_code=201)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    """Create a project up-front so it appears in dropdowns even before
    any traces are logged. Idempotent — returns existing project if name
    already exists (either in the projects table or implicitly via traces)."""
    name = data.name.strip()
    if not name:
        raise HTTPException(400, "Project name cannot be empty")

    existing = db.query(ProjectRecord).filter(ProjectRecord.name == name).first()
    if existing:
        return {
            "name": existing.name,
            "description": existing.description,
            "created_at": existing.created_at.isoformat(),
            "already_existed": True,
        }

    project = ProjectRecord(name=name, description=data.description.strip())
    db.add(project)
    db.commit()
    db.refresh(project)

    return {
        "name": project.name,
        "description": project.description,
        "created_at": project.created_at.isoformat(),
        "already_existed": False,
    }


@router.delete("/projects/{name}")
def delete_project(name: str, db: Session = Depends(get_db)):
    """Delete a user-created project entry. Does NOT delete traces/prompts
    that reference this project name — only removes it from the explicit
    projects table. For projects that have trace history, this is close to
    a no-op from the dashboard's point of view (list_projects() re-derives
    the project from its traces either way) — use DELETE /projects/{name}/purge
    to actually remove a project's data."""
    project = db.query(ProjectRecord).filter(ProjectRecord.name == name).first()
    if not project:
        raise HTTPException(404, f"Project '{name}' not found")
    db.delete(project)
    db.commit()
    return {"status": "deleted", "name": name}


@router.delete("/projects/{name}/purge")
def purge_project(name: str, db: Session = Depends(get_db)):
    """Permanently delete a project and ALL of its data: every trace (and
    their spans, via cascade) plus the projects-table entry if one exists.
    This is the operation the dashboard's project card delete button uses —
    plain DELETE /projects/{name} only removes the lightweight registry
    entry and leaves trace history in place, which isn't what "delete this
    project" means to a user looking at a card full of traces.

    Does NOT touch prompts (global, not project-scoped) or budgets/alert
    channels referencing this project name — those are left in place."""
    traces = db.query(TraceRecord).filter(TraceRecord.project == name).all()
    trace_count = len(traces)
    for t in traces:
        db.delete(t)  # cascades to spans via the relationship's cascade="all, delete-orphan"

    project = db.query(ProjectRecord).filter(ProjectRecord.name == name).first()
    had_registry_entry = project is not None
    if project:
        db.delete(project)

    if trace_count == 0 and not had_registry_entry:
        raise HTTPException(404, f"Project '{name}' not found")

    db.commit()
    return {"status": "purged", "name": name, "traces_deleted": trace_count}


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    """List all projects with rich stats. Merges user-created projects
    (from the projects table) with projects implicitly derived from traces."""
    from sqlalchemy import func
    import math

    def _safe(v):
        try:
            f = float(v)
            return f if not (math.isnan(f) or math.isinf(f)) else None
        except (TypeError, ValueError):
            return None

    # 1. Projects implicitly derived from trace activity
    trace_projects = (
        db.query(
            TraceRecord.project,
            func.count(TraceRecord.trace_id).label("count"),
            func.avg(TraceRecord.total_latency_ms).label("avg_latency"),
            func.sum(TraceRecord.total_cost_usd).label("total_cost"),
            func.max(TraceRecord.created_at).label("last_activity"),
        )
        .group_by(TraceRecord.project)
        .all()
    )

    by_name: dict[str, dict] = {}
    for p in trace_projects:
        success = db.query(func.count(TraceRecord.trace_id)).filter(
            TraceRecord.project == p.project, TraceRecord.status == "success"
        ).scalar() or 0
        error = db.query(func.count(TraceRecord.trace_id)).filter(
            TraceRecord.project == p.project, TraceRecord.status == "error"
        ).scalar() or 0

        # Quality score: mean of each evaluated trace's own average metric
        # score. Distinct from "success" (did the code run without an
        # exception) — this reflects RAGAS-style answer quality. None when
        # no trace in the project has been evaluated yet, so the frontend
        # can show "not evaluated" instead of a misleading 0%.
        metric_rows = (
            db.query(TraceRecord.metrics)
            .filter(TraceRecord.project == p.project, TraceRecord.metrics.isnot(None))
            .all()
        )
        per_trace_avgs = []
        for (metrics,) in metric_rows:
            if not metrics:
                continue
            values = [v for v in (_safe(x) for x in metrics.values()) if v is not None]
            if values:
                per_trace_avgs.append(sum(values) / len(values))
        avg_quality_score = round(sum(per_trace_avgs) / len(per_trace_avgs), 4) if per_trace_avgs else None

        by_name[p.project] = {
            "name": p.project,
            "count": p.count,
            "success": success,
            "error": error,
            "avg_latency_ms": round(p.avg_latency or 0, 1),
            "total_cost_usd": round(float(p.total_cost or 0), 6),
            "avg_quality_score": avg_quality_score,
            "evaluated_traces": len(per_trace_avgs),
            "last_activity": p.last_activity.isoformat() if p.last_activity else None,
            "user_created": False,
        }

    # 2. User-created projects (may overlap with trace-derived ones)
    for proj in db.query(ProjectRecord).all():
        if proj.name in by_name:
            by_name[proj.name]["user_created"] = True
            by_name[proj.name]["description"] = proj.description
        else:
            by_name[proj.name] = {
                "name": proj.name,
                "count": 0,
                "success": 0,
                "error": 0,
                "avg_latency_ms": 0,
                "total_cost_usd": 0,
                "avg_quality_score": None,
                "evaluated_traces": 0,
                "last_activity": proj.created_at.isoformat(),
                "user_created": True,
                "description": proj.description,
            }

    return {"projects": list(by_name.values())}


@router.get("/search")
def search_traces(
    q: str = Query(..., min_length=1),
    project: str = Query("all"),
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """Search traces by query text, answer, or trace ID."""
    query = db.query(TraceRecord)
    if project != "all":
        query = query.filter(TraceRecord.project == project)

    search = f"%{q}%"
    query = query.filter(
        (TraceRecord.query.ilike(search))
        | (TraceRecord.answer.ilike(search))
        | (TraceRecord.trace_id.ilike(search))
        | (TraceRecord.name.ilike(search))
    )

    traces = query.order_by(TraceRecord.created_at.desc()).limit(limit).all()
    return {
        "total": len(traces),
        "query": q,
        "traces": [
            {
                "trace_id": t.trace_id,
                "project": t.project,
                "name": t.name,
                "query": (t.query or "")[:150],
                "answer": (t.answer or "")[:150],
                "status": t.status,
                "total_latency_ms": t.total_latency_ms or 0,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in traces
        ],
    }


@router.get("")
def list_traces(
    project: str = Query("all"),
    status: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List traces with filtering. Use project='all' to see all projects."""
    query = db.query(TraceRecord)
    if project != "all":
        query = query.filter(TraceRecord.project == project)

    if status:
        query = query.filter(TraceRecord.status == status)

    total = query.count()
    traces = query.order_by(TraceRecord.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "traces": [
            {
                "trace_id": t.trace_id,
                "project": t.project,
                "name": t.name,
                "user": t.user or "",
                "status": t.status,
                "eval_status": t.eval_status or "none",
                "start_time": t.start_time.isoformat() if t.start_time else None,
                "end_time": t.end_time.isoformat() if t.end_time else None,
                "total_latency_ms": t.total_latency_ms,
                "total_cost_usd": t.total_cost_usd,
                "total_tokens": t.total_tokens or {},
                "query": t.query[:200] if t.query else "",
                "answer": t.answer[:200] if t.answer else "",
                "metrics": t.metrics or {},
                "num_spans": len(t.spans),
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in traces
        ],
    }


@router.get("/{trace_id}")
def get_trace(trace_id: str, db: Session = Depends(get_db)):
    """Get a single trace with all spans."""
    trace = db.query(TraceRecord).filter(TraceRecord.trace_id == trace_id).first()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    return {
        "trace_id": trace.trace_id,
        "project": trace.project,
        "name": trace.name,
        "status": trace.status,
        "start_time": trace.start_time.isoformat() if trace.start_time else None,
        "end_time": trace.end_time.isoformat() if trace.end_time else None,
        "total_latency_ms": trace.total_latency_ms,
        "total_cost_usd": trace.total_cost_usd,
        "total_tokens": trace.total_tokens or {},
        "query": trace.query,
        "context": trace.context,
        "answer": trace.answer,
        "ground_truth": trace.ground_truth,
        "retrieved_chunks": trace.retrieved_chunks or [],
        "metrics": trace.metrics or {},
        "suggestions": trace.suggestions or [],
        "spans": [
            {
                "span_id": s.span_id,
                "parent_span_id": s.parent_span_id,
                "name": s.name,
                "span_type": s.span_type,
                "status": s.status,
                "start_time": s.start_time.isoformat() if s.start_time else None,
                "end_time": s.end_time.isoformat() if s.end_time else None,
                "latency_ms": s.latency_ms,
                "inputs": s.inputs or {},
                "outputs": s.outputs or {},
                "error": s.error,
                "tokens": s.tokens or {},
                "cost_usd": s.cost_usd,
                "model": s.model,
            }
            for s in trace.spans
        ],
    }


@router.delete("/{trace_id}")
def delete_trace(trace_id: str, db: Session = Depends(get_db)):
    """Delete a trace and all its spans."""
    trace = db.query(TraceRecord).filter(TraceRecord.trace_id == trace_id).first()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    db.delete(trace)
    db.commit()
    return {"status": "deleted", "trace_id": trace_id}
