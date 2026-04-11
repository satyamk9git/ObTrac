"""
Evaluation API - Run RAGAS metrics on traces, with or without ground truth.
"""

import threading
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import logging

from app.db.database import get_db, SessionLocal
from app.db.models import TraceRecord, GroundTruthRecord, LLMConfigRecord, EvalJobRecord

logger = logging.getLogger("obtrac")

router = APIRouter(prefix="/evaluation", tags=["evaluation"])

def _build_litellm_model(config: LLMConfigRecord) -> str:
    """Build the LiteLLM model string from a DB config record."""
    prefixes = {
        "openai": "",
        "azure_openai": "azure/",
        "anthropic": "anthropic/",
        "gemini": "gemini/",
        "vertex_ai": "vertex_ai/",
        "bedrock": "bedrock/",
        "ollama": "ollama/",
        "groq": "groq/",
        "together": "together_ai/",
        "huggingface": "huggingface/",
        "vllm": "openai/",
    }
    prefix = prefixes.get(config.provider, "")
    if config.provider == "azure_openai" and config.azure_deployment:
        return f"azure/{config.azure_deployment}"
    return f"{prefix}{config.model_id}"


# Metric metadata — what each metric does, needs, and thresholds
METRIC_INFO = {
    "faithfulness": {
        "name": "Faithfulness",
        "description": "Measures if the answer is grounded in the retrieved context. Detects hallucination.",
        "needs_ground_truth": False,
        "needs_context": True,
        "threshold": 0.7,
        "category": "Generation Quality",
        "what_it_measures": "How much of the generated answer can be inferred from the retrieved context.",
        "score_interpretation": {
            "good": ">=0.8 — Answer is well-grounded in context",
            "warning": "0.5-0.8 — Some claims not supported by context",
            "bad": "<0.5 — Significant hallucination detected",
        },
        "improvement_tips": [
            "Lower LLM temperature",
            "Add 'Only use provided context' to prompt",
            "Use a more instruction-following model",
            "Reduce context window to avoid noise",
        ],
    },
    "answer_relevancy": {
        "name": "Answer Relevancy",
        "description": "Measures if the answer actually addresses the user's question.",
        "needs_ground_truth": False,
        "needs_context": False,
        "threshold": 0.7,
        "category": "Generation Quality",
        "what_it_measures": "Semantic similarity between the question and the generated answer.",
        "score_interpretation": {
            "good": ">=0.8 — Answer directly addresses the question",
            "warning": "0.5-0.8 — Answer partially relevant",
            "bad": "<0.5 — Answer drifts from the question",
        },
        "improvement_tips": [
            "Rephrase prompt to emphasize answering the exact question",
            "Add explicit instruction to stay on topic",
            "Reduce context length to avoid distraction",
        ],
    },
    "context_precision": {
        "name": "Context Precision",
        "description": "Measures if relevant chunks are ranked higher than irrelevant ones.",
        "needs_ground_truth": True,
        "needs_context": True,
        "threshold": 0.6,
        "category": "Retrieval Quality",
        "what_it_measures": "Whether the most relevant documents appear at the top of retrieved results.",
        "score_interpretation": {
            "good": ">=0.8 — Relevant chunks ranked at top",
            "warning": "0.5-0.8 — Some irrelevant chunks ranked high",
            "bad": "<0.5 — Retrieval ranking is poor",
        },
        "improvement_tips": [
            "Add a reranker (Cohere rerank, cross-encoder)",
            "Tune similarity threshold",
            "Improve chunking strategy (smaller chunks, better overlap)",
            "Use hybrid search (BM25 + vector)",
        ],
    },
    "context_recall": {
        "name": "Context Recall",
        "description": "Measures if all relevant information needed to answer is retrieved.",
        "needs_ground_truth": True,
        "needs_context": True,
        "threshold": 0.6,
        "category": "Retrieval Quality",
        "what_it_measures": "What fraction of the ground truth answer can be attributed to the retrieved context.",
        "score_interpretation": {
            "good": ">=0.8 — Most relevant info was retrieved",
            "warning": "0.5-0.8 — Some relevant info missing",
            "bad": "<0.5 — Critical information not retrieved",
        },
        "improvement_tips": [
            "Increase top_k retrieval count",
            "Use hybrid search (BM25 + vector)",
            "Improve chunking with more overlap",
            "Check if the answer exists in your knowledge base",
        ],
    },
    "answer_correctness": {
        "name": "Answer Correctness",
        "description": "Measures factual correctness of the answer against ground truth.",
        "needs_ground_truth": True,
        "needs_context": False,
        "threshold": 0.7,
        "category": "End-to-End Quality",
        "what_it_measures": "Combination of factual similarity and semantic similarity with ground truth.",
        "score_interpretation": {
            "good": ">=0.8 — Answer is factually correct",
            "warning": "0.5-0.8 — Partially correct",
            "bad": "<0.5 — Significant factual errors",
        },
        "improvement_tips": [
            "Improve retrieval to fetch more relevant context",
            "Use a stronger generation model",
            "Add few-shot examples to your prompt",
        ],
    },
    "answer_similarity": {
        "name": "Answer Similarity",
        "description": "Measures semantic similarity between the generated answer and ground truth.",
        "needs_ground_truth": True,
        "needs_context": False,
        "threshold": 0.7,
        "category": "End-to-End Quality",
        "what_it_measures": "How semantically close the generated answer is to the expected answer.",
        "score_interpretation": {
            "good": ">=0.8 — Highly similar to expected answer",
            "warning": "0.5-0.8 — Somewhat similar",
            "bad": "<0.5 — Very different from expected",
        },
        "improvement_tips": [
            "Use more explicit prompting",
            "Increase context window",
            "Try a model that follows instructions more closely",
        ],
    },
}


