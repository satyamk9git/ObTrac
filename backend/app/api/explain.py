"""
Metric Explanation API — get detailed reasoning + improvement techniques for any metric score.
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db.database import get_db
from app.db.models import TraceRecord, LLMConfigRecord

router = APIRouter(prefix="/explain", tags=["explain"])


# Static metric knowledge base
METRIC_KNOWLEDGE = {
    "faithfulness": {
        "what": "Measures how grounded the answer is in the retrieved context. A low score means the LLM is hallucinating — saying things not supported by the context.",
        "scoring": "1.0 = every claim in the answer is supported by context. 0.0 = answer is fully hallucinated.",
        "common_causes_low": [
            "LLM temperature too high → creative but ungrounded outputs",
            "Prompt doesn't explicitly say 'use only the provided context'",
            "Retrieved context is irrelevant → LLM falls back on its training data",
            "Context is too long → LLM ignores parts of it",
            "Model is too small/weak to follow instructions",
        ],
        "improvement_techniques": [
            "Lower temperature to 0.0-0.2",
            "Add 'Answer ONLY using the provided context. If not in context, say so' to your prompt",
            "Improve retrieval quality (better chunking, reranker, hybrid search)",
            "Use a stronger instruction-following model (gpt-4o, claude-opus)",
            "Add few-shot examples showing context-grounded answers",
            "Use chain-of-thought: ask LLM to first list what's in context, then answer",
        ],
    },
    "answer_relevancy": {
        "what": "Measures whether the answer actually addresses the user's question. A low score means the answer is off-topic or evasive.",
        "scoring": "1.0 = perfectly addresses the question. 0.0 = completely off-topic.",
        "common_causes_low": [
            "Answer drifts to related but unrelated topics",
            "Answer is too verbose, burying the main point",
            "Question is ambiguous → LLM picks the wrong interpretation",
            "Prompt encourages tangents (e.g., 'provide additional context')",
            "RAGAS bias against very short answers (e.g., 'Yes', 'Paris')",
        ],
        "improvement_techniques": [
            "Add 'Answer the question directly without preamble' to your prompt",
            "Use reformulation: rephrase the user query before retrieval",
            "Limit max_tokens to prevent rambling",
            "For factual Q&A, instruct: 'Reply in 1-2 sentences'",
            "Add output format constraints (e.g., JSON schema)",
            "Test with longer reference answers if your answers are very short",
        ],
    },
    "context_precision": {
        "what": "Measures whether the retrieved chunks are relevant to the question. A low score means your retriever is fetching noise.",
        "scoring": "1.0 = all retrieved chunks are relevant. 0.0 = none of them help.",
        "common_causes_low": [
            "Top-k is too high (retrieving 10 chunks when 3 are needed)",
            "Embedding model is generic (not domain-tuned)",
            "Documents are poorly chunked (chunks too small/large)",
            "Query and documents have vocabulary mismatch (e.g., abbreviations)",
            "No reranker → similarity scores are noisy",
        ],
        "improvement_techniques": [
            "Add a reranker (Cohere Rerank, cross-encoder, BGE reranker)",
            "Reduce top_k from 10 → 3-5",
            "Use hybrid search (BM25 + vector) — handles exact term matches",
            "Improve chunking: 200-500 tokens with 50 token overlap",
            "Use HyDE: generate hypothetical answer first, then retrieve on that",
            "Fine-tune embeddings on your domain (e.g., medical, legal)",
            "Add metadata filters (date, category, source)",
        ],
    },
    "context_recall": {
        "what": "Measures whether the retrieved context contains all the information needed to answer the question. A low score means relevant info is missing.",
        "scoring": "1.0 = all required info was retrieved. 0.0 = nothing relevant retrieved.",
        "common_causes_low": [
            "Top-k too low — relevant chunk wasn't in top results",
            "Information is split across multiple chunks (none fully relevant)",
            "Query embedding doesn't match the document's phrasing",
            "Documents not in the index at all",
            "Chunk overlap is 0 → context cut at boundaries",
        ],
        "improvement_techniques": [
            "Increase top_k to 10-15",
            "Use parent document retrieval: retrieve small chunks, return their parents",
            "Add chunk overlap (50-100 tokens) so context isn't cut",
            "Use multi-query retrieval: rephrase the query 3 ways, union results",
            "Improve chunking strategy: semantic chunking instead of fixed-size",
            "Verify all source documents are indexed (run a sanity check)",
            "Use larger embedding model (better recall vs precision tradeoff)",
        ],
    },
    "answer_correctness": {
        "what": "Combines factual + semantic similarity between the answer and the ground truth. Measures end-to-end correctness.",
        "scoring": "1.0 = answer matches ground truth in facts and meaning. 0.0 = completely wrong.",
        "common_causes_low": [
            "Wrong information generated (factual error)",
            "Answer is correct but worded very differently from ground truth",
            "Missing key facts that ground truth contains",
            "Adding incorrect facts not in ground truth",
            "Unit/format mismatch (e.g., '5' vs 'five')",
        ],
        "improvement_techniques": [
            "Improve retrieval (most factual errors come from missing context)",
            "Use a stronger LLM for generation",
            "Add few-shot examples that match your ground truth style",
            "Post-process answers to normalize format (numbers, dates, names)",
            "Verify facts with a second LLM call (self-consistency)",
            "Use structured output (JSON) to enforce specific fields",
        ],
    },
    "answer_similarity": {
        "what": "Measures semantic similarity (cosine distance) between the answer and ground truth. Lower-bound check for correctness.",
        "scoring": "1.0 = semantically identical. 0.0 = completely different topics.",
        "common_causes_low": [
            "Answer is too short compared to ground truth (or vice versa)",
            "Different vocabulary used (synonyms not captured by embeddings)",
            "Answer is in a different format/structure",
            "Embedding model is not domain-specific",
        ],
        "improvement_techniques": [
            "Match the format/length of your ground truth in your prompts",
            "Use a more powerful embedding model (text-embedding-3-large)",
            "Normalize both answers (lowercase, strip punctuation) before comparison",
            "Generate ground truth and answers using the same LLM family",
        ],
    },
}


class ExplainRequest(BaseModel):
    trace_id: str
    metric: str
    score: float
    use_llm: bool = True
    llm_config_id: Optional[str] = None


@router.post("/metric")
def explain_metric(req: ExplainRequest, db: Session = Depends(get_db)):
    """
    Explain why a metric got a particular score and how to improve it.

    Combines:
    1. Static knowledge base (always returned)
    2. LLM-generated trace-specific reasoning (optional)
    """
    knowledge = METRIC_KNOWLEDGE.get(req.metric)
    if not knowledge:
        raise HTTPException(404, f"Unknown metric: {req.metric}")

    trace = db.query(TraceRecord).filter(TraceRecord.trace_id == req.trace_id).first()
    if not trace:
        raise HTTPException(404, "Trace not found")

    # Determine severity
    if req.score >= 0.8:
        severity = "good"
        verdict = f"Excellent — {req.metric.replace('_', ' ')} of {req.score*100:.1f}% indicates this metric is performing well."
    elif req.score >= 0.6:
        severity = "warning"
        verdict = f"Acceptable but improvable — {req.metric.replace('_', ' ')} of {req.score*100:.1f}% has room to grow."
    else:
        severity = "critical"
        verdict = f"Below threshold — {req.metric.replace('_', ' ')} of {req.score*100:.1f}% needs attention."

    response = {
        "metric": req.metric,
        "score": req.score,
        "severity": severity,
        "verdict": verdict,
        "what_it_measures": knowledge["what"],
        "scoring": knowledge["scoring"],
        "common_causes": knowledge["common_causes_low"] if req.score < 0.8 else [],
        "improvement_techniques": knowledge["improvement_techniques"] if req.score < 0.8 else [],
        "trace_specific_analysis": None,
    }

    # Optional: LLM-powered trace-specific analysis
    if req.use_llm and req.score < 0.9:
        try:
            llm_cfg = None
            if req.llm_config_id:
                llm_cfg = db.query(LLMConfigRecord).filter(LLMConfigRecord.id == req.llm_config_id).first()
            if not llm_cfg:
                llm_cfg = (
                    db.query(LLMConfigRecord)
                    .filter(LLMConfigRecord.use_for_auto_eval == True, LLMConfigRecord.is_active == True)
                    .first()
                )
            if not llm_cfg:
                llm_cfg = db.query(LLMConfigRecord).filter(LLMConfigRecord.is_active == True).first()

            if llm_cfg:
                analysis = _llm_analyze_trace(
                    trace=trace,
                    metric=req.metric,
                    score=req.score,
                    llm_cfg=llm_cfg,
                )
                response["trace_specific_analysis"] = analysis
        except Exception as e:
            response["trace_specific_analysis"] = {"error": str(e)[:200]}

    return response


def _llm_analyze_trace(trace: TraceRecord, metric: str, score: float, llm_cfg: LLMConfigRecord) -> dict:
    """Use an LLM to analyze why this specific trace got this score."""
    from litellm import completion

    # Build analysis prompt
    prompt = f"""You are a RAG observability expert. Analyze why this trace got a low score for the metric '{metric}'.

