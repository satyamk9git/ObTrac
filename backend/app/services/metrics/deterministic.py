"""
Deterministic, judge-free metrics — no LLM call, no cost, no judge-bias
risk. Always registered (source="ragas"), unlike deepeval_adapter.py/
phoenix_adapter.py which only register if their package is installed.
"""

from __future__ import annotations

from app.services.metrics.base import MetricDefinition, MetricInput, MetricResult


def build_metrics() -> list[MetricDefinition]:
    return [ToolCallSuccessRateMetric()]


class ToolCallSuccessRateMetric(MetricDefinition):
    """Deterministic — fraction of the trace's tool calls that succeeded.
    Doesn't need DeterministicMetric's (answer, ground_truth) -> float
    shape since it reads inp.tool_calls instead, so it's its own small
    class rather than another DeterministicMetric instance."""

    source = "ragas"
    category = "Tool Use"
    key = "tool_call_success_rate"
    display_name = "Tool Call Success Rate"
    description = "Fraction of tool calls in this trace that completed successfully (vs. errored)."
    what_it_measures = description
    needs_ground_truth = False
    needs_context = False
    needs_tool_calls = True
    threshold = 0.9
    improvement_tips = [
        "Check the failing tool call's arguments — a common cause is the model passing malformed input",
        "Verify the tool itself is reachable/healthy (API down, auth expired, rate limited)",
        "Add retry logic or clearer tool descriptions if the model is calling tools incorrectly",
    ]

    def score(self, inp: MetricInput, judge_llm) -> MetricResult:
        if not inp.tool_calls:
            return MetricResult(metric=self.key, error="No tool calls to score")
        successes = sum(1 for c in inp.tool_calls if c.get("status") == "success")
        rate = successes / len(inp.tool_calls)
        return MetricResult(
            metric=self.key, score=round(rate, 4),
            reason=f"{successes}/{len(inp.tool_calls)} tool calls succeeded",
        )
