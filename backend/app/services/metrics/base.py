"""
Core metric abstractions.

Before this module existed, the same 6 metric names were independently
hardcoded in four disconnected places: JUDGE_PROMPTS (llm_judge.py),
METRIC_INFO (evaluation.py), SuggestionEngine.RULES (obtrac_sdk/evaluator.py),
and METRIC_KNOWLEDGE (explain.py). Every metric — built-in judge-prompt
metric, external-framework adapter (DeepEval/MLflow/Phoenix), or a future
custom metric — now implements MetricDefinition once and is looked up by
key through MetricRegistry (registry.py) everywhere else.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models import LLMConfigRecord


@dataclass
class MetricInput:
    """Everything a metric might need to score one trace. A metric that
    doesn't use a given field simply ignores it."""

    question: str = ""
    answer: str = ""
    contexts: list[str] = field(default_factory=list)  # multi-chunk; full list for context-aware metrics
    ground_truth: str = ""
    retrieved_chunks: list[dict] = field(default_factory=list)
    trace_metadata: dict[str, Any] = field(default_factory=dict)
    # Tool-call data, walked from trace.spans where span_type == "tool_call":
    # [{"name": str, "args": dict, "result": Any, "status": str}, ...].
    # expected_tools comes from a matched GroundTruthRecord.expected_tools,
    # same shape, no "result"/"status" (those describe what happened, not
    # what should happen).
    tool_calls: list[dict] = field(default_factory=list)
    expected_tools: list[dict] = field(default_factory=list)

    @property
    def context(self) -> str:
        """Single-string view (first context chunk) for metrics that were
        built against ObTrac's original single-string context model."""
        return self.contexts[0] if self.contexts else ""

    @property
    def has_context(self) -> bool:
        return bool(self.contexts)

    @property
    def has_ground_truth(self) -> bool:
        return bool(self.ground_truth)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    @property
    def has_expected_tools(self) -> bool:
        return bool(self.expected_tools)


@dataclass
class MetricResult:
    metric: str
    score: Optional[float] = None
    reason: str = ""
    error: Optional[str] = None

    @staticmethod
    def clamp_score(raw: Any) -> Optional[float]:
        """Shared score-sanitizing logic: coerce to float, reject NaN/Inf,
        clamp to [0, 1], round to 4dp. Returns None if unusable."""
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        if math.isnan(value) or math.isinf(value):
            return None
        return round(min(max(value, 0.0), 1.0), 4)


class MetricDefinition(ABC):
    """Base class every metric implements. One instance per metric is
    registered with MetricRegistry and looked up by `key` everywhere else
    (gating, execution, /evaluation/metrics-info, the AI-explain modal)."""

    key: str = ""
    display_name: str = ""
    category: str = "Uncategorized"
    source: str = "custom"  # "ragas" | "deepeval" | "mlflow" | "arize" | "custom"
    needs_ground_truth: bool = False
    needs_context: bool = False
    needs_tool_calls: bool = False
    needs_expected_tools: bool = False
    threshold: float = 0.7
    description: str = ""
    what_it_measures: str = ""
    score_interpretation: dict[str, str] = {}
    improvement_tips: list[str] = []

    def is_runnable(self, inp: MetricInput) -> tuple[bool, Optional[str]]:
        """Whether this metric can run against the given input.
        Returns (True, None) if runnable, else (False, reason)."""
        if self.needs_ground_truth and not inp.has_ground_truth:
            return False, "Requires ground truth. Upload via Resources or provide directly."
        if self.needs_context and not inp.has_context:
            return False, "No retrieved context available in this trace."
        if self.needs_tool_calls and not inp.has_tool_calls:
            return False, "No tool calls captured in this trace. Instrument tool functions with @trace(tool_name=...) to enable this metric."
        if self.needs_expected_tools and not inp.has_expected_tools:
            return False, "Requires an expected-tools reference. Add expected_tools to this question's ground-truth dataset entry."
        return True, None

    @abstractmethod
    def score(self, inp: MetricInput, judge_llm: "LLMConfigRecord | None") -> MetricResult:
        """Score one trace. Must not raise — catch internally and return a
        MetricResult with `error` set, so one bad metric never breaks the
        rest of a batch."""
        ...

    def info_dict(self) -> dict:
        """Shape matching the legacy METRIC_INFO dict, for
        GET /evaluation/metrics-info and the AI-explain fallback."""
        return {
            "name": self.display_name or self.key,
            "description": self.description,
            "needs_ground_truth": self.needs_ground_truth,
            "needs_context": self.needs_context,
            "needs_tool_calls": self.needs_tool_calls,
            "needs_expected_tools": self.needs_expected_tools,
            "threshold": self.threshold,
            "category": self.category,
            "source": self.source,
            "what_it_measures": self.what_it_measures,
            "score_interpretation": self.score_interpretation,
            "improvement_tips": self.improvement_tips,
        }