Question: {trace.query or 'N/A'}
Retrieved Context: {(trace.context or 'N/A')[:2000]}
Generated Answer: {(trace.answer or 'N/A')[:1500]}
Ground Truth: {trace.ground_truth or 'Not provided'}

Metric: {metric}
Score: {score:.2f} (out of 1.0)

Provide a JSON response with these keys:
- "diagnosis": one specific reason why THIS particular trace failed (be concrete, reference the actual content)
- "evidence": quote the specific text from the trace that supports your diagnosis
- "fix": one specific actionable fix for this trace
- "priority": one of "high", "medium", "low"

Reply with ONLY the JSON object, no markdown."""

    # Build LLM call
    prefixes = {
        "openai": "", "azure_openai": "azure/", "anthropic": "anthropic/",
        "gemini": "gemini/", "ollama": "ollama/", "groq": "groq/",
    }
    prefix = prefixes.get(llm_cfg.provider, "")
    if llm_cfg.provider == "azure_openai" and llm_cfg.azure_deployment:
        model = f"azure/{llm_cfg.azure_deployment}"
    else:
        model = f"{prefix}{llm_cfg.model_id}"

    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    if llm_cfg.provider == "azure_openai":
        kwargs["max_completion_tokens"] = 800
        kwargs["api_version"] = llm_cfg.api_version
    else:
        kwargs["max_tokens"] = 800
    if llm_cfg.api_key:
        kwargs["api_key"] = llm_cfg.api_key
    if llm_cfg.api_base:
        kwargs["api_base"] = llm_cfg.api_base

    response = completion(**kwargs)
    text = response.choices[0].message.content.strip()

    # Parse JSON
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: return as plain text
        return {"diagnosis": text, "evidence": "", "fix": "", "priority": "medium"}


# =====================================================================
# PROJECT-LEVEL AI INSIGHTS — analyze the whole project's metrics
# =====================================================================

import time as _time

# Cache: {project: (timestamp, payload)} — TTL 10 minutes so refreshes don't burn tokens
_project_insights_cache: dict = {}
_PROJECT_INSIGHTS_TTL = 600  # 10 minutes


class ProjectInsightsRequest(BaseModel):
    project: str
    refresh: bool = False  # if True, ignores cache and re-runs the analysis


@router.post("/project-metrics")
def explain_project_metrics(req: ProjectInsightsRequest, db: Session = Depends(get_db)):
    """
    Use an LLM to analyze a project's overall RAGAS metrics and identify
    patterns, root causes, and high-leverage fixes — at the AGGREGATE level
    rather than the per-trace level.

    Cached for 10 minutes per project to avoid burning tokens on refresh.
    """
    cache_key = req.project
    now = _time.time()

    if not req.refresh and cache_key in _project_insights_cache:
        ts, cached = _project_insights_cache[cache_key]
        if now - ts < _PROJECT_INSIGHTS_TTL:
            cached["from_cache"] = True
            cached["cache_age_seconds"] = int(now - ts)
            return cached

    # 1. Fetch all evaluated traces in this project
    traces = (
        db.query(TraceRecord)
        .filter(TraceRecord.project == req.project)
        .filter(TraceRecord.metrics != None)
        .order_by(TraceRecord.created_at.desc())
        .limit(200)
        .all()
    )

    # Filter for traces that actually have metric data
    evaluated = [t for t in traces if t.metrics and isinstance(t.metrics, dict) and len(t.metrics) > 0]

    if not evaluated:
        return {
            "project": req.project,
            "status": "no_data",
            "message": "No evaluated traces in this project. Run RAGAS evaluation on some traces first.",
        }

    # 2. Compute aggregate metric averages
    metric_sums: dict = {}
    metric_counts: dict = {}
    for t in evaluated:
        for k, v in (t.metrics or {}).items():
            if isinstance(v, (int, float)) and v == v:  # filter NaN
                metric_sums[k] = metric_sums.get(k, 0.0) + float(v)
                metric_counts[k] = metric_counts.get(k, 0) + 1

    avg_metrics = {
        k: round(metric_sums[k] / metric_counts[k], 3)
        for k in metric_sums
        if metric_counts[k] > 0
    }

    if not avg_metrics:
        return {
            "project": req.project,
            "status": "no_data",
            "message": "Traces exist but contain no numeric metric scores.",
        }

    # 3. Identify the worst metric and pull example traces that triggered it
    worst_metric = min(avg_metrics, key=avg_metrics.get)
    worst_score = avg_metrics[worst_metric]

    # Sort traces by the worst metric ascending and grab the bottom 3
    sortable = [
        t for t in evaluated
        if isinstance((t.metrics or {}).get(worst_metric), (int, float))
    ]
    sortable.sort(key=lambda t: t.metrics.get(worst_metric, 1.0))
    bottom_traces = sortable[:3]

    examples = []
    for t in bottom_traces:
        examples.append({
            "trace_id": t.trace_id[:12],
            "query": (t.query or "")[:200],
            "answer": (t.answer or "")[:300],
            "context_snippet": (t.context or "")[:400],
            "ground_truth": (t.ground_truth or "")[:200] if t.ground_truth else None,
            "scores": {k: round(v, 3) for k, v in (t.metrics or {}).items() if isinstance(v, (int, float)) and v == v},
        })

    # 4. Pick an LLM to do the analysis
    llm_cfg = (
        db.query(LLMConfigRecord)
        .filter(LLMConfigRecord.use_for_auto_eval == True, LLMConfigRecord.is_active == True)
        .first()
    )
    if not llm_cfg:
        llm_cfg = db.query(LLMConfigRecord).filter(LLMConfigRecord.is_active == True).first()
    if not llm_cfg:
        return {
            "project": req.project,
            "status": "no_llm",
            "message": "No LLM configured. Add one in LLM Config and mark it 'Use for Auto-Evaluation'.",
        }

    # 5. Build the prompt
    metrics_table = "\n".join([
        f"  - {name}: {score:.1%}"
        for name, score in sorted(avg_metrics.items(), key=lambda x: x[1])
    ])

    examples_text = "\n\n".join([
        f"--- Trace {ex['trace_id']} ---\n"
        f"Question: {ex['query']}\n"
        f"Answer: {ex['answer']}\n"
        f"Context: {ex['context_snippet']}\n"
        f"Ground truth: {ex['ground_truth'] or '(none)'}\n"
        f"Scores: {ex['scores']}"
        for ex in examples
    ])

    prompt = f"""You are a RAG observability expert reviewing the aggregate metrics for a production RAG system.

