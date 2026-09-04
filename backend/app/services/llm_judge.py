"""
LLM-as-Judge — Direct evaluation without RAGAS.
Uses the configured auto-eval LLM to score traces.
"""

import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import SimpleNamespace

import litellm

from app.db.models import LLMConfigRecord

logger = logging.getLogger("obtrac")

JUDGE_PROMPTS = {
    "faithfulness": """You are an evaluation judge. Score how faithful the answer is to the provided context.
A faithful answer ONLY contains information from the context. Hallucinated information scores low.

Context:
{context}

Question: {question}
Answer: {answer}

Score from 0.0 to 1.0 where:
- 1.0 = Completely faithful, all claims supported by context
- 0.5 = Partially faithful, some unsupported claims
- 0.0 = Completely hallucinated, not grounded in context

Reply ONLY with JSON: {{"score": 0.0-1.0, "reason": "one line explanation"}}""",

    "answer_relevancy": """You are an evaluation judge. Score how relevant the answer is to the question.

Question: {question}
Answer: {answer}

Score from 0.0 to 1.0 where:
- 1.0 = Directly answers the question completely
- 0.5 = Partially answers or drifts off topic
- 0.0 = Does not address the question at all

Reply ONLY with JSON: {{"score": 0.0-1.0, "reason": "one line explanation"}}""",

    "context_precision": """You are an evaluation judge. Score how precise the retrieved context is.
Does the context contain relevant information for answering the question?

Question: {question}
Context:
{context}

Score from 0.0 to 1.0 where:
- 1.0 = All retrieved context is highly relevant
- 0.5 = Some relevant, some irrelevant
- 0.0 = Context is completely irrelevant

Reply ONLY with JSON: {{"score": 0.0-1.0, "reason": "one line explanation"}}""",

    "answer_correctness": """You are an evaluation judge. Score the factual correctness of the answer compared to the ground truth.

Question: {question}
Answer: {answer}
Ground Truth: {ground_truth}

Score from 0.0 to 1.0 where:
- 1.0 = Factually identical to ground truth
- 0.5 = Partially correct
- 0.0 = Completely wrong

Reply ONLY with JSON: {{"score": 0.0-1.0, "reason": "one line explanation"}}""",

    "context_recall": """You are an evaluation judge. Score whether the retrieved context contains ALL the information needed to produce the ground truth answer.
This is about completeness of retrieval, not precision — irrelevant extra chunks don't hurt this score, but missing information does.

Question: {question}
Ground Truth: {ground_truth}
Retrieved Context:
{context}

Score from 0.0 to 1.0 where:
- 1.0 = Every fact in the ground truth can be found in the retrieved context
- 0.5 = Some facts from the ground truth are present, others are missing
- 0.0 = None of the ground truth's facts are present in the retrieved context

Reply ONLY with JSON: {{"score": 0.0-1.0, "reason": "one line explanation"}}""",

    "agent_goal_accuracy": """You are an evaluation judge using RAGAS's agent-goal-accuracy methodology — a binary (not graded) verdict on whether the agent achieved what the user actually asked for, considering its full tool-call trajectory and final answer.
If a ground truth / expected outcome is provided, compare the agent's actual end state against it. If none is provided, infer from the question alone what a successful outcome would look like, then judge whether the actual trajectory and answer achieved it.

Question: {question}
Tool Calls Made:
{actual_tool_calls}
Final Answer: {answer}
Expected Outcome (if known): {ground_truth}

Reply with a binary verdict:
- 1.0 = The agent achieved the user's goal — correct tools used (if any were needed) and the final answer resolves the request
- 0.0 = The agent did NOT achieve the goal — wrong approach, incomplete, or the final answer doesn't actually resolve what was asked

Reply ONLY with JSON: {{"score": 0.0 or 1.0, "reason": "one line explanation"}}""",
}


class _LiteLLMChat:
    """Minimal ChatLiteLLM replacement — langchain_community 0.4.x removed
    ChatLiteLLM entirely, so call litellm directly. Only implements
    .invoke(text) -> obj.content, which is all this module needs."""

    def __init__(self, model, kwargs):
        self.model = model
        self.kwargs = kwargs

    def invoke(self, prompt_text: str):
        resp = litellm.completion(
            model=self.model,
            messages=[{"role": "user", "content": prompt_text}],
            **self.kwargs,
        )
        return SimpleNamespace(content=resp.choices[0].message.content)


