"""
DeepEval adapter — only importable if `pip install obtrac[deepeval]` (or
deepeval is otherwise installed); registry.py wraps the import in a
try/except so a missing dependency just means fewer metrics show up in
GET /evaluation/metrics-info, not a startup crash.

DeepEval's own internal LLM calls (claim extraction, verdict generation,
etc.) are routed through litellm using ObTrac's existing LLMConfigRecord
credentials via _ObTracDeepEvalModel, so using a DeepEval metric doesn't
require a second, separate API key — same judge config as everything else.

All keys are prefixed "deepeval_" so they can never collide with ObTrac's
own built-in metric keys (e.g. "faithfulness") in the flat registry.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase

from app.services.metrics.base import MetricDefinition, MetricInput, MetricResult

if TYPE_CHECKING:
    from app.db.models import LLMConfigRecord

logger = logging.getLogger("obtrac")

# DeepEval's own prompts (multi-step claim extraction, verdict lists, etc.)
# are far more verbose than ObTrac's short {"score","reason"} judge
# prompts — 512 tokens (llm_judge.py's default) truncates them badly.
_DEEPEVAL_MAX_TOKENS = 4096


class _ObTracDeepEvalModel(DeepEvalBaseLLM):
    """Adapts ObTrac's litellm-backed judge (app.services.llm_judge._build_llm)
    to DeepEvalBaseLLM's interface, so DeepEval metrics run through the same
    provider/credential plumbing as every other judge call in ObTrac."""

    def __init__(self, llm_config: "LLMConfigRecord"):
        self._llm_config = llm_config
        super().__init__(model=llm_config.model_id)

    def load_model(self):
        from app.services.llm_judge import _build_llm
        return _build_llm(self._llm_config, max_tokens=_DEEPEVAL_MAX_TOKENS)

    def generate(self, prompt: str, *args, **kwargs) -> str:
        return self.model.invoke(prompt).content

    async def a_generate(self, prompt: str, *args, **kwargs) -> str:
        # DeepEval metrics default to async_mode=True, but every metric
        # below is constructed with async_mode=False so this path isn't
        # actually exercised — implemented anyway since it's abstract.
        return self.generate(prompt)

    def get_model_name(self) -> str:
        return f"{self._llm_config.provider}/{self._llm_config.model_id}"


def _test_case_from_input(inp: MetricInput) -> LLMTestCase:
    return LLMTestCase(
        input=inp.question,
        actual_output=inp.answer,
        expected_output=inp.ground_truth or None,
        context=inp.contexts or None,
        retrieval_context=inp.contexts or None,
    )


class DeepEvalMetricAdapter(MetricDefinition):
    source = "deepeval"
    category = "DeepEval"

    def __init__(self, key: str, display_name: str, description: str, metric_cls,
                 needs_ground_truth: bool = False, needs_context: bool = False,
                 threshold: float = 0.5, metric_kwargs: dict | None = None):
        self.key = key
        self.display_name = display_name
        self.description = description
        self._metric_cls = metric_cls
        self._metric_kwargs = metric_kwargs or {}
        self.needs_ground_truth = needs_ground_truth
        self.needs_context = needs_context
        self.threshold = threshold
        self.what_it_measures = description
        self.improvement_tips = [
            "See DeepEval's docs for this metric: https://deepeval.com/docs/metrics-introduction",
        ]

    def score(self, inp: MetricInput, judge_llm: "LLMConfigRecord | None") -> MetricResult:
        if judge_llm is None:
            return MetricResult(metric=self.key, error="No judge LLM configured")
        try:
            model = _ObTracDeepEvalModel(judge_llm)
            metric = self._metric_cls(
                threshold=self.threshold, model=model,
                include_reason=True, async_mode=False,
                **self._metric_kwargs,
            )
            test_case = _test_case_from_input(inp)
            metric.measure(test_case)
            score = MetricResult.clamp_score(metric.score)
            if score is None:
                return MetricResult(metric=self.key, error="DeepEval metric did not return a valid score")
            return MetricResult(metric=self.key, score=score, reason=getattr(metric, "reason", "") or "")
        except Exception as e:
            logger.warning(f"DeepEval metric '{self.key}' failed: {e}")
            return MetricResult(metric=self.key, error=str(e))


def build_metrics() -> list[DeepEvalMetricAdapter]:
    """Raises ImportError if deepeval isn't installed — registry.py catches
    that and simply doesn't register these metrics."""
    from deepeval.metrics import (
        AnswerRelevancyMetric,
        BiasMetric,
        ContextualPrecisionMetric,
        ContextualRecallMetric,
        ContextualRelevancyMetric,
        FaithfulnessMetric,
        HallucinationMetric,
        ToxicityMetric,
    )

    return [
        DeepEvalMetricAdapter(
            key="deepeval_faithfulness", display_name="Faithfulness (DeepEval)",
            description="DeepEval's faithfulness metric: extracts claims from the answer and checks each against the retrieved context, catching partial hallucination ObTrac's single-score judge can miss.",
            metric_cls=FaithfulnessMetric, needs_context=True, threshold=0.7,
        ),
        DeepEvalMetricAdapter(
            key="deepeval_answer_relevancy", display_name="Answer Relevancy (DeepEval)",
            description="DeepEval's answer relevancy metric: extracts statements from the answer and checks each is relevant to the question.",
            metric_cls=AnswerRelevancyMetric, threshold=0.7,
        ),
        DeepEvalMetricAdapter(
            key="deepeval_contextual_precision", display_name="Contextual Precision (DeepEval)",
            description="Whether relevant retrieved chunks are ranked above irrelevant ones, using the expected answer as the relevance reference.",
            metric_cls=ContextualPrecisionMetric, needs_context=True, needs_ground_truth=True, threshold=0.6,
        ),
        DeepEvalMetricAdapter(
            key="deepeval_contextual_recall", display_name="Contextual Recall (DeepEval)",
            description="Whether the retrieved context contains everything needed to produce the expected answer.",
            metric_cls=ContextualRecallMetric, needs_context=True, needs_ground_truth=True, threshold=0.6,
        ),
        DeepEvalMetricAdapter(
            key="deepeval_contextual_relevancy", display_name="Contextual Relevancy (DeepEval)",
            description="What fraction of the retrieved context is actually relevant to the question, independent of ranking.",
            metric_cls=ContextualRelevancyMetric, needs_context=True, threshold=0.6,
        ),
        DeepEvalMetricAdapter(
            key="deepeval_hallucination", display_name="Hallucination (DeepEval)",
            description="Whether the answer contradicts the provided context — a direct contradiction check, distinct from ObTrac's groundedness-style faithfulness score.",
            metric_cls=HallucinationMetric, needs_context=True, threshold=0.5,
        ),
        DeepEvalMetricAdapter(
            key="deepeval_bias", display_name="Bias (DeepEval)",
            description="Detects gender, racial, political, or other bias in the generated answer.",
            metric_cls=BiasMetric, threshold=0.5,
        ),
        DeepEvalMetricAdapter(
            key="deepeval_toxicity", display_name="Toxicity (DeepEval)",
            description="Detects toxic, harmful, or offensive content in the generated answer.",
            metric_cls=ToxicityMetric, threshold=0.5,
        ),
    ]
