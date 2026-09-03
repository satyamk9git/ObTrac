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


def _to_deepeval_tool_calls(calls: list) -> list:
    """Normalize ObTrac's tool-call dicts ({"name","args","result","status"})
    — or a bare tool-name string, for a hand-entered expected_tools list —
    into deepeval.test_case.ToolCall objects."""
    from deepeval.test_case import ToolCall

    result = []
    for c in calls or []:
        if isinstance(c, dict):
            result.append(ToolCall(
                name=c.get("name", ""),
                input_parameters=c.get("args", c.get("arguments")) or None,
                output=c.get("result"),
            ))
        else:
            result.append(ToolCall(name=str(c)))
    return result


def _test_case_from_input(inp: MetricInput) -> LLMTestCase:
    return LLMTestCase(
        input=inp.question,
        actual_output=inp.answer,
        expected_output=inp.ground_truth or None,
        context=inp.contexts or None,
        retrieval_context=inp.contexts or None,
        tools_called=_to_deepeval_tool_calls(inp.tool_calls) if inp.tool_calls else None,
        expected_tools=_to_deepeval_tool_calls(inp.expected_tools) if inp.expected_tools else None,
    )


class DeepEvalMetricAdapter(MetricDefinition):
    source = "deepeval"
    category = "DeepEval"

    def __init__(self, key: str, display_name: str, description: str, metric_cls,
                 needs_ground_truth: bool = False, needs_context: bool = False,
                 needs_tool_calls: bool = False, needs_expected_tools: bool = False,
                 threshold: float = 0.5, metric_kwargs: dict | None = None):
        self.key = key
        self.display_name = display_name
        self.description = description
        self._metric_cls = metric_cls
        self._metric_kwargs = metric_kwargs or {}
        self.needs_ground_truth = needs_ground_truth
        self.needs_context = needs_context
        self.needs_tool_calls = needs_tool_calls
        self.needs_expected_tools = needs_expected_tools
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


class GEvalMetricAdapter(MetricDefinition):
    """GEval is DeepEval's plain-English-criteria LLM judge — the same
    mechanism the (backlogged) custom-metric-authoring feature will use to
    compile a user-written rubric into a runnable metric. These three
    instances are fixed presets (general-purpose answer-quality checks that
    don't need a rubric-authoring UI to be useful), not user-customizable
    yet — registered the same way as any other built-in metric."""

    source = "deepeval"
    category = "DeepEval"

    def __init__(self, key: str, display_name: str, description: str, criteria: str, threshold: float = 0.6):
        self.key = key
        self.display_name = display_name
        self.description = description
        self.what_it_measures = description
        self.threshold = threshold
        self._criteria = criteria
        self.improvement_tips = [
            "See DeepEval's G-Eval docs: https://deepeval.com/docs/metrics-llm-evals",
        ]

    def score(self, inp: MetricInput, judge_llm: "LLMConfigRecord | None") -> MetricResult:
        if judge_llm is None:
            return MetricResult(metric=self.key, error="No judge LLM configured")
        try:
            from deepeval.metrics import GEval
            from deepeval.test_case import LLMTestCaseParams

            model = _ObTracDeepEvalModel(judge_llm)
            metric = GEval(
                name=self.display_name,
                criteria=self._criteria,
                evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
                model=model, threshold=self.threshold, async_mode=False,
            )
            test_case = _test_case_from_input(inp)
            metric.measure(test_case)
            score = MetricResult.clamp_score(metric.score)
            if score is None:
                return MetricResult(metric=self.key, error="G-Eval did not return a valid score")
            return MetricResult(metric=self.key, score=score, reason=getattr(metric, "reason", "") or "")
        except Exception as e:
            logger.warning(f"G-Eval metric '{self.key}' failed: {e}")
            return MetricResult(metric=self.key, error=str(e))


def build_metrics() -> list[MetricDefinition]:
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
        MisuseMetric,
        NonAdviceMetric,
        PIILeakageMetric,
        ToolCorrectnessMetric,
        ArgumentCorrectnessMetric,
        ToxicityMetric,
    )

    return [
        DeepEvalMetricAdapter(
            key="deepeval_faithfulness", display_name="Faithfulness (DeepEval)",
            description="DeepEval's faithfulness metric: extracts claims from the answer and checks each against the retrieved context, catching partial hallucination Cortexa's single-score judge can miss.",
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
            description="Whether the answer contradicts the provided context — a direct contradiction check, distinct from Cortexa's groundedness-style faithfulness score.",
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
        DeepEvalMetricAdapter(
            key="deepeval_pii_leakage", display_name="PII Leakage (DeepEval)",
            description="Detects personally identifiable information (names, emails, phone numbers, IDs) leaked in the generated answer.",
            metric_cls=PIILeakageMetric, threshold=0.5,
        ),
        DeepEvalMetricAdapter(
            key="deepeval_misuse", display_name="Misuse (DeepEval)",
            description=(
                "Detects the answer being used off-purpose — e.g. a support/knowledge-base "
                "assistant giving unrelated generated code, creative writing, or other "
                "out-of-domain output instead of answering from its knowledge base."
            ),
            metric_cls=MisuseMetric, threshold=0.5,
            metric_kwargs={"domain": "a RAG assistant answering questions from its own knowledge base"},
        ),
        DeepEvalMetricAdapter(
            key="deepeval_non_advice", display_name="Non-Advice (DeepEval)",
            description=(
                "Detects the answer giving regulated professional advice (medical, legal, "
                "or financial) it isn't qualified to give, rather than general information. "
                "Uses a generic medical/legal/financial default — most relevant for support "
                "and knowledge-base assistants in regulated domains."
            ),
            metric_cls=NonAdviceMetric, threshold=0.5,
            metric_kwargs={"advice_types": ["medical", "legal", "financial"]},
        ),
        DeepEvalMetricAdapter(
            key="deepeval_tool_correctness", display_name="Tool Correctness (DeepEval)",
            description="Whether the tools actually called match the expected tools for this task, by name.",
            metric_cls=ToolCorrectnessMetric, needs_tool_calls=True, needs_expected_tools=True, threshold=0.7,
        ),
        DeepEvalMetricAdapter(
            key="deepeval_argument_correctness", display_name="Argument Correctness (DeepEval)",
            description="Whether the arguments passed to the tools that were called are sensible given the question — doesn't require an expected-tools reference, unlike Tool Correctness.",
            metric_cls=ArgumentCorrectnessMetric, needs_tool_calls=True, threshold=0.7,
        ),
        GEvalMetricAdapter(
            key="geval_conciseness", display_name="Conciseness (G-Eval)",
            description="Whether the answer is concise and free of unnecessary padding, repetition, or irrelevant tangents.",
            criteria="Determine whether the actual output is concise — it should directly address the input without unnecessary repetition, padding, or irrelevant tangents.",
        ),
        GEvalMetricAdapter(
            key="geval_clarity", display_name="Clarity (G-Eval)",
            description="Whether the answer is clearly written and easy to understand, independent of factual correctness.",
            criteria="Determine whether the actual output is clear and easy to understand — well-structured, unambiguous, and free of confusing phrasing, regardless of whether the content is fully correct.",
        ),
        GEvalMetricAdapter(
            key="geval_coherence", display_name="Coherence (G-Eval)",
            description="Whether the answer is logically structured and internally consistent, with ideas that flow and don't contradict each other.",
            criteria="Determine whether the actual output is coherent — ideas should flow logically, later statements should not contradict earlier ones, and the overall structure should make sense as a whole.",
        ),
    ]
