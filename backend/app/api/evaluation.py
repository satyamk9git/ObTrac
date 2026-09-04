"""
Evaluation API - Run quality metrics on traces, with or without ground truth.
Sources built-in, DeepEval, and Arize Phoenix metrics via the metric
registry (app.services.metrics) — not limited to RAGAS-style scoring.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import logging

from app.db.database import get_db, SessionLocal
from app.db.models import TraceRecord, GroundTruthRecord, LLMConfigRecord, EvalJobRecord
from app.services.metrics import MetricInput, MetricRunner, get_registry

logger = logging.getLogger("obtrac")

router = APIRouter(prefix="/evaluation", tags=["evaluation"])

_CATEGORY_DESCRIPTIONS = {
    "Generation Quality": "Metrics that evaluate the LLM's answer quality",
    "Retrieval Quality": "Metrics that evaluate the retriever's performance",
    "End-to-End Quality": "Metrics that evaluate the full RAG pipeline output",
}


def _metric_info() -> dict:
    """Legacy-shaped METRIC_INFO dict (name/description/needs_*/threshold/
    category/...), now sourced from the metric registry instead of being
    its own hardcoded dict — kept as a function (not a module-level
    constant) so it always reflects whatever's currently registered,
    including any external-framework metrics registered after import time."""
    return {key: metric.info_dict() for key, metric in get_registry().all().items()}


def _build_contexts(trace) -> list[str]:
    """Centralizes context-building logic that used to be duplicated at 3
    call sites in this file. Priority (trace.context string over
    retrieved_chunks) matches the original per-call-site behavior exactly,
    since some traces have both populated and the string form was always
    preferred — external multi-chunk-aware metrics (Part C) get the full
    retrieved_chunks list directly instead of going through this."""
    if trace.context:
        return [trace.context]
    if trace.retrieved_chunks:
        return [str(c) for c in trace.retrieved_chunks]
    return []


def _build_tool_calls(trace) -> list[dict]:
    """Walks trace.spans for TOOL_CALL spans and normalizes them into the
    shape MetricInput.tool_calls / the tool-dependent metric adapters
    expect: {"name", "args", "result", "status"}."""
    calls = []
    for span in trace.spans or []:
        if span.span_type != "tool_call" or not span.tool_name:
            continue
        calls.append({
            "name": span.tool_name,
            "args": span.tool_args or {},
            "result": span.tool_result,
            "status": span.status,
        })
    return calls


@router.get("/metrics-info")
def get_metrics_info():
    """Get detailed information about all available metrics — built-in
    plus any external-framework adapters (DeepEval/MLflow/Phoenix) that
    are installed."""
    info = _metric_info()
    categories: dict[str, dict] = {}
    for key, meta in info.items():
        cat = meta["category"]
        categories.setdefault(cat, {
            "description": _CATEGORY_DESCRIPTIONS.get(cat, ""),
            "metrics": [],
        })["metrics"].append(key)
    return {
        "metrics": info,
        "categories": categories,
    }


class EvalRequest(BaseModel):
    trace_id: str
    metrics: list[str] = ["faithfulness", "answer_relevancy"]
    ground_truth: Optional[str] = None
    judge_llm_config_id: Optional[str] = None


@router.post("/run")
def run_evaluation(req: EvalRequest, db: Session = Depends(get_db)):
    """
    Run RAGAS evaluation on a specific trace.
    If ground truth is needed, it can be provided directly or matched from resources.
    """
    trace = db.query(TraceRecord).filter(TraceRecord.trace_id == req.trace_id).first()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    # Determine ground truth
    ground_truth = req.ground_truth or trace.ground_truth
    gt_record = None

    # Try to match from resources if not provided
    if not ground_truth and trace.query:
        gt_record = (
            db.query(GroundTruthRecord)
            .filter(GroundTruthRecord.question == trace.query)
            .first()
        )
        if gt_record:
            ground_truth = gt_record.ground_truth

    # Check which metrics can run
    registry = get_registry()
    contexts = _build_contexts(trace)
    eval_input = MetricInput(
        question=trace.query or "", answer=trace.answer or "",
        contexts=contexts, ground_truth=ground_truth or "",
        retrieved_chunks=trace.retrieved_chunks or [],
        tool_calls=_build_tool_calls(trace),
        expected_tools=(gt_record.expected_tools if gt_record else None) or [],
    )
    runnable_metrics = []
    skipped_metrics = []
    for m in req.metrics:
        metric = registry.get(m)
        if not metric:
            skipped_metrics.append({"metric": m, "reason": f"Unknown metric: {m}"})
            continue
        ok, reason = metric.is_runnable(eval_input)
        if not ok:
            skipped_metrics.append({"metric": m, "reason": reason})
            continue
        runnable_metrics.append(m)

    if not runnable_metrics:
        return {
            "trace_id": req.trace_id,
            "status": "no_metrics_to_run",
            "skipped": skipped_metrics,
            "metrics": {},
            "suggestions": [],
        }

    # Get judge LLM from LLM Config
    judge_config = None
    if req.judge_llm_config_id:
        judge_config = (
            db.query(LLMConfigRecord)
            .filter(LLMConfigRecord.id == req.judge_llm_config_id)
            .first()
        )
    else:
        # Auto-pick priority: use_for_auto_eval > role=judge > any active
        judge_config = (
            db.query(LLMConfigRecord)
            .filter(LLMConfigRecord.use_for_auto_eval == True, LLMConfigRecord.is_active == True)
            .first()
        )
        if not judge_config:
            judge_config = (
                db.query(LLMConfigRecord)
                .filter(LLMConfigRecord.role == "judge", LLMConfigRecord.is_active == True)
                .first()
            )
        if not judge_config:
            judge_config = (
                db.query(LLMConfigRecord)
                .filter(LLMConfigRecord.is_active == True)
                .first()
            )

    if not judge_config:
        return {
            "trace_id": req.trace_id,
            "status": "error",
            "error": (
                "No LLM configured for evaluation. "
                "Go to LLM Config and add an LLM (with role 'judge' or 'generator')."
            ),
            "skipped": skipped_metrics,
        }

    # Run evaluation via the metric registry — built-in metrics are scored
    # by LLM-as-judge (llm_judge.py), external-framework metrics by their
    # own adapter (Part C). RAGAS's own package is not used here: its own
    # internal import (langchain_community.chat_models.vertexai — removed
    # upstream) isn't fixable by simple version pinning without breaking
    # langgraph/langchain-openai's newer langchain-core requirement.
    try:
        from obtrac_sdk.evaluator import SuggestionEngine

        metric_results = MetricRunner.run(runnable_metrics, eval_input, judge_config)
        result_dict = {r.metric: r.score for r in metric_results if r.score is not None}
        # A metric that was runnable but failed mid-scoring (bad judge
        # response, adapter exception, etc.) has score=None and previously
        # just vanished from the response with no trace of the failure —
        # surface it instead of silently dropping it.
        failed_dict = {r.metric: (r.error or "Unknown error") for r in metric_results if r.score is None}

        if not result_dict and runnable_metrics:
            return {
                "trace_id": req.trace_id,
                "status": "error",
                "error": "Judge LLM did not return valid scores for any metric. Check the LLM config and try again.",
                "skipped": skipped_metrics,
                "failed": failed_dict,
            }

        # Generate suggestions
        engine = SuggestionEngine()
        suggestions = engine.generate_suggestions(result_dict)

        # Save to trace
        existing_metrics = trace.metrics or {}
        existing_metrics.update(result_dict)
        trace.metrics = existing_metrics
        trace.suggestions = suggestions
        if ground_truth:
            trace.ground_truth = ground_truth
        db.commit()

        return {
            "trace_id": req.trace_id,
            "status": "success",
            "metrics": result_dict,
            "failed": failed_dict,
            "suggestions": suggestions,
            "skipped": skipped_metrics,
            "ground_truth_used": bool(ground_truth),
            "judge_llm": f"{judge_config.provider}/{judge_config.model_id}",
        }

    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        return {
            "trace_id": req.trace_id,
            "status": "error",
            "error": str(e),
            "skipped": skipped_metrics,
        }


@router.post("/run-batch")
def run_batch_evaluation(
    project: str = Query("test-rag-app"),
    metrics: str = Query("faithfulness,answer_relevancy"),
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """Run evaluation on multiple recent traces."""
    metric_list = [m.strip() for m in metrics.split(",")]
    traces = (
        db.query(TraceRecord)
        .filter(TraceRecord.project == project)
        .order_by(TraceRecord.created_at.desc())
        .limit(limit)
        .all()
    )

    results = []
    for trace in traces:
        req = EvalRequest(trace_id=trace.trace_id, metrics=metric_list)
        result = run_evaluation(req, db)
        results.append(result)

    success = sum(1 for r in results if r.get("status") == "success")
    return {
        "total": len(results),
        "success": success,
        "failed": len(results) - success,
        "results": results,
    }


# =============================================
# Bulk "run missing evals" — fills in only the metrics a trace doesn't
# already have, instead of re-scoring everything (unlike /run-batch).
# Runs as a background job, reusing EvalJobRecord so it shows up in the
# same "N evals running" badge as per-trace jobs.
# =============================================

_BULK_JOB_SENTINEL = "__bulk__"


class RunMissingEvalsRequest(BaseModel):
    project: str
    metrics: list[str] = ["faithfulness", "answer_relevancy"]
    judge_llm_config_id: Optional[str] = None
    limit: int = 200  # how many recent traces to check


def _run_missing_evals_job(job_id: str, params: dict):
    """Daemon-thread worker. Owns its own DB session — never reuse a request session."""
    db = SessionLocal()
    try:
        job = db.query(EvalJobRecord).filter(EvalJobRecord.id == job_id).first()
        if not job:
            return

        job.status = "running"
        job.started_at = datetime.utcnow()
        job.progress_message = "Scanning traces for missing metrics..."
        db.commit()

        project = params["project"]
        wanted_metrics = params["metrics"]
        judge_llm_config_id = params.get("judge_llm_config_id")

        traces = (
            db.query(TraceRecord)
            .filter(TraceRecord.project == project, TraceRecord.status == "success")
            .order_by(TraceRecord.created_at.desc())
            .limit(params.get("limit", 200))
            .all()
        )

        to_process = []
        for t in traces:
            have = set((t.metrics or {}).keys())
            missing = [m for m in wanted_metrics if m not in have]
            if missing:
                to_process.append((t, missing))

        job.progress_message = f"{len(to_process)} of {len(traces)} traces have missing metrics"
        db.commit()

        evaluated, failed, skipped_no_metrics = 0, 0, 0
        for i, (trace, missing) in enumerate(to_process):
            job.progress_message = (
                f"Evaluating {i + 1}/{len(to_process)} — {trace.trace_id[:8]} "
                f"(missing: {', '.join(missing)})"
            )
            db.commit()
            try:
                req = EvalRequest(
                    trace_id=trace.trace_id,
                    metrics=missing,
                    judge_llm_config_id=judge_llm_config_id,
                )
                result = run_evaluation(req, db)
                status = result.get("status")
                if status == "success":
                    evaluated += 1
                elif status == "no_metrics_to_run":
                    # e.g. needs ground truth this trace doesn't have — not a failure
                    skipped_no_metrics += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                logger.warning(f"Bulk missing-eval failed for {trace.trace_id}: {e}")

        job.status = "completed"
        job.result = {
            "project": project,
            "traces_checked": len(traces),
            "traces_with_missing_metrics": len(to_process),
            "evaluated": evaluated,
            "skipped_no_applicable_metrics": skipped_no_metrics,
            "failed": failed,
        }
        job.progress_message = "Done"
    except Exception as e:
        job.status = "failed"
        job.error = f"{type(e).__name__}: {str(e)[:500]}"
        logger.exception(f"Bulk missing-eval job {job_id} crashed")
    finally:
        job.finished_at = datetime.utcnow()
        db.commit()
        db.close()


@router.post("/run-missing-async", status_code=202)
def run_missing_evals_async(req: RunMissingEvalsRequest, db: Session = Depends(get_db)):
    """
    Queue a background job that evaluates only the traces (and only the
    specific metrics) that are currently missing scores — traces that
    already have a metric keep their existing score untouched, so this is
    safe to run repeatedly without wasting judge-LLM calls on traces that
    are already fully scored.

    Poll GET /evaluation/jobs/{id} for progress; the final `result` field
    has {traces_checked, traces_with_missing_metrics, evaluated, failed}.
    """
    job_id = str(uuid.uuid4())
    job = EvalJobRecord(
        id=job_id,
        trace_id=_BULK_JOB_SENTINEL,
        project=req.project,
        status="queued",
        metrics=req.metrics,
        judge_llm_config_ids=[req.judge_llm_config_id] if req.judge_llm_config_id else [],
        progress_message="Queued",
    )
    db.add(job)
    db.commit()

    params = {
        "project": req.project,
        "metrics": req.metrics,
        "judge_llm_config_id": req.judge_llm_config_id,
        "limit": req.limit,
    }
    threading.Thread(target=_run_missing_evals_job, args=(job_id, params), daemon=True).start()

    return {
        "job_id": job_id,
        "status": "queued",
        "project": req.project,
        "message": "Bulk missing-evals job queued. Poll /evaluation/jobs/{job_id} for progress.",
    }


# =============================================
# Multi-LLM Comparison Evaluation
# =============================================

class MultiLLMEvalRequest(BaseModel):
    trace_id: str
    metrics: list[str] = ["faithfulness", "answer_relevancy"]
    judge_llm_config_ids: list[str] = []  # List of LLM config IDs to evaluate with
    ground_truth: Optional[str] = None
    dataset_name: Optional[str] = None  # Pick GT from a saved dataset (auto-match by question)


def _execute_multi_llm_eval(
    db: Session,
    trace_id: str,
    metrics: list[str],
    judge_llm_config_ids: list[str],
    ground_truth: Optional[str],
    dataset_name: Optional[str],
    job: Optional[EvalJobRecord] = None,
) -> dict:
    """Core synchronous eval logic. Used by both the sync endpoint and the
    background-thread async runner. If `job` is provided, progress messages
    are written to the job row so the frontend can poll status."""

    def _set_progress(msg: str):
        if job is not None:
            job.progress_message = msg
            db.commit()

    trace = db.query(TraceRecord).filter(TraceRecord.trace_id == trace_id).first()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    # Mock the request shape for the rest of the existing flow
    class _Req:
        pass
    req = _Req()
    req.trace_id = trace_id
    req.metrics = metrics
    req.judge_llm_config_ids = judge_llm_config_ids
    req.ground_truth = ground_truth
    req.dataset_name = dataset_name

    # Ground truth — resolution priority:
    # 1. Explicit text in req.ground_truth
    # 2. Semantic match in specified dataset (using embeddings)
    # 3. Existing trace.ground_truth
    ground_truth = req.ground_truth
    matched_expected_tools = None
    if not ground_truth and req.dataset_name and trace.query:
        try:
            from app.api.resources import match_ground_truth_semantic
            match_result = match_ground_truth_semantic(
                query=trace.query,
                dataset_name=req.dataset_name,
                project=trace.project,
                db=db,
            )
            if match_result.get("found") and match_result.get("match"):
                ground_truth = match_result["match"]["ground_truth"]
                matched_expected_tools = match_result["match"].get("expected_tools")
                logger.info(f"Semantic GT match: '{trace.query[:40]}' -> '{match_result['match']['question'][:40]}' (score: {match_result.get('score')})")
        except Exception as e:
            logger.warning(f"Semantic match failed: {e}")
    if not ground_truth:
        ground_truth = trace.ground_truth

    # Get LLM configs
    llm_configs = []
    if req.judge_llm_config_ids:
        for cid in req.judge_llm_config_ids:
            cfg = db.query(LLMConfigRecord).filter(LLMConfigRecord.id == cid).first()
            if cfg:
                llm_configs.append(cfg)
    else:
        llm_configs = db.query(LLMConfigRecord).filter(LLMConfigRecord.is_active == True).all()

    if not llm_configs:
        return {
            "trace_id": req.trace_id,
            "status": "error",
            "error": "No LLMs configured. Go to LLM Config and add at least one LLM.",
        }

    # Build context, then filter metrics against the registry
    contexts = _build_contexts(trace)
    registry = get_registry()
    eval_input = MetricInput(
        question=trace.query or "", answer=trace.answer or "",
        contexts=contexts, ground_truth=ground_truth or "",
        retrieved_chunks=trace.retrieved_chunks or [],
        tool_calls=_build_tool_calls(trace),
        expected_tools=matched_expected_tools or [],
    )
    runnable_metrics = []
    skipped_metrics = []
    for m in req.metrics:
        metric = registry.get(m)
        if not metric:
            skipped_metrics.append({"metric": m, "reason": "Unknown metric"})
            continue
        ok, reason = metric.is_runnable(eval_input)
        if not ok:
            skipped_metrics.append({"metric": m, "reason": reason})
            continue
        runnable_metrics.append(m)

    if not runnable_metrics:
        return {
            "trace_id": req.trace_id,
            "status": "no_metrics_to_run",
            "skipped": skipped_metrics,
            "llm_results": [],
            "recommendations": {},
        }

    # Run evaluation for EACH LLM concurrently — _run_single_llm_eval doesn't
    # touch the DB (it's pure LLM calls), so this is safe to parallelize.
    # (Previously sequential: N judges took N times as long as one, on top
    # of each judge's own metrics also having been sequential — see
    # evaluate_with_llm_judge in llm_judge.py for that half of the fix.)
    names = ", ".join(c.name for c in llm_configs)
    _set_progress(f"Evaluating with {len(llm_configs)} judge(s) in parallel: {names}...")
    with ThreadPoolExecutor(max_workers=min(len(llm_configs), 4)) as pool:
        llm_results = list(pool.map(
            lambda cfg: _run_single_llm_eval(trace, cfg, runnable_metrics, contexts, ground_truth, matched_expected_tools),
            llm_configs,
        ))

    _set_progress("Generating recommendations...")

    # Generate detailed recommendations
    recommendations = _generate_detailed_recommendations(
        trace, llm_results, runnable_metrics
    )

    # Save best metrics to trace
    if llm_results:
        best_metrics = {}
        for m in runnable_metrics:
            scores = [r["metrics"].get(m) for r in llm_results if r["metrics"].get(m) is not None]
            if scores:
                best_metrics[m] = round(max(scores), 4)
        trace.metrics = best_metrics
        trace.suggestions = recommendations.get("trace_level", [])
        if ground_truth:
            trace.ground_truth = ground_truth
        db.commit()

    return {
        "trace_id": req.trace_id,
        "status": "success",
        "llm_results": llm_results,
        "skipped": skipped_metrics,
        "recommendations": recommendations,
        "ground_truth_used": bool(ground_truth),
    }


@router.post("/run-multi-llm")
def run_multi_llm_evaluation(req: MultiLLMEvalRequest, db: Session = Depends(get_db)):
    """Synchronous multi-LLM RAGAS evaluation. Blocks until done.
    Use the async variant for long-running evals."""
    return _execute_multi_llm_eval(
        db=db,
        trace_id=req.trace_id,
        metrics=req.metrics,
        judge_llm_config_ids=req.judge_llm_config_ids,
        ground_truth=req.ground_truth,
        dataset_name=req.dataset_name,
    )


# =============================================
# Async multi-LLM evaluation (background jobs)
# =============================================


def _run_eval_job_in_background(job_id: str, params: dict):
    """Daemon-thread worker. Owns its own DB session — never reuse a request session."""
    db = SessionLocal()
    try:
        job = db.query(EvalJobRecord).filter(EvalJobRecord.id == job_id).first()
        if not job:
            return

        job.status = "running"
        job.started_at = datetime.utcnow()
        job.progress_message = "Starting evaluation..."
        db.commit()

        try:
            result = _execute_multi_llm_eval(
                db=db,
                trace_id=params["trace_id"],
                metrics=params["metrics"],
                judge_llm_config_ids=params["judge_llm_config_ids"],
                ground_truth=params.get("ground_truth"),
                dataset_name=params.get("dataset_name"),
                job=job,
            )
            job.status = "completed"
            job.result = result
            job.progress_message = "Done"
        except HTTPException as e:
            job.status = "failed"
            job.error = f"{e.status_code}: {e.detail}"
        except Exception as e:
            job.status = "failed"
            job.error = f"{type(e).__name__}: {str(e)[:500]}"
            logger.exception(f"Eval job {job_id} crashed")
        finally:
            job.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


@router.post("/run-multi-llm-async", status_code=202)
def run_multi_llm_async(req: MultiLLMEvalRequest, db: Session = Depends(get_db)):
    """Queue a RAGAS evaluation as a background job. Returns immediately
    with the job ID. The actual eval runs in a daemon thread and survives
    page navigation / browser close.

    Poll GET /evaluation/jobs/{id} to track progress."""
    # Validate the trace exists before queueing
    trace = db.query(TraceRecord).filter(TraceRecord.trace_id == req.trace_id).first()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    job_id = str(uuid.uuid4())
    job = EvalJobRecord(
        id=job_id,
        trace_id=req.trace_id,
        project=trace.project,
        status="queued",
        metrics=req.metrics,
        judge_llm_config_ids=req.judge_llm_config_ids,
        dataset_name=req.dataset_name,
        ground_truth=req.ground_truth,
        progress_message="Queued",
    )
    db.add(job)
    db.commit()

    # Fire-and-forget background thread
    params = {
        "trace_id": req.trace_id,
        "metrics": req.metrics,
        "judge_llm_config_ids": req.judge_llm_config_ids,
        "ground_truth": req.ground_truth,
        "dataset_name": req.dataset_name,
    }
    threading.Thread(
        target=_run_eval_job_in_background,
        args=(job_id, params),
        daemon=True,
    ).start()

    return {
        "job_id": job_id,
        "status": "queued",
        "trace_id": req.trace_id,
        "message": "Evaluation queued. Poll /evaluation/jobs/{job_id} for status.",
    }


def _job_to_dict(job: EvalJobRecord) -> dict:
    return {
        "id": job.id,
        "trace_id": job.trace_id,
        "project": job.project,
        "status": job.status,
        "metrics": job.metrics or [],
        "judge_llm_config_ids": job.judge_llm_config_ids or [],
        "dataset_name": job.dataset_name,
        "progress_message": job.progress_message,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.get("/jobs")
def list_eval_jobs(
    status: Optional[str] = Query(None, description="Filter by status: queued, running, completed, failed, cancelled"),
    project: Optional[str] = Query(None),
    trace_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """List eval jobs with optional filters. Used by the running-evals badge."""
    q = db.query(EvalJobRecord)
    if status:
        # Allow comma-separated: ?status=queued,running
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        q = q.filter(EvalJobRecord.status.in_(statuses))
    if project:
        q = q.filter(EvalJobRecord.project == project)
    if trace_id:
        q = q.filter(EvalJobRecord.trace_id == trace_id)
    rows = q.order_by(EvalJobRecord.created_at.desc()).limit(limit).all()
    return {
        "jobs": [_job_to_dict(r) for r in rows],
        "count": len(rows),
    }


@router.get("/jobs/{job_id}")
def get_eval_job(job_id: str, db: Session = Depends(get_db)):
    """Get a single eval job by ID."""
    job = db.query(EvalJobRecord).filter(EvalJobRecord.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Eval job not found")
    return _job_to_dict(job)


@router.delete("/jobs/{job_id}")
def cancel_eval_job(job_id: str, db: Session = Depends(get_db)):
    """Mark a queued job as cancelled. Cannot cancel a job that's already
    running — Python threads can't be safely killed mid-execution. The job
    will still complete and write its result; the status flag is informational."""
    job = db.query(EvalJobRecord).filter(EvalJobRecord.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Eval job not found")
    if job.status in ("completed", "failed", "cancelled"):
        return {"status": job.status, "message": "Already finished"}
    if job.status == "running":
        return {"status": "running", "message": "Cannot cancel — already running. It will finish shortly."}
    job.status = "cancelled"
    job.finished_at = datetime.utcnow()
    db.commit()
    return {"status": "cancelled"}


def _run_single_llm_eval(trace, llm_cfg, metrics, contexts, ground_truth, expected_tools=None) -> dict:
    """Run evaluation with a single LLM judge via the metric registry
    (app.services.metrics) — built-in metrics score via app.services.llm_judge
    under the hood; RAGAS itself is not used here (its own package has a
    broken internal import — langchain_community.chat_models.vertexai,
    removed upstream — that isn't fixable by simple version pinning without
    breaking langgraph/langchain-openai's newer langchain-core requirement)."""
    try:
        eval_input = MetricInput(
            question=trace.query or "", answer=trace.answer or "",
            contexts=contexts, ground_truth=ground_truth or "",
            retrieved_chunks=trace.retrieved_chunks or [],
            tool_calls=_build_tool_calls(trace),
            expected_tools=expected_tools or [],
        )
        metric_results = MetricRunner.run(metrics, eval_input, llm_cfg)
        result_dict = {r.metric: r.score for r in metric_results if r.score is not None}
        failed_dict = {r.metric: (r.error or "Unknown error") for r in metric_results if r.score is None}

        if not result_dict and metrics:
            return {
                "llm_name": llm_cfg.name,
                "llm_provider": llm_cfg.provider,
                "llm_model": llm_cfg.model_id,
                "status": "error",
                "error": "Judge LLM did not return valid scores for any metric",
                "metrics": {},
                "failed": failed_dict,
            }

        return {
            "llm_name": llm_cfg.name,
            "llm_provider": llm_cfg.provider,
            "llm_model": llm_cfg.model_id,
            "status": "success",
            "metrics": result_dict,
            "failed": failed_dict,
        }

    except Exception as e:
        logger.error(f"Eval with {llm_cfg.name} failed: {e}")
        return {
            "llm_name": llm_cfg.name,
            "llm_provider": llm_cfg.provider,
            "llm_model": llm_cfg.model_id,
            "status": "error",
            "error": str(e),
            "metrics": {},
        }


def _generate_detailed_recommendations(trace, llm_results, metrics) -> dict:
    """Generate per-metric and trace-level recommendations."""
    recommendations = {
        "metric_level": {},
        "trace_level": [],
    }

    # Collect all scores per metric across LLMs
    metric_scores: dict[str, list[dict]] = {}
    for m in metrics:
        metric_scores[m] = []
        for r in llm_results:
            if r["status"] == "success" and m in r["metrics"]:
                metric_scores[m].append({
                    "llm": r["llm_name"],
                    "score": r["metrics"][m],
                })

    # Per-metric recommendations
    registry = get_registry()
    for m, scores in metric_scores.items():
        metric_def = registry.get(m)
        info = metric_def.info_dict() if metric_def else {}
        threshold = info.get("threshold", 0.7)

        if not scores:
            recommendations["metric_level"][m] = {
                "status": "not_evaluated",
                "message": "No LLM could evaluate this metric.",
                "scores": [],
                "avg_score": None,
                "best_llm": None,
                "recommendations": [],
            }
            continue

        avg_score = sum(s["score"] for s in scores) / len(scores)
        best = max(scores, key=lambda x: x["score"])
        worst = min(scores, key=lambda x: x["score"])

        # Determine status
        if avg_score >= 0.8:
            status = "good"
            status_msg = f"Strong performance (avg {avg_score:.1%}). No action needed."
        elif avg_score >= threshold:
            status = "warning"
            status_msg = f"Acceptable but can improve (avg {avg_score:.1%})."
        else:
            status = "critical"
            status_msg = f"Below threshold (avg {avg_score:.1%} < {threshold:.0%}). Action needed."

        # Build recommendations
        metric_recs = []
        if avg_score < 0.8:
            metric_recs.extend(info.get("improvement_tips", []))

        # LLM comparison insight
        if len(scores) > 1:
            spread = best["score"] - worst["score"]
            if spread > 0.15:
                metric_recs.append(
                    f"Large score variance ({spread:.1%}) across judges. "
                    f"Best: {best['llm']} ({best['score']:.1%}), "
                    f"Worst: {worst['llm']} ({worst['score']:.1%}). "
                    f"Consider using {best['llm']} as your primary judge."
                )

        recommendations["metric_level"][m] = {
            "status": status,
            "message": status_msg,
            "scores": scores,
            "avg_score": round(avg_score, 4),
            "best_llm": best["llm"],
            "threshold": threshold,
            "recommendations": metric_recs,
        }

    # Trace-level recommendations
    all_avg_scores = {
        m: data["avg_score"]
        for m, data in recommendations["metric_level"].items()
        if data["avg_score"] is not None
    }

    if all_avg_scores:
        overall_avg = sum(all_avg_scores.values()) / len(all_avg_scores)

        if overall_avg >= 0.8:
            recommendations["trace_level"].append(
                f"Overall pipeline quality is GOOD (avg {overall_avg:.1%}). "
                "Minor optimizations possible but not critical."
            )
        elif overall_avg >= 0.6:
            recommendations["trace_level"].append(
                f"Overall pipeline quality is MODERATE (avg {overall_avg:.1%}). "
                "Focus on the lowest-scoring metrics below."
            )
        else:
            recommendations["trace_level"].append(
                f"Overall pipeline quality is LOW (avg {overall_avg:.1%}). "
                "Significant improvements needed in retrieval and/or generation."
            )

        # Find weakest areas
        sorted_metrics = sorted(all_avg_scores.items(), key=lambda x: x[1])
        weakest = sorted_metrics[0]
        weakest_metric_def = registry.get(weakest[0])
        info = weakest_metric_def.info_dict() if weakest_metric_def else {}

        if weakest[1] < 0.7:
            category = info.get("category", "Unknown")
            if category == "Retrieval Quality":
                recommendations["trace_level"].append(
                    f"PRIORITY: Fix retrieval — {info.get('name', weakest[0])} is at {weakest[1]:.1%}. "
                    "Your retriever is not fetching the right documents. "
                    "Try: hybrid search, reranker, better chunking strategy."
                )
            elif category == "Generation Quality":
                recommendations["trace_level"].append(
                    f"PRIORITY: Fix generation — {info.get('name', weakest[0])} is at {weakest[1]:.1%}. "
                    "The LLM is not producing quality answers from the context. "
                    "Try: better prompt template, lower temperature, stronger model."
                )
            else:
                recommendations["trace_level"].append(
                    f"PRIORITY: {info.get('name', weakest[0])} is at {weakest[1]:.1%}. "
                    "Check both retrieval and generation quality."
                )

        # Check context vs answer quality
        retrieval_scores = [
            all_avg_scores.get(m) for m in ["context_precision", "context_recall"]
            if m in all_avg_scores
        ]
        generation_scores = [
            all_avg_scores.get(m) for m in ["faithfulness", "answer_relevancy"]
            if m in all_avg_scores
        ]

        if retrieval_scores and generation_scores:
            ret_avg = sum(retrieval_scores) / len(retrieval_scores)
            gen_avg = sum(generation_scores) / len(generation_scores)
            if ret_avg < 0.6 and gen_avg >= 0.7:
                recommendations["trace_level"].append(
                    "DIAGNOSIS: Retrieval is the bottleneck. "
                    "Your LLM generates good answers from context, but the retriever "
                    "isn't fetching the right documents. Focus on improving retrieval."
                )
            elif gen_avg < 0.6 and ret_avg >= 0.7:
                recommendations["trace_level"].append(
                    "DIAGNOSIS: Generation is the bottleneck. "
                    "Your retriever fetches relevant docs, but the LLM isn't using them well. "
                    "Focus on prompt engineering or try a stronger model."
                )

    recommendations["overall_score"] = round(
        sum(all_avg_scores.values()) / len(all_avg_scores), 4
    ) if all_avg_scores else None

    return recommendations
