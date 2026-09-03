"""
ObTrac's 6 original RAGAS-style metrics, now expressed as MetricDefinition
instances instead of the four hardcoded dicts they used to live in
(JUDGE_PROMPTS + METRIC_INFO + SuggestionEngine.RULES + METRIC_KNOWLEDGE).

The actual LLM-call/JSON-parsing logic is NOT duplicated here — LLMJudgeMetric
delegates to app.services.llm_judge's existing _build_llm/_score_one_metric,
so behavior is byte-for-byte identical to before this registry existed. That
module also stays importable standalone (scripts/dev/run_llm_judge_evals.py
still uses it directly).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.metrics.base import MetricDefinition, MetricInput, MetricResult

if TYPE_CHECKING:
    from app.db.models import LLMConfigRecord


class LLMJudgeMetric(MetricDefinition):
    """A metric scored by asking a judge LLM to fill in a prompt template
    and return {"score": 0.0-1.0, "reason": "..."} as JSON."""

    source = "obtrac"

    def __init__(self, key: str, prompt_template: str, **info):
        self.key = key
        self.prompt_template = prompt_template
        self.display_name = info.get("name", key)
        self.description = info.get("description", "")
        self.needs_ground_truth = info.get("needs_ground_truth", False)
        self.needs_context = info.get("needs_context", False)
        self.threshold = info.get("threshold", 0.7)
        self.category = info.get("category", "Uncategorized")
        self.what_it_measures = info.get("what_it_measures", "")
        self.score_interpretation = info.get("score_interpretation", {})
        self.improvement_tips = info.get("improvement_tips", [])

    def score(self, inp: MetricInput, judge_llm: "LLMConfigRecord | None") -> MetricResult:
        if judge_llm is None:
            return MetricResult(metric=self.key, error="No judge LLM configured")

        from app.services.llm_judge import _build_llm, _score_one_metric

        llm = _build_llm(judge_llm)
        _, score, reason = _score_one_metric(
            llm, self.key, self.prompt_template,
            inp.question, inp.answer, inp.context, inp.ground_truth,
        )
        if score is None:
            return MetricResult(metric=self.key, error="Judge LLM did not return a valid score")
        return MetricResult(metric=self.key, score=score, reason=reason or "")


# Metadata that used to live in backend/app/api/evaluation.py's METRIC_INFO —
# moved here so it travels with the prompt template it describes instead of
# being a separately-maintained dict.
_METRIC_METADATA = {
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
        # Ground truth was needed by RAGAS's specific context_precision
        # implementation; our llm_judge.py judge scores this from just the
        # question + retrieved context, so gating it on ground_truth here
        # would wrongly skip it whenever no ground truth is available —
        # which is most of the time.
        "needs_ground_truth": False,
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


def build_metrics() -> list[LLMJudgeMetric]:
    """Construct the 6 built-in metric instances. Imports JUDGE_PROMPTS
    lazily to avoid a hard import-time dependency between the metrics
    package and llm_judge.py (which itself imports litellm)."""
    from app.services.llm_judge import JUDGE_PROMPTS

    return [
        LLMJudgeMetric(key=key, prompt_template=JUDGE_PROMPTS[key], **meta)
        for key, meta in _METRIC_METADATA.items()
    ]