@router.get("/metrics-info")
def get_metrics_info():
    """Get detailed information about all available RAGAS metrics."""
    return {
        "metrics": METRIC_INFO,
        "categories": {
            "Generation Quality": {
                "description": "Metrics that evaluate the LLM's answer quality",
                "metrics": [k for k, v in METRIC_INFO.items() if v["category"] == "Generation Quality"],
            },
            "Retrieval Quality": {
                "description": "Metrics that evaluate the retriever's performance",
                "metrics": [k for k, v in METRIC_INFO.items() if v["category"] == "Retrieval Quality"],
            },
            "End-to-End Quality": {
                "description": "Metrics that evaluate the full RAG pipeline output",
                "metrics": [k for k, v in METRIC_INFO.items() if v["category"] == "End-to-End Quality"],
            },
        },
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
    runnable_metrics = []
    skipped_metrics = []
    for m in req.metrics:
        info = METRIC_INFO.get(m)
        if not info:
            skipped_metrics.append({"metric": m, "reason": f"Unknown metric: {m}"})
            continue
        if info["needs_ground_truth"] and not ground_truth:
            skipped_metrics.append({
                "metric": m,
                "reason": "Requires ground truth. Upload via Resources or provide directly.",
            })
            continue
        if info["needs_context"] and not trace.context and not trace.retrieved_chunks:
            skipped_metrics.append({
                "metric": m,
                "reason": "No retrieved context available in this trace.",
            })
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

    # Build evaluation data
    contexts = []
    if trace.context:
        contexts = [trace.context]
    elif trace.retrieved_chunks:
        contexts = [str(c) for c in trace.retrieved_chunks]

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

    # Run RAGAS evaluation
    try:
        import os
        from datasets import Dataset
        from obtrac_sdk.evaluator import _load_ragas_metric, SuggestionEngine

        ragas_metrics = []
        metric_names = []
        for m in runnable_metrics:
            metric_obj = _load_ragas_metric(m)
            if metric_obj:
                ragas_metrics.append(metric_obj)
                metric_names.append(m)

        if not ragas_metrics:
            return {
                "trace_id": req.trace_id,
                "status": "error",
                "error": "Could not load RAGAS metrics. Check if ragas is installed.",
                "skipped": skipped_metrics,
            }

        data = {
            "question": [trace.query],
            "answer": [trace.answer],
            "contexts": [contexts],
        }
        if ground_truth:
            data["ground_truth"] = [ground_truth]

        dataset = Dataset.from_dict(data)

        # Set env vars from LLM config so RAGAS/LiteLLM can find credentials
        # Save originals to restore after
        env_backup = {}
        if judge_config.provider == "azure_openai":
            env_vars = {
                "AZURE_API_KEY": judge_config.api_key or "",
                "AZURE_API_BASE": judge_config.api_base or "",
                "AZURE_API_VERSION": judge_config.api_version or "2024-12-01-preview",
            }
            for k, v in env_vars.items():
                env_backup[k] = os.environ.get(k)
                os.environ[k] = v
        elif judge_config.api_key:
            # For OpenAI, Anthropic, etc — set the key RAGAS expects
            provider_env = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "gemini": "GEMINI_API_KEY",
                "groq": "GROQ_API_KEY",
                "together": "TOGETHER_API_KEY",
            }
            env_key = provider_env.get(judge_config.provider)
            if env_key:
                env_backup[env_key] = os.environ.get(env_key)
                os.environ[env_key] = judge_config.api_key

        # Build LangChain LLM wrapper via LiteLLM
        from langchain_community.chat_models import ChatLiteLLM
        from langchain_community.embeddings import HuggingFaceEmbeddings
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper

        llm_model_string = _build_litellm_model(judge_config)
        llm_kwargs = {}
        if judge_config.api_key:
            llm_kwargs["api_key"] = judge_config.api_key
        if judge_config.api_base:
            llm_kwargs["api_base"] = judge_config.api_base
        if judge_config.provider == "azure_openai" and judge_config.api_version:
            llm_kwargs["api_version"] = judge_config.api_version

        max_tok_key = "max_tokens"
        if judge_config.provider == "azure_openai":
            max_tok_key = "max_completion_tokens"

        lc_llm = ChatLiteLLM(
            model=llm_model_string,
            temperature=0,
            **{max_tok_key: 1024},
            **llm_kwargs,
        )
        lc_embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
        )

        # Wrap for RAGAS 0.4.x
        judge_llm = LangchainLLMWrapper(lc_llm)
        embeddings = LangchainEmbeddingsWrapper(lc_embeddings)

        from ragas import evaluate as ragas_evaluate

        result = ragas_evaluate(
            dataset=dataset,
            metrics=ragas_metrics,
            llm=judge_llm,
            embeddings=embeddings,
        )

        # Restore env vars
        for k, v in env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        import math

        def _extract_score(val):
            if val is None: return None
            if isinstance(val, list): val = val[0] if val else None
            if isinstance(val, dict): val = list(val.values())[0] if val else None
            if val is None: return None
            try:
                f = float(val)
                return round(f, 4) if not (math.isnan(f) or math.isinf(f)) else None
            except: return None

        result_dict = {}
        # Try scores attribute first (RAGAS 0.4.x)
        if hasattr(result, 'scores') and result.scores:
            for score_dict in result.scores:
                if isinstance(score_dict, dict):
                    for m in metric_names:
                        v = _extract_score(score_dict.get(m))
                        if v is not None: result_dict[m] = v
        # Fallback: dict access
        if not result_dict:
            for m in metric_names:
                try:
                    v = _extract_score(result[m])
                    if v is not None: result_dict[m] = v
                except: pass

        # If RAGAS returned all NaN (Azure compatibility issue), note it
        if not result_dict and metric_names:
            logger.warning(f"RAGAS returned NaN for all metrics. This is a known RAGAS 0.4.x + Azure OpenAI issue.")
            return {
                "trace_id": req.trace_id,
                "status": "partial",
                "metrics": {},
                "suggestions": ["RAGAS evaluation returned NaN. This is a known compatibility issue with RAGAS 0.4.x and Azure OpenAI. Try running evaluation manually or use a different judge LLM."],
                "skipped": skipped_metrics,
                "ground_truth_used": bool(ground_truth),
                "judge_llm": f"{judge_config.provider}/{judge_config.model_id}",
                "note": "RAGAS 0.4.x may not fully support Azure OpenAI for some metrics. The LLM call succeeded but RAGAS could not parse the response.",
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

    # Filter metrics
    runnable_metrics = []
    skipped_metrics = []
    for m in req.metrics:
        info = METRIC_INFO.get(m)
        if not info:
            skipped_metrics.append({"metric": m, "reason": f"Unknown metric"})
            continue
        if info["needs_ground_truth"] and not ground_truth:
            skipped_metrics.append({"metric": m, "reason": "Requires ground truth"})
            continue
        if info["needs_context"] and not trace.context and not trace.retrieved_chunks:
            skipped_metrics.append({"metric": m, "reason": "No context available"})
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

    # Build context and dataset
    contexts = []
    if trace.context:
        contexts = [trace.context]
    elif trace.retrieved_chunks:
        contexts = [str(c) for c in trace.retrieved_chunks]

    # Run evaluation for EACH LLM
    llm_results = []
    for idx, llm_cfg in enumerate(llm_configs):
        _set_progress(f"Evaluating with {llm_cfg.name} ({idx+1}/{len(llm_configs)})...")
        llm_result = _run_single_llm_eval(
            trace, llm_cfg, runnable_metrics, contexts, ground_truth
        )
        llm_results.append(llm_result)

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


def _run_single_llm_eval(trace, llm_cfg, metrics, contexts, ground_truth) -> dict:
    """Run evaluation with a single LLM judge."""
    import os

    try:
        from datasets import Dataset
        from obtrac_sdk.evaluator import _load_ragas_metric

        ragas_metrics = []
        metric_names = []
        for m in metrics:
            obj = _load_ragas_metric(m)
            if obj:
                ragas_metrics.append(obj)
                metric_names.append(m)

        if not ragas_metrics:
            return {
                "llm_name": llm_cfg.name,
                "llm_provider": llm_cfg.provider,
                "llm_model": llm_cfg.model_id,
                "status": "error",
                "error": "Could not load metrics",
                "metrics": {},
            }

        data = {
            "question": [trace.query],
            "answer": [trace.answer],
            "contexts": [contexts],
        }
        if ground_truth:
            data["ground_truth"] = [ground_truth]

        dataset = Dataset.from_dict(data)

        # Set env vars
        env_backup = {}
        if llm_cfg.provider == "azure_openai":
            env_vars = {
                "AZURE_API_KEY": llm_cfg.api_key or "",
                "AZURE_API_BASE": llm_cfg.api_base or "",
                "AZURE_API_VERSION": llm_cfg.api_version or "2024-12-01-preview",
            }
            for k, v in env_vars.items():
                env_backup[k] = os.environ.get(k)
                os.environ[k] = v
        elif llm_cfg.api_key:
            provider_env = {
                "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
                "gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY",
            }
            env_key = provider_env.get(llm_cfg.provider)
            if env_key:
                env_backup[env_key] = os.environ.get(env_key)
                os.environ[env_key] = llm_cfg.api_key

        from langchain_community.chat_models import ChatLiteLLM
        from langchain_community.embeddings import HuggingFaceEmbeddings
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper

        model_string = _build_litellm_model(llm_cfg)
        llm_kwargs = {}
        if llm_cfg.api_key:
            llm_kwargs["api_key"] = llm_cfg.api_key
        if llm_cfg.api_base:
            llm_kwargs["api_base"] = llm_cfg.api_base
        if llm_cfg.provider == "azure_openai" and llm_cfg.api_version:
            llm_kwargs["api_version"] = llm_cfg.api_version

        max_tok_key = "max_completion_tokens" if llm_cfg.provider == "azure_openai" else "max_tokens"
        lc_llm = ChatLiteLLM(
            model=model_string, temperature=0,
            **{max_tok_key: 1024}, **llm_kwargs,
        )
        lc_embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
        )

        # Wrap for RAGAS 0.4.x
        judge_llm = LangchainLLMWrapper(lc_llm)
        embeddings = LangchainEmbeddingsWrapper(lc_embeddings)

        from ragas import evaluate as ragas_evaluate
        result = ragas_evaluate(
            dataset=dataset, metrics=ragas_metrics,
            llm=judge_llm, embeddings=embeddings,
        )

        # Restore env
        for k, v in env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

        result_dict = {}
        # RAGAS 0.4.x: result can be dict-like or have .scores / .to_pandas()
        import math
        logger.info(f"RAGAS result type: {type(result)}, scores: {getattr(result, 'scores', None)}")

        def _extract_score(val):
            """Extract a valid float from RAGAS result value (handles list, nan, None)."""
            if val is None:
                return None
            if isinstance(val, list):
                val = val[0] if val else None
            if isinstance(val, dict):
                val = list(val.values())[0] if val else None
            if val is None:
                return None
            try:
                f = float(val)
                if math.isnan(f) or math.isinf(f):
                    return None
                return round(f, 4)
            except (TypeError, ValueError):
                return None

        # Method 1: scores attribute (RAGAS 0.4.x)
        if hasattr(result, 'scores') and result.scores:
            for score_dict in result.scores:
                if isinstance(score_dict, dict):
                    for m in metric_names:
                        if m in score_dict:
                            v = _extract_score(score_dict[m])
                            if v is not None:
                                result_dict[m] = v

        # Method 2: dict-like access
        if not result_dict:
            for m in metric_names:
                try:
                    v = _extract_score(result[m])
                    if v is not None:
                        result_dict[m] = v
                except (KeyError, TypeError):
                    pass

        # Method 3: to_pandas
        if not result_dict and hasattr(result, 'to_pandas'):
            try:
                df = result.to_pandas()
                for m in metric_names:
                    if m in df.columns:
                        v = _extract_score(df[m].iloc[0])
                        if v is not None:
                            result_dict[m] = v
            except Exception:
                pass

        return {
            "llm_name": llm_cfg.name,
            "llm_provider": llm_cfg.provider,
            "llm_model": llm_cfg.model_id,
            "status": "success",
            "metrics": result_dict,
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
    for m, scores in metric_scores.items():
        info = METRIC_INFO.get(m, {})
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
        info = METRIC_INFO.get(weakest[0], {})

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