def _litellm_model_string(config: LLMConfigRecord) -> str:
    """The litellm `model=` string for a given config, e.g. "anthropic/claude-sonnet-5".
    Shared with external-framework adapters (deepeval_adapter, phoenix_adapter)
    that need to address the same judge model litellm-style, not just this
    module's own _build_llm."""
    prefixes = {
        "openai": "", "azure_openai": "azure/", "anthropic": "anthropic/",
        "gemini": "gemini/", "ollama": "ollama/", "groq": "groq/",
    }
    prefix = prefixes.get(config.provider, "")
    if config.provider == "azure_openai" and config.azure_deployment:
        return f"azure/{config.azure_deployment}"
    return f"{prefix}{config.model_id}"


def _build_llm(config: LLMConfigRecord, max_tokens: int = 512):
    """Build a litellm-backed chat object from config. `max_tokens`
    defaults to 512 (enough for ObTrac's own short {"score","reason"} judge
    prompts) but external-framework adapters (e.g. DeepEval, whose internal
    prompts ask for much longer structured reasoning) pass a higher value."""
    model = _litellm_model_string(config)

    kwargs = {}
    if config.api_key:
        kwargs["api_key"] = config.api_key
    if config.api_base:
        kwargs["api_base"] = config.api_base
    if config.provider == "azure_openai" and config.api_version:
        kwargs["api_version"] = config.api_version

    max_tok = "max_completion_tokens" if config.provider == "azure_openai" else "max_tokens"

    # Anthropic models run extended thinking by default and reject any
    # temperature other than 1 (and reject top_p entirely) while thinking
    # is active.
    judge_temperature = 1 if config.provider == "anthropic" else 0
    kwargs["temperature"] = judge_temperature
    kwargs[max_tok] = max_tokens
    return _LiteLLMChat(model=model, kwargs=kwargs)


def _score_one_metric(llm, metric: str, prompt_template: str, question: str, answer: str,
                       context: str, ground_truth: str, **extra_fields):
    """Run a single metric's judge prompt. Returns (metric, score, reason) or
    (metric, None, None) on failure/skip — isolated so it can run in a
    worker thread alongside the other metrics. `extra_fields` lets prompts
    with placeholders beyond the standard 4 (e.g. tool-call metrics needing
    {actual_tool_calls}/{expected_tool_calls}) reuse this same call/parse
    path instead of duplicating it."""
    prompt = prompt_template.format(
        question=question,
        answer=answer,
        context=context or "No context provided.",
        ground_truth=ground_truth or "",
        **extra_fields,
    )
    try:
        response = llm.invoke(prompt)
        text = response.content.strip()

        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json\n")
        parsed = json.loads(text)

        score = float(parsed.get("score", 0))
        if math.isnan(score) or math.isinf(score):
            return metric, None, None
        return metric, round(min(max(score, 0), 1), 4), parsed.get("reason", "")
    except Exception as e:
        logger.warning(f"LLM judge failed for {metric}: {e}")
        return metric, None, None


def evaluate_with_llm_judge(
    llm_config: LLMConfigRecord,
    question: str,
    answer: str,
    context: str = "",
    ground_truth: str = "",
    metrics: list[str] = None,
) -> dict:
    """
    Evaluate a trace using LLM-as-judge (no RAGAS dependency).
    Returns {"metrics": {...}, "reasons": {...}, "judge": "..."}

    Each metric is an independent LLM call (its own judge prompt, its own
    response) — they're run concurrently in a thread pool instead of one
    after another, since a full 6-metric eval run sequentially was taking
    six full round-trips (worse with Claude's extended thinking adding
    per-call latency) when the results don't depend on each other at all.
    """
    metrics = metrics or ["faithfulness", "answer_relevancy"]
    llm = _build_llm(llm_config)

    runnable = []
    for metric in metrics:
        prompt_template = JUDGE_PROMPTS.get(metric)
        if not prompt_template:
            continue
        if "{context}" in prompt_template and not context:
            continue
        if "{ground_truth}" in prompt_template and not ground_truth:
            continue
        runnable.append((metric, prompt_template))

    result_metrics = {}
    result_reasons = {}

    if runnable:
        with ThreadPoolExecutor(max_workers=min(len(runnable), 6)) as pool:
            futures = [
                pool.submit(_score_one_metric, llm, metric, template, question, answer, context, ground_truth)
                for metric, template in runnable
            ]
            for future in as_completed(futures):
                metric, score, reason = future.result()
                if score is not None:
                    result_metrics[metric] = score
                    result_reasons[metric] = reason

    return {
        "metrics": result_metrics,
        "reasons": result_reasons,
        "judge": f"{llm_config.provider}/{llm_config.model_id}",
    }
