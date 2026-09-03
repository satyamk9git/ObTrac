"""
Deterministic, judge-free metrics from RAGAS's own "Natural Language
Comparison" catalog (BLEU/ROUGE/chrF/exact match/string similarity): pure
string/n-gram comparison against ground truth, no LLM call, no cost, no
judge-bias risk, and no external dependency (hand-rolled here rather than
pulling in sacrebleu/rouge-score, matching this project's general policy
of keeping the always-available "ragas" source dependency-free —
optional frameworks like DeepEval/Phoenix are the ones that cost an
extra `pip install`, not this).

Always registered (source="ragas"), unlike deepeval_adapter.py/
phoenix_adapter.py which only register if their package is installed.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from difflib import SequenceMatcher

from app.services.metrics.base import MetricDefinition, MetricInput, MetricResult


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _ngrams(tokens: list[str], n: int) -> Counter:
    return Counter(tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1))


class DeterministicMetric(MetricDefinition):
    source = "ragas"
    category = "Text Comparison"
    needs_ground_truth = True
    needs_context = False

    def __init__(self, key: str, display_name: str, description: str, threshold: float, fn):
        self.key = key
        self.display_name = display_name
        self.description = description
        self.what_it_measures = description
        self.threshold = threshold
        self._fn = fn
        self.improvement_tips = [
            "This is a string-comparison metric, not an LLM judgment — a low "
            "score often just means a correct answer was phrased differently "
            "than the ground truth. Cross-check against answer_similarity or "
            "answer_correctness before assuming the answer is wrong.",
        ]

    def score(self, inp: MetricInput, judge_llm) -> MetricResult:
        # No judge_llm needed — deterministic, ignores it entirely.
        try:
            value = self._fn(inp.answer or "", inp.ground_truth or "")
            score = MetricResult.clamp_score(value)
            if score is None:
                return MetricResult(metric=self.key, error="Comparison produced a non-numeric result")
            return MetricResult(metric=self.key, score=score, reason="")
        except Exception as e:
            return MetricResult(metric=self.key, error=str(e))


def _exact_match(answer: str, ground_truth: str) -> float:
    return 1.0 if answer.strip().lower() == ground_truth.strip().lower() else 0.0


def _string_presence(answer: str, ground_truth: str) -> float:
    return 1.0 if ground_truth.strip().lower() in answer.strip().lower() else 0.0


def _non_llm_string_similarity(answer: str, ground_truth: str) -> float:
    return SequenceMatcher(None, answer.strip().lower(), ground_truth.strip().lower()).ratio()


def _bleu_score(answer: str, ground_truth: str, max_n: int = 4) -> float:
    """Standard BLEU with add-1 smoothing (avoids a hard 0 from one missing
    n-gram order on short answers) and a brevity penalty."""
    hyp, ref = _tokenize(answer), _tokenize(ground_truth)
    if not hyp or not ref:
        return 0.0
    precisions = []
    for n in range(1, max_n + 1):
        hyp_ngrams, ref_ngrams = _ngrams(hyp, n), _ngrams(ref, n)
        overlap = sum((hyp_ngrams & ref_ngrams).values())
        total = max(sum(hyp_ngrams.values()), 1)
        precisions.append((overlap + 1) / (total + 1))
    geo_mean = math.exp(sum(math.log(p) for p in precisions) / len(precisions))
    brevity_penalty = 1.0 if len(hyp) > len(ref) else math.exp(1 - len(ref) / max(len(hyp), 1))
    return geo_mean * brevity_penalty


def _rouge_l(answer: str, ground_truth: str) -> float:
    """ROUGE-L: F-measure over the longest common subsequence."""
    hyp, ref = _tokenize(answer), _tokenize(ground_truth)
    if not hyp or not ref:
        return 0.0
    m, n = len(hyp), len(ref)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            dp[i][j] = dp[i - 1][j - 1] + 1 if hyp[i - 1] == ref[j - 1] else max(dp[i - 1][j], dp[i][j - 1])
    lcs = dp[m][n]
    if lcs == 0:
        return 0.0
    precision, recall = lcs / m, lcs / n
    return 2 * precision * recall / (precision + recall)


def _chrf_score(answer: str, ground_truth: str, n: int = 6) -> float:
    """chrF: character n-gram F-score, averaged over n-gram orders 1..n."""
    hyp_chars = re.sub(r"\s+", " ", answer.strip().lower())
    ref_chars = re.sub(r"\s+", " ", ground_truth.strip().lower())
    if not hyp_chars or not ref_chars:
        return 0.0
    f_scores = []
    for order in range(1, n + 1):
        hyp_ngrams = Counter(hyp_chars[i:i + order] for i in range(len(hyp_chars) - order + 1))
        ref_ngrams = Counter(ref_chars[i:i + order] for i in range(len(ref_chars) - order + 1))
        if not hyp_ngrams or not ref_ngrams:
            continue
        overlap = sum((hyp_ngrams & ref_ngrams).values())
        precision = overlap / max(sum(hyp_ngrams.values()), 1)
        recall = overlap / max(sum(ref_ngrams.values()), 1)
        if precision + recall > 0:
            f_scores.append(2 * precision * recall / (precision + recall))
    return sum(f_scores) / len(f_scores) if f_scores else 0.0


def build_metrics() -> list[DeterministicMetric]:
    return [
        DeterministicMetric(
            key="exact_match", display_name="Exact Match",
            description="Whether the answer is character-for-character identical to the ground truth (case-insensitive).",
            threshold=1.0, fn=_exact_match,
        ),
        DeterministicMetric(
            key="string_presence", display_name="String Presence",
            description="Whether the ground truth text appears verbatim as a substring of the answer.",
            threshold=1.0, fn=_string_presence,
        ),
        DeterministicMetric(
            key="non_llm_string_similarity", display_name="String Similarity",
            description="Character-sequence similarity ratio between the answer and ground truth — a fast, non-LLM lower bound on correctness.",
            threshold=0.6, fn=_non_llm_string_similarity,
        ),
        DeterministicMetric(
            key="bleu_score", display_name="BLEU Score",
            description="N-gram precision (1-4 grams) between the answer and ground truth with a brevity penalty — standard machine-translation-style overlap metric.",
            threshold=0.3, fn=_bleu_score,
        ),
        DeterministicMetric(
            key="rouge_score", display_name="ROUGE-L Score",
            description="F-measure over the longest common subsequence of words between the answer and ground truth.",
            threshold=0.4, fn=_rouge_l,
        ),
        DeterministicMetric(
            key="chrf_score", display_name="chrF Score",
            description="Character n-gram F-score between the answer and ground truth — more robust than BLEU/ROUGE to small wording/morphology differences.",
            threshold=0.4, fn=_chrf_score,
        ),
        ToolCallSuccessRateMetric(),
    ]


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