PROJECT: {req.project}
TOTAL EVALUATED TRACES: {len(evaluated)}

AVERAGE METRIC SCORES (sorted worst-first):
{metrics_table}

WORST METRIC: {worst_metric} ({worst_score:.1%})

THREE LOWEST-SCORING TRACES ON THIS METRIC:
{examples_text}

Analyze the patterns ACROSS these traces (not each one individually) and produce a JSON response:

{{
  "health": "good" | "warning" | "critical",
  "headline": "One-sentence summary of the system's health",
  "top_issues": [
    {{
      "metric": "metric name",
      "severity": "high" | "medium" | "low",
      "pattern": "What's happening across the bad traces (not just one)",
      "root_cause": "Why this is happening — be specific about the RAG pipeline component"
    }}
  ],
  "highest_leverage_fix": {{
    "title": "Short action title",
    "description": "What to do, in 2-3 sentences",
    "expected_impact": "Which metrics will improve and by roughly how much",
    "code_or_config_example": "A small concrete code snippet or config change"
  }},
  "whats_working": "What the system is doing well — be specific so the user doesn't accidentally regress it",
  "next_steps": ["Action 1", "Action 2", "Action 3"]
}}

Return ONLY the JSON object, no markdown fences."""

    # 6. Call the LLM
    try:
        from litellm import completion
        prefixes = {
            "openai": "", "azure_openai": "azure/", "anthropic": "anthropic/",
            "gemini": "gemini/", "ollama": "ollama/", "groq": "groq/",
        }
        prefix = prefixes.get(llm_cfg.provider, "")
        if llm_cfg.provider == "azure_openai" and llm_cfg.azure_deployment:
            model = f"azure/{llm_cfg.azure_deployment}"
        else:
            model = f"{prefix}{llm_cfg.model_id}"

        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        if llm_cfg.provider == "azure_openai":
            kwargs["max_completion_tokens"] = 1500
            kwargs["api_version"] = llm_cfg.api_version
        else:
            kwargs["max_tokens"] = 1500
        if llm_cfg.api_key:
            kwargs["api_key"] = llm_cfg.api_key
        if llm_cfg.api_base:
            kwargs["api_base"] = llm_cfg.api_base

        resp = completion(**kwargs)
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        try:
            insights = json.loads(text)
        except json.JSONDecodeError:
            insights = {
                "health": "warning",
                "headline": "Analysis returned in non-JSON format",
                "raw_response": text[:1500],
            }

    except Exception as e:
        return {
            "project": req.project,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)[:300]}",
        }

    payload = {
        "project": req.project,
        "status": "ok",
        "evaluated_traces": len(evaluated),
        "worst_metric": worst_metric,
        "worst_score": worst_score,
        "avg_metrics": avg_metrics,
        "analyzed_by": f"{llm_cfg.provider}/{llm_cfg.model_id}",
        "insights": insights,
        "from_cache": False,
        "cache_age_seconds": 0,
        "generated_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
    }

    _project_insights_cache[cache_key] = (now, payload)
    return payload


# =====================================================================
# CORRELATION ANALYSIS — interpret a metric correlation matrix
# =====================================================================

_correlation_insights_cache: dict = {}
_CORRELATION_TTL = 600  # 10 minutes


class CorrelationInsightsRequest(BaseModel):
    project: str
    refresh: bool = False


@router.post("/correlation")
def explain_correlation(req: CorrelationInsightsRequest, db: Session = Depends(get_db)):
    """
    Use an LLM to interpret a project's metric correlation matrix in plain
    English. Identifies meaningful patterns, anti-correlations, and what
    they imply about the RAG pipeline.

    Cached for 10 minutes per project.
    """
    cache_key = req.project
    now = _time.time()

    if not req.refresh and cache_key in _correlation_insights_cache:
        ts, cached = _correlation_insights_cache[cache_key]
        if now - ts < _CORRELATION_TTL:
            cached["from_cache"] = True
            cached["cache_age_seconds"] = int(now - ts)
            return cached

    # 1. Compute the correlation matrix from the project's evaluated traces
    traces = (
        db.query(TraceRecord)
        .filter(TraceRecord.project == req.project)
        .filter(TraceRecord.metrics != None)
        .order_by(TraceRecord.created_at.desc())
        .limit(500)
        .all()
    )
    evaluated = [t for t in traces if t.metrics and isinstance(t.metrics, dict) and len(t.metrics) > 0]

    if len(evaluated) < 3:
        return {
            "project": req.project,
            "status": "insufficient_data",
            "message": f"Need at least 3 evaluated traces to analyze correlation. Found {len(evaluated)}.",
        }

    # Build per-metric value lists
    metric_values: dict = {}
    for t in evaluated:
        for k, v in (t.metrics or {}).items():
            if isinstance(v, (int, float)) and v == v:
                metric_values.setdefault(k, []).append(float(v))

    # Filter to metrics that have enough samples and variance
    valid_metrics = {}
    for k, vals in metric_values.items():
        if len(vals) >= 3:
            # Need some variance to compute correlation
            if max(vals) - min(vals) > 1e-6:
                valid_metrics[k] = vals

    if len(valid_metrics) < 2:
        return {
            "project": req.project,
            "status": "insufficient_data",
            "message": "Need at least 2 metrics with variance to compute correlations.",
        }

    # Compute Pearson correlation between all pairs
    def _pearson(xs, ys):
        n = min(len(xs), len(ys))
        if n < 2:
            return 0.0
        xs, ys = xs[:n], ys[:n]
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        dx = (sum((x - mx) ** 2 for x in xs)) ** 0.5
        dy = (sum((y - my) ** 2 for y in ys)) ** 0.5
        if dx == 0 or dy == 0:
            return 0.0
        return num / (dx * dy)

    metric_names = sorted(valid_metrics.keys())
    matrix_text_lines = []
    notable_pairs = []
    for i, m1 in enumerate(metric_names):
        for j, m2 in enumerate(metric_names):
            if j <= i:
                continue
            r = round(_pearson(valid_metrics[m1], valid_metrics[m2]), 3)
            matrix_text_lines.append(f"  {m1} ↔ {m2}: {r:+.2f}")
            # Track strong correlations for highlighting
            if abs(r) >= 0.5:
                notable_pairs.append((m1, m2, r))

    matrix_text = "\n".join(matrix_text_lines)

    # 2. Pick an LLM
    llm_cfg = (
        db.query(LLMConfigRecord)
        .filter(LLMConfigRecord.use_for_auto_eval == True, LLMConfigRecord.is_active == True)
        .first()
    )
    if not llm_cfg:
        llm_cfg = db.query(LLMConfigRecord).filter(LLMConfigRecord.is_active == True).first()
    if not llm_cfg:
        return {
            "project": req.project,
            "status": "no_llm",
            "message": "No LLM configured. Add one in LLM Config and mark it 'Use for Auto-Evaluation'.",
        }

    # 3. Build the prompt
    prompt = f"""You are a RAG observability expert analyzing how metrics relate to each other in a production RAG system.

