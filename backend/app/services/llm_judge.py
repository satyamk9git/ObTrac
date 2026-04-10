"""
LLM-as-Judge — Direct evaluation without RAGAS.
Uses the configured auto-eval LLM to score traces.
"""

import json
import logging
import math
from langchain_community.chat_models import ChatLiteLLM

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
}


def _build_llm(config: LLMConfigRecord):
    """Build a LangChain LLM from config."""
    prefixes = {
        "openai": "", "azure_openai": "azure/", "anthropic": "anthropic/",
        "gemini": "gemini/", "ollama": "ollama/", "groq": "groq/",
    }
    prefix = prefixes.get(config.provider, "")
    if config.provider == "azure_openai" and config.azure_deployment:
        model = f"azure/{config.azure_deployment}"
    else:
        model = f"{prefix}{config.model_id}"

    kwargs = {}
    if config.api_key:
        kwargs["api_key"] = config.api_key
    if config.api_base:
        kwargs["api_base"] = config.api_base
    if config.provider == "azure_openai" and config.api_version:
        kwargs["api_version"] = config.api_version

    max_tok = "max_completion_tokens" if config.provider == "azure_openai" else "max_tokens"

    return ChatLiteLLM(model=model, temperature=0, **{max_tok: 512}, **kwargs)


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
    """
    metrics = metrics or ["faithfulness", "answer_relevancy"]
    llm = _build_llm(llm_config)

    result_metrics = {}
    result_reasons = {}

    for metric in metrics:
        prompt_template = JUDGE_PROMPTS.get(metric)
        if not prompt_template:
            continue

        # Skip context-dependent metrics if no context
        if "{context}" in prompt_template and not context:
            continue
        if "{ground_truth}" in prompt_template and not ground_truth:
            continue

        prompt = prompt_template.format(
            question=question,
            answer=answer,
            context=context or "No context provided.",
            ground_truth=ground_truth or "",
        )

        try:
            response = llm.invoke(prompt)
            text = response.content.strip()

            # Parse JSON from response
            if text.startswith("```"):
                text = text.split("```")[1].lstrip("json\n")
            parsed = json.loads(text)

            score = float(parsed.get("score", 0))
            if not math.isnan(score) and not math.isinf(score):
                result_metrics[metric] = round(min(max(score, 0), 1), 4)
                result_reasons[metric] = parsed.get("reason", "")

        except Exception as e:
            logger.warning(f"LLM judge failed for {metric}: {e}")

    return {
        "metrics": result_metrics,
        "reasons": result_reasons,
        "judge": f"{llm_config.provider}/{llm_config.model_id}",
    }
