"""
Runs a set of metrics against one MetricInput, in parallel — same pattern
evaluate_with_llm_judge used, generalized to any MetricDefinition source
(built-in judge prompts, DeepEval, MLflow, Phoenix, custom) instead of only
LLM-judge prompt metrics.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from app.services.metrics.base import MetricInput, MetricResult
from app.services.metrics.registry import get_registry

if TYPE_CHECKING:
    from app.db.models import LLMConfigRecord

logger = logging.getLogger("obtrac")


class MetricRunner:
    @staticmethod
    def run(
        metric_keys: list[str],
        inp: MetricInput,
        judge_llm: "LLMConfigRecord | None",
    ) -> list[MetricResult]:
        """Score `inp` against every metric in metric_keys that's actually
        registered and runnable. Unknown/unrunnable metrics are silently
        skipped here — callers that need skip reasons should check
        registry.get(key).is_runnable(inp) themselves before calling run()
        (this mirrors how evaluate_with_llm_judge worked: gating is the
        caller's job, running is this function's job)."""
        registry = get_registry()

        runnable = []
        for key in metric_keys:
            metric = registry.get(key)
            if metric is None:
                continue
            ok, _ = metric.is_runnable(inp)
            if ok:
                runnable.append(metric)

        if not runnable:
            return []

        results: list[MetricResult] = []
        with ThreadPoolExecutor(max_workers=min(len(runnable), 6)) as pool:
            futures = {pool.submit(m.score, inp, judge_llm): m for m in runnable}
            for future in as_completed(futures):
                metric = futures[future]
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.warning(f"Metric '{metric.key}' raised instead of returning an error result: {e}")
                    results.append(MetricResult(metric=metric.key, error=str(e)))
        return results