PROJECT: {req.project}
EVALUATED TRACES: {len(evaluated)}

PEARSON CORRELATION COEFFICIENTS BETWEEN METRIC PAIRS:
(values range from -1.0 to +1.0 where +1.0 = always move together, -1.0 = always move opposite, 0 = independent)

{matrix_text}

Analyze ONLY the meaningful patterns (correlations above |0.5|). For each notable pattern, explain in plain English what it implies about the RAG pipeline (retriever, generator, prompt, model, etc.).

Return JSON in this format:

{{
  "summary": "One-sentence headline about what the correlation matrix reveals",
  "expected_patterns": [
    {{
      "pair": "metric_a ↔ metric_b",
      "correlation": 0.85,
      "interpretation": "Why this is expected and what it means"
    }}
  ],
  "concerning_patterns": [
    {{
      "pair": "metric_a ↔ metric_b",
      "correlation": -0.4,
      "interpretation": "Why this is unusual",
      "likely_cause": "What's probably happening in the pipeline",
      "investigation_step": "What to check next"
    }}
  ],
  "key_insight": "The single most important takeaway from this matrix — what should the user act on?",
  "no_action_needed_if": "What's normal and doesn't need investigation"
}}

Return ONLY the JSON, no markdown fences."""

    # 4. Call the LLM
    try:
        from litellm import completion
        prefixes = {
            "openai": "", "azure_openai": "azure/", "anthropic": "anthropic/",
            "gemini": "gemini/", "ollama": "ollama/", "groq": "groq/",
        }
        prefix = prefixes.get(llm_cfg.provider, "")
        if llm_cfg.provider == "azure_openai" and llm_cfg.azure_deployment:
            model = f"azure/{llm_cfg.azure_deployment}"
        else:
            model = f"{prefix}{llm_cfg.model_id}"

        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        if llm_cfg.provider == "azure_openai":
            kwargs["max_completion_tokens"] = 1500
            kwargs["api_version"] = llm_cfg.api_version
        else:
            kwargs["max_tokens"] = 1500
        if llm_cfg.api_key:
            kwargs["api_key"] = llm_cfg.api_key
        if llm_cfg.api_base:
            kwargs["api_base"] = llm_cfg.api_base

        resp = completion(**kwargs)
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        try:
            insights = json.loads(text)
        except json.JSONDecodeError:
            insights = {
                "summary": "Analysis returned in non-JSON format",
                "raw_response": text[:1500],
            }
    except Exception as e:
        return {
            "project": req.project,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)[:300]}",
        }

    payload = {
        "project": req.project,
        "status": "ok",
        "evaluated_traces": len(evaluated),
        "metric_count": len(metric_names),
        "notable_pair_count": len(notable_pairs),
        "analyzed_by": f"{llm_cfg.provider}/{llm_cfg.model_id}",
        "insights": insights,
        "from_cache": False,
        "cache_age_seconds": 0,
        "generated_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
    }

    _correlation_insights_cache[cache_key] = (now, payload)
    return payload
