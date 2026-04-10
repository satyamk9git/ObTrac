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
