"""
RAGAS evaluation engine for computing RAG quality metrics.
"""

import logging
from typing import Any

from datasets import Dataset

from obtrac_sdk.models import Trace, EvalResult

logger = logging.getLogger("obtrac")

# Metric name to RAGAS metric object mapping
AVAILABLE_METRICS = {
    "faithfulness": "ragas.metrics.faithfulness",
    "answer_relevancy": "ragas.metrics.answer_relevancy",
    "context_precision": "ragas.metrics.context_precision",
    "context_recall": "ragas.metrics.context_recall",
    "answer_correctness": "ragas.metrics.answer_correctness",
    "answer_similarity": "ragas.metrics.answer_similarity",
    "harmfulness": "ragas.metrics.harmfulness",
}

# Metrics that require ground truth
GROUND_TRUTH_METRICS = {
    "context_recall",
    "answer_correctness",
    "answer_similarity",
}


def _load_ragas_metric(metric_name: str):
    """Dynamically load a RAGAS metric by name."""
    try:
        from ragas.metrics import (
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
            answer_correctness,
            answer_similarity,
        )

        metric_map = {
            "faithfulness": faithfulness,
            "answer_relevancy": answer_relevancy,
            "context_precision": context_precision,
            "context_recall": context_recall,
            "answer_correctness": answer_correctness,
            "answer_similarity": answer_similarity,
        }

        return metric_map.get(metric_name)
    except ImportError as e:
        logger.warning(f"Could not load RAGAS metric '{metric_name}': {e}")
        return None


class SuggestionEngine:
    """Generates actionable suggestions based on metric scores."""

    RULES = {
        "faithfulness": {
            "threshold": 0.7,
            "low_suggestion": (
                "The LLM is generating information not found in the retrieved context "
                "(hallucination). Try: (1) Lower temperature, (2) Add 'Only answer "
                "based on the provided context' to your prompt, (3) Use a more "
                "instruction-following model."
            ),
        },
        "answer_relevancy": {
            "threshold": 0.7,
            "low_suggestion": (
                "The answer is drifting from the original question. Try: "
                "(1) Rephrase your prompt template to emphasize answering the exact "
                "question, (2) Reduce context length to avoid distraction, "
                "(3) Add explicit instruction to stay on topic."
            ),
        },
        "context_precision": {
            "threshold": 0.6,
            "low_suggestion": (
                "Irrelevant chunks are being retrieved and ranked high. Try: "
                "(1) Add a reranker (e.g., Cohere rerank, cross-encoder), "
                "(2) Tune similarity threshold, (3) Improve chunking strategy "
                "(smaller chunks, better overlap), (4) Use hybrid search."
            ),
        },
        "context_recall": {
            "threshold": 0.6,
            "low_suggestion": (
                "Important information is missing from retrieved context. Try: "
                "(1) Increase top_k, (2) Use hybrid search (BM25 + vector), "
                "(3) Improve document chunking with more overlap, "
                "(4) Check if the answer exists in your knowledge base."
            ),
        },
        "answer_correctness": {
            "threshold": 0.7,
            "low_suggestion": (
                "The answer does not match the expected ground truth. Try: "
                "(1) Improve retrieval to fetch more relevant context, "
                "(2) Use a stronger generation model, (3) Add few-shot examples "
                "to your prompt."
            ),
        },
    }

    def generate_suggestions(self, metrics: dict[str, float]) -> list[str]:
        suggestions = []
        for metric_name, score in metrics.items():
            rule = self.RULES.get(metric_name)
            if rule and score < rule["threshold"]:
                suggestions.append(
                    f"[{metric_name}: {score:.2f}] {rule['low_suggestion']}"
                )

        if not suggestions and metrics:
            suggestions.append(
                "All metrics are within acceptable range. Your RAG pipeline "
                "is performing well."
            )

        return suggestions


class RAGASEvaluator:
    """Runs RAGAS evaluation on trace data."""

    def __init__(self):
        self.suggestion_engine = SuggestionEngine()

    def evaluate(
        self,
        trace: Trace,
        metrics: list[str] = None,
        llm: Any = None,
        embeddings: Any = None,
    ) -> EvalResult:
        """
        Evaluate a trace using RAGAS metrics.

        Args:
            trace: The trace containing query, context, answer, ground_truth
            metrics: List of metric names to compute
            llm: LLM to use for evaluation (LangChain-compatible)
            embeddings: Embeddings model for semantic metrics
        """
        from ragas import evaluate as ragas_evaluate

        metrics = metrics or ["faithfulness", "answer_relevancy"]

        # Filter out ground-truth metrics if no ground truth available
        if not trace.ground_truth:
            metrics = [m for m in metrics if m not in GROUND_TRUTH_METRICS]

        if not metrics:
            logger.warning("No applicable metrics after filtering. Skipping eval.")
            return EvalResult(trace_id=trace.trace_id)

        # Load RAGAS metric objects
        ragas_metrics = []
        for m in metrics:
            metric_obj = _load_ragas_metric(m)
            if metric_obj:
                ragas_metrics.append(metric_obj)
            else:
                logger.warning(f"Unknown metric: {m}")

        if not ragas_metrics:
            return EvalResult(trace_id=trace.trace_id)

        # Build dataset for RAGAS
        contexts = []
        if trace.context:
            contexts = [trace.context]
        elif trace.retrieved_chunks:
            contexts = [
                str(chunk.get("result", chunk))
                for chunk in trace.retrieved_chunks
            ]

        data = {
            "question": [trace.query],
            "answer": [trace.answer],
            "contexts": [contexts],
        }

        if trace.ground_truth:
            data["ground_truth"] = [trace.ground_truth]

        dataset = Dataset.from_dict(data)

        # Run evaluation
        eval_kwargs = {"dataset": dataset, "metrics": ragas_metrics}
        if llm:
            eval_kwargs["llm"] = llm
        if embeddings:
            eval_kwargs["embeddings"] = embeddings

        try:
            result = ragas_evaluate(**eval_kwargs)
            result_dict = {m: float(result[m]) for m in metrics if m in result}
        except Exception as e:
            logger.error(f"RAGAS evaluation failed: {e}")
            result_dict = {}

        # Generate suggestions
        suggestions = self.suggestion_engine.generate_suggestions(result_dict)

        judge_model = ""
        if llm:
            judge_model = getattr(llm, "model_name", str(llm))

        eval_result = EvalResult(
            trace_id=trace.trace_id,
            metrics=result_dict,
            suggestions=suggestions,
            judge_model=judge_model,
        )

        logger.info(
            f"Evaluation complete for trace {trace.trace_id[:8]}: {result_dict}"
        )

        return eval_result

    def evaluate_batch(
        self,
        traces: list[Trace],
        metrics: list[str] = None,
        llm: Any = None,
        embeddings: Any = None,
    ) -> list[EvalResult]:
        """Evaluate multiple traces in batch."""
        results = []
        for trace in traces:
            result = self.evaluate(trace, metrics, llm, embeddings)
            results.append(result)
        return results
