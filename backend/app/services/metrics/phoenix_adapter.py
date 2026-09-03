"""
Arize Phoenix adapter — only importable if `pip install obtrac[arize]` (or
arize-phoenix-evals is otherwise installed); registry.py wraps the import
in a try/except so a missing dependency just means fewer metrics show up
in GET /evaluation/metrics-info, not a startup crash.

NOTE on license: arize-phoenix-evals is Elastic License 2.0 (ELv2), not a
permissive license like ObTrac's own MIT. It's used here as an optional
library dependency for self-hosted evaluation, which ELv2 permits — but
it's a meaningfully different license than the rest of this project, worth
knowing before enabling this extra.

NOTE on credentials (verified against the installed arize-phoenix-evals
3.6.0 source, not assumed): phoenix.evals.llm.LLM(provider="litellm",
api_key=...) stores that kwarg on the LiteLLMClient it builds, but the
LiteLLMAdapter's generate_text/generate_object methods never actually read
it back out when calling litellm.completion() — only kwargs passed at the
*call* site reach litellm, and Phoenix's own evaluator classes never pass
one through. So an API key given to the LLM() constructor is silently
dropped in this version. The reliable way to hand Phoenix's litellm client
real credentials is the environment variable litellm itself falls back to
(e.g. ANTHROPIC_API_KEY) — set for the duration of the call, restored
after. Since that's a *process-wide* mutation, every Phoenix-backed score()
call takes a module-level lock, trading away parallelism between Phoenix
metrics specifically (built-in and DeepEval metrics are unaffected and
still run fully concurrently) for not leaking one judge's credentials into
another judge's concurrent call.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING

from phoenix.evals import LLM

from app.services.metrics.base import MetricDefinition, MetricInput, MetricResult

if TYPE_CHECKING:
    from app.db.models import LLMConfigRecord

logger = logging.getLogger("obtrac")

_phoenix_call_lock = threading.Lock()

# litellm's own recognized env var per provider. Providers not listed here
# (azure_openai needs 3 separate env vars; vertex_ai/bedrock need
# credential files/IAM, not a single key) aren't supported by this adapter
# yet — scoring returns a clear error instead of silently using the wrong
# (or no) credentials.
_PROVIDER_ENV_VAR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
}


def _call_with_temp_credentials(llm_config: "LLMConfigRecord", fn):
    """Run `fn()` with llm_config's API key set as the env var litellm
    reads for its provider, restoring whatever was there before."""
    env_var = _PROVIDER_ENV_VAR.get(llm_config.provider)
    if not env_var:
        raise RuntimeError(
            f"The Phoenix adapter doesn't yet support provider '{llm_config.provider}' "
            f"(only {', '.join(_PROVIDER_ENV_VAR)} are wired up)."
        )
    with _phoenix_call_lock:
        previous = os.environ.get(env_var)
        if llm_config.api_key:
            os.environ[env_var] = llm_config.api_key
        try:
            return fn()
        finally:
            if previous is None:
                os.environ.pop(env_var, None)
            else:
                os.environ[env_var] = previous


class PhoenixMetricAdapter(MetricDefinition):
    source = "arize"
    category = "Arize Phoenix"

    def __init__(self, key: str, display_name: str, description: str, evaluator_cls,
                 build_eval_input, needs_ground_truth: bool = False, needs_context: bool = False,
                 threshold: float = 0.5):
        self.key = key
        self.display_name = display_name
        self.description = description
        self._evaluator_cls = evaluator_cls
        self._build_eval_input = build_eval_input
        self.needs_ground_truth = needs_ground_truth
        self.needs_context = needs_context
        self.threshold = threshold
        self.what_it_measures = description
        self.improvement_tips = [
            "See Arize Phoenix's docs for this metric: https://arize.com/docs/phoenix/evaluation",
        ]

    def score(self, inp: MetricInput, judge_llm: "LLMConfigRecord | None") -> MetricResult:
        if judge_llm is None:
            return MetricResult(metric=self.key, error="No judge LLM configured")

        from app.services.llm_judge import _litellm_model_string

        def _run():
            llm = LLM(provider="litellm", model=_litellm_model_string(judge_llm))
            evaluator = self._evaluator_cls(llm=llm)
            eval_input = self._build_eval_input(inp)
            return evaluator.evaluate(eval_input)

        try:
            scores = _call_with_temp_credentials(judge_llm, _run)
        except Exception as e:
            logger.warning(f"Phoenix metric '{self.key}' failed: {e}")
            return MetricResult(metric=self.key, error=str(e))

        if not scores:
            return MetricResult(metric=self.key, error="Phoenix evaluator returned no score")

        result = scores[0]
        raw = result.score
        # Phoenix marks each Score with its own optimization direction
        # instead of a fixed convention — invert "minimize" metrics
        # (e.g. toxicity: 1.0 = toxic) so higher is always better here,
        # matching every other metric source in this registry.
        normalized = (1.0 - raw) if result.direction == "minimize" else raw
        score = MetricResult.clamp_score(normalized)
        if score is None:
            return MetricResult(metric=self.key, error="Phoenix metric did not return a valid score")
        return MetricResult(metric=self.key, score=score, reason=result.explanation or "")


def build_metrics() -> list[PhoenixMetricAdapter]:
    """Raises ImportError if arize-phoenix-evals isn't installed —
    registry.py catches that and simply doesn't register these metrics."""
    from phoenix.evals.metrics import (
        CorrectnessEvaluator,
        FaithfulnessEvaluator,
        RetrievalRelevanceEvaluator,
        ToxicityEvaluator,
    )

    return [
        PhoenixMetricAdapter(
            key="phoenix_faithfulness", display_name="Faithfulness (Phoenix)",
            description="Arize Phoenix's faithfulness check: is the answer supported by the retrieved context.",
            evaluator_cls=FaithfulnessEvaluator, needs_context=True, threshold=0.7,
            build_eval_input=lambda inp: {
                "input": inp.question, "output": inp.answer, "context": "\n\n".join(inp.contexts),
            },
        ),
        PhoenixMetricAdapter(
            key="phoenix_correctness", display_name="Correctness (Phoenix)",
            description=(
                "Arize Phoenix's factual-accuracy check. Note: Phoenix's CorrectnessEvaluator "
                "judges from the LLM's own world knowledge — it doesn't take a ground-truth "
                "answer as input, unlike ObTrac's own answer_correctness metric."
            ),
            evaluator_cls=CorrectnessEvaluator, threshold=0.7,
            build_eval_input=lambda inp: {"input": inp.question, "output": inp.answer},
        ),
        PhoenixMetricAdapter(
            key="phoenix_toxicity", display_name="Toxicity (Phoenix)",
            description="Detects hateful, demeaning, abusive, or threatening content in the answer.",
            evaluator_cls=ToxicityEvaluator, threshold=0.5,
            build_eval_input=lambda inp: {"text": inp.answer},
        ),
        PhoenixMetricAdapter(
            key="phoenix_retrieval_relevance", display_name="Retrieval Relevance (Phoenix)",
            description="Whether the retrieved context contains information that materially helps answer the question — a retrieval-quality check, independent of the final answer.",
            evaluator_cls=RetrievalRelevanceEvaluator, needs_context=True, threshold=0.6,
            build_eval_input=lambda inp: {"input": inp.question, "context": "\n\n".join(inp.contexts)},
        ),
    ]
